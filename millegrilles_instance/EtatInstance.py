import logging

from asyncio import Event
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_instance.Certificats import preparer_certificats_web
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_messages.IpUtils import get_ip, get_hostname
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.FormatteurMessages import SignateurTransactionSimple, FormatteurMessageMilleGrilles


class EtatInstance:

    def __init__(self, configuration: ConfigurationInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration

        self.__ip_address: Optional[str] = None
        self.__hostname: Optional[str] = None
        self.__instance_id: Optional[str] = None
        self.__niveau_securite: Optional[str] = None
        self.__idmg: Optional[str] = None
        self.__certificat_millegrille: Optional[EnveloppeCertificat] = None
        self.__clecertificat: Optional[CleCertificat] = None
        self.__nom_domaine: Optional[str] = None
        self.__password_mq: Optional[str] = None

        self.__docker_present = False
        self.__docker_actif = False

        # Liste de listeners qui sont appeles sur changement de configuration
        self.__config_listeners = list()
        self.__formatteur_message: Optional[FormatteurMessageMilleGrilles] = None

        self.__stop_event: Optional[Event] = None
        self.__redemarrer = False

    async def reload_configuration(self):
        self.__logger.info("Reload configuration sur disque ou dans docker")

        self.__ip_address = get_ip()
        self.__hostname = get_hostname(fqdn=True)

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

        self.__nom_domaine = 'mg-dev5.maple.maceroc.com'
        self.__logger.debug("Nom domaine insance: %s" % self.__nom_domaine)

        if self.__clecertificat is not None:
            signateur = SignateurTransactionSimple(self.__clecertificat)
            self.__formatteur_message = FormatteurMessageMilleGrilles(self.__idmg, signateur)

        for listener in self.__config_listeners:
            await listener(self)

    def ajouter_listener(self, callback_async):
        self.__config_listeners.append(callback_async)

    def retirer_listener(self, callback_async):
        self.__config_listeners.remove(callback_async)

    def etat(self):
        pass

    def set_docker_present(self, etat: bool):
        self.__docker_present = etat

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
        return self.__nom_domaine

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
        if self.__niveau_securite == Constantes.SECURITE_PROTEGE:
            return self.__hostname
        else:
            raise NotImplementedError('todo')

    @property
    def formatteur_message(self):
        return self.__formatteur_message

    def set_redemarrer(self, redemarrer):
        self.__redemarrer = redemarrer

    @property
    def redemarrer(self):
        return self.__redemarrer

    def set_stop_event(self, stop_event: Event):
        self.__stop_event = stop_event

    async def stop(self):
        if self.__stop_event is not None:
            self.__stop_event.set()
        else:
            raise Exception("Stop event non disponible")


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
