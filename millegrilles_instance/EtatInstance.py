import os

import aiohttp
import datetime
import logging
import json

from asyncio import Event
from json.decoder import JSONDecodeError
from typing import Optional
from os import path, listdir

from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages import Constantes
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.Certificats import preparer_certificats_web, generer_certificats_modules, generer_passwords, \
    generer_certificats_modules_satellites
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_messages.IpUtils import get_ip, get_hostname
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.FormatteurMessages import SignateurTransactionSimple, FormatteurMessageMilleGrilles
from millegrilles_instance.EntretienNginx import EntretienNginx
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_messages.messages.ValidateurCertificats import ValidateurCertificatCache
from millegrilles_messages.messages.ValidateurMessage import ValidateurMessage


class EtatInstance:

    def __init__(self, configuration: ConfigurationInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__client_session = aiohttp.ClientSession()

        self.__ip_address: Optional[str] = None
        self.__hostname: Optional[str] = None
        self.__instance_id: Optional[str] = None
        self.__niveau_securite: Optional[str] = None
        self.__idmg: Optional[str] = None
        self.__certificat_millegrille: Optional[EnveloppeCertificat] = None
        self.__clecertificat: Optional[CleCertificat] = None
        self.__password_mq: Optional[str] = None

        self.__host_mq = "localhost"
        self.__port_mq = 5673

        self.__docker_present = False
        self.__docker_actif = False
        self.__csr_genere: Optional[CleCsrGenere] = None

        self.__entretien_nginx: Optional[EntretienNginx] = None

        # Liste de listeners qui sont appeles sur changement de configuration
        self.__config_listeners = list()
        self.__formatteur_message: Optional[FormatteurMessageMilleGrilles] = None
        self.__validateur_certificats: Optional[ValidateurCertificatCache] = None
        self.__validateur_message: Optional[ValidateurMessage] = None

        self.__stop_event: Optional[Event] = None
        self.__redemarrer = False

        self.__attente_rotation_maitredescles: Optional[datetime.datetime] = None

        self.__certificats_maitredescles: dict[str, CacheCertificat] = dict()

    async def reload_configuration(self):
        self.__logger.info("Reload configuration sur disque ou dans docker")

        self.__ip_address = get_ip()
        self.__hostname = get_hostname(fqdn=True)
        self.__logger.debug("Nom domaine instance: %s" % self.__hostname)

        # Generer les certificats web self-signed au besoin
        path_cert_web, path_cle_web = preparer_certificats_web(self.__configuration.path_secrets)
        self.__configuration.path_certificat_web = path_cert_web
        self.__configuration.path_cle_web = path_cle_web

        self.__instance_id = load_fichier_config(self.__configuration.instance_id_path)
        self.__logger.info("Instance id : %s", self.__instance_id)

        self.__niveau_securite = load_fichier_config(self.__configuration.instance_securite_path)
        self.__logger.info("Securite : %s", self.__niveau_securite)

        self.__idmg = load_fichier_config(self.__configuration.instance_idmg_path)
        self.__logger.info("IDMG : %s", self.__idmg)

        self.__certificat_millegrille = load_enveloppe_cert(self.__configuration.instance_ca_pem_path)
        self.__logger.debug("Certificat Millegrille\n%s" % self.__certificat_millegrille)

        self.__clecertificat = load_clecert(self.__configuration.instance_key_pem_path,
                                            self.__configuration.instance_cert_pem_path)
        self.__logger.debug("Certificat instance: %s" % self.__clecertificat)

        # Exporter configuration pour modules dependants
        self.maj_configuration_json()

        if self.__clecertificat is not None:
            signateur = SignateurTransactionSimple(self.__clecertificat)
            self.__formatteur_message = FormatteurMessageMilleGrilles(self.__idmg, signateur)
            self.__validateur_certificats = ValidateurCertificatCache(self.__certificat_millegrille)
            self.__validateur_message = ValidateurMessage(self.__validateur_certificats)

        for listener in self.__config_listeners:
            await listener(self)

    def maj_configuration_json(self, configuration: Optional[dict] = None):
        config_json_path = self.configuration.config_json
        try:
            with open(config_json_path, 'rb') as fichier:
                params_courants = json.load(fichier)
            os.rename(config_json_path, config_json_path + '.old')
        except FileNotFoundError:
            params_courants = dict()
        except JSONDecodeError:
            raise Exception("Fichier %s corrompu" % config_json_path)

        params_courants['instance_id'] = self.instance_id
        params_courants['idmg'] = self.idmg or params_courants.get('idmg')
        params_courants['securite'] = self.niveau_securite or params_courants.get('securite')

        if configuration is not None:
            params_courants.update(configuration)

        try:
            self.__host_mq = params_courants['mq_host']
        except KeyError:
            pass

        try:
            self.__port_mq = params_courants['mq_port']
        except KeyError:
            pass

        with open(config_json_path, 'w') as fichier:
            json.dump(params_courants, fichier, indent=2)

    def ajouter_listener(self, callback_async):
        self.__config_listeners.append(callback_async)

    def retirer_listener(self, callback_async):
        try:
            self.__config_listeners.remove(callback_async)
        except ValueError:
            pass

    def etat(self):
        pass

    async def entretien(self):
        if self.__validateur_certificats is not None:
            await self.__validateur_certificats.entretien()

        maitredescles_expire = [v.fingerprint for v in self.__certificats_maitredescles.values() if v.cache_expire()]
        for fingerprint in maitredescles_expire:
            del self.__certificats_maitredescles[fingerprint]

    def set_docker_present(self, etat: bool):
        self.__docker_present = etat

    def get_csr_genere(self):
        if self.__csr_genere is None:
            self.__csr_genere = CleCsrGenere.build(self.instance_id)
        return self.__csr_genere

    def clear_csr_genere(self):
        self.__csr_genere = None

    def ajouter_certificat_maitredescles(self, certificat: EnveloppeCertificat):
        fingerprint = certificat.fingerprint
        try:
            env_cache = self.__certificats_maitredescles[fingerprint]
            # Touch certificat existant
            env_cache.touch()
        except KeyError:
            # Conserver certificat
            env_cache = CacheCertificat(certificat)
            self.__certificats_maitredescles[fingerprint] = env_cache

    @property
    def stop_event(self):
        return self.__stop_event

    @property
    def docker_present(self):
        return self.__docker_present

    def set_docker_actif(self, etat: bool):
        self.__docker_actif = etat

    @property
    def docker_actif(self):
        return self.__docker_actif

    @property
    def instance_id(self):
        return self.__instance_id

    @property
    def niveau_securite(self):
        return self.__niveau_securite

    @property
    def idmg(self):
        return self.__idmg

    @property
    def certissuer_url(self):
        return self.__configuration.certissuer_url

    @property
    def nom_domaine(self):
        return self.__hostname

    @property
    def configuration(self):
        return self.__configuration

    @property
    def clecertificat(self):
        return self.__clecertificat

    @property
    def certificat_millegrille(self):
        return self.__certificat_millegrille

    @property
    def ip_address(self):
        return self.__ip_address

    @property
    def hostname(self):
        return self.__hostname

    @property
    def mq_hostname(self):
        return self.__host_mq or self.__hostname

    @property
    def mq_port(self):
        return self.__port_mq

    @property
    def formatteur_message(self):
        return self.__formatteur_message

    def set_redemarrer(self, redemarrer):
        self.__redemarrer = redemarrer

    def set_entretien_nginx(self, entretien_nginx):
        self.__entretien_nginx = entretien_nginx

    @property
    def client_session(self):
        return self.__client_session

    @property
    def entretien_nginx(self):
        return self.__entretien_nginx

    @property
    def redemarrer(self):
        return self.__redemarrer

    @property
    def validateur_certificats(self):
        return self.__validateur_certificats

    @property
    def validateur_message(self):
        return self.__validateur_message

    def doit_activer_443(self):
        """
        :return: True si le WebServer doit ouvrir le port 443 (en plus du port 2443)
        """
        if self.__certificat_millegrille is None:
            return True
        if self.__docker_present is False:
            return True

        return False

    def set_stop_event(self, stop_event: Event):
        self.__stop_event = stop_event

    async def stop(self):
        if self.__stop_event is not None:
            self.__stop_event.set()
        else:
            raise Exception("Stop event non disponible")

    async def generer_certificats_module(self, producer: MessageProducerFormatteur, etat_docker, nom_module: str, configuration: dict):
        config = {nom_module: configuration}
        await generer_certificats_modules(producer, self.__client_session, self, config, None)

    async def generer_certificats_module_satellite(self, producer: MessageProducerFormatteur,
                                                   etat_docker, nom_module: str, configuration: dict):
        config = {nom_module: configuration}
        await generer_certificats_modules_satellites(producer, self, etat_docker, config)

    async def generer_passwords(self, etat_docker, passwords: list):
        await generer_passwords(self, etat_docker, passwords)

    async def emettre_presence(self, producer: MessageProducerFormatteur, info: Optional[dict] = None):
        self.__logger.info("Emettre presence")
        if info is not None:
            info_updatee = info.copy()
        else:
            info_updatee = dict()

        info_updatee['hostname'] = self.hostname
        info_updatee['domaine'] = self.hostname
        info_updatee['fqdn_detecte'] = get_hostname(fqdn=True)
        info_updatee['ip_detectee'] = self.ip_address
        info_updatee['instance_id'] = self.instance_id
        info_updatee['securite'] = self.niveau_securite

        # Faire la liste des applications installees
        liste_applications = await self.get_liste_configurations()
        info_updatee['applications_configurees'] = liste_applications

        niveau_securite = self.niveau_securite
        if niveau_securite == Constantes.SECURITE_SECURE:
            # Downgrade 4.secure a niveau 3.protege
            niveau_securite = Constantes.SECURITE_PROTEGE

        await producer.emettre_evenement(info_updatee, Constantes.DOMAINE_INSTANCE,
                                         ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE,
                                         exchanges=niveau_securite)

    async def get_liste_configurations(self) -> list:
        """
        Charge l'information de configuration de toutes les applications connues.
        :return:
        """
        info_configuration = list()
        path_docker_apps = self.configuration.path_docker_apps
        try:
            for fichier_config in listdir(path_docker_apps):
                if not fichier_config.startswith('app.'):
                    continue  # Skip, ce n'est pas une application
                with open(path.join(path_docker_apps, fichier_config), 'rb') as fichier:
                    contenu = json.load(fichier)
                nom = contenu['nom']
                version = contenu['version']
                info_configuration.append({'nom': nom, 'version': version})
        except FileNotFoundError:
            self.__logger.debug("get_liste_configurations Path catalogues docker non trouve")

        return info_configuration

    def maj_clecert(self, clecert: CleCertificat):
        # Installer le certificat d'instance
        cert_pem = '\n'.join(clecert.enveloppe.chaine_pem())
        cle_pem = clecert.private_key_bytes().decode('utf-8')
        configuration = self.configuration
        path_cert = configuration.instance_cert_pem_path
        path_key = configuration.instance_key_pem_path
        with open(path_cert, 'w') as fichier:
            fichier.write(cert_pem)
        with open(path_key, 'w') as fichier:
            fichier.write(cle_pem)

    def set_rotation_maitredescles(self):
        # Conserver delai de 3 heures avant prochaine rotation de certificat de maitre des cles
        self.__attente_rotation_maitredescles = datetime.datetime.utcnow() + datetime.timedelta(hours=3)

    def is_rotation_maitredescles(self):
        if self.__attente_rotation_maitredescles is None:
            return False

        datenow = datetime.datetime.utcnow()
        if datenow > self.__attente_rotation_maitredescles:
            self.__attente_rotation_maitredescles = None
            return False

        return True


def load_fichier_config(path_fichier: str) -> Optional[str]:
    try:
        with open(path_fichier, 'r') as fichier:
            value = fichier.read().strip()
        return value
    except FileNotFoundError:
        return None


def load_clecert(path_cle: str, path_cert: str) -> Optional[CleCertificat]:
    try:
        return CleCertificat.from_files(path_cle, path_cert)
    except FileNotFoundError:
        return None


def load_enveloppe_cert(path_cert: str) -> Optional[EnveloppeCertificat]:
    try:
        return EnveloppeCertificat.from_file(path_cert)
    except FileNotFoundError:
        return None


class CacheCertificat:

    def __init__(self, enveloppe: EnveloppeCertificat):
        self.derniere_reception = datetime.datetime.utcnow()
        self.enveloppe = enveloppe

    @property
    def fingerprint(self) -> str:
        return self.enveloppe.fingerprint

    @property
    def pems(self) -> list:
        return self.enveloppe.chaine_pem()

    def touch(self):
        self.derniere_reception = datetime.datetime.utcnow()

    def cache_expire(self) -> bool:
        date_expiration = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        return self.derniere_reception < date_expiration
