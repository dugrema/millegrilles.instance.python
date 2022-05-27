# Module d'entretien de l'instance protegee
import aiohttp
import asyncio
import base64
import datetime
import json
import logging
import secrets

from os import path, stat
from typing import Optional

from aiohttp import web, ClientSession
from asyncio import Event, TimeoutError

from millegrilles.messages import Constantes
from millegrilles.instance.EtatInstance import EtatInstance
from millegrilles.instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles.messages.CleCertificat import CleCertificat
from millegrilles.certificats.Generes import CleCsrGenere
from millegrilles.instance.EntretienRabbitMq import EntretienRabbitMq

logger = logging.getLogger(__name__)


def get_module_execution(etat_instance: EtatInstance):
    securite = etat_instance.niveau_securite

    if securite == Constantes.SECURITE_PROTEGE:
        return InstanceProtegee()

    return None


CONFIG_MODULES_PROTEGES = [
    # 'docker.certissuer.json',
    # 'docker.acme.json',
    # 'docker.nginx.json',
    'docker.redis.json',
    'docker.mq.json',
    'docker.mongo.json',
    'docker.core.json',
    # 'docker.coupdoeil.json',
]


class InstanceProtegee:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_stop: Optional[Event] = None
        self.__etat_instance: Optional[EtatInstance] = None
        self.__etat_docker: Optional[EtatDockerInstanceSync] = None

        self.__tache_initialisation = TacheEntretien(datetime.timedelta(days=1), self.docker_initialisation)
        self.__tache_certificats = TacheEntretien(datetime.timedelta(minutes=30), self.entretien_certificats)
        self.__tache_passwords = TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords)
        self.__tache_services = TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services)
        self.__tache_mq = TacheEntretien(datetime.timedelta(seconds=30), self.entretien_mq)

        self.__client_session = aiohttp.ClientSession()

        self.__event_entretien: Optional[Event] = None
        self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_rabbitmq: Optional[EntretienRabbitMq] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self.__event_stop = Event()
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

        self.__event_entretien = Event()
        self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_rabbitmq = EntretienRabbitMq(self.__etat_instance)

        # Ajouter listener de changement de configuration. Demarre l'execution des taches d'entretien/installation.
        self.__etat_instance.ajouter_listener(self.declencher_run)

    async def fermer(self):
        self.__event_stop.set()

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        self.__event_setup_initial_certificats.clear()
        self.__event_setup_initial_passwords.clear()
        self.__tache_certificats.reset()
        self.__tache_passwords.reset()

        # Declencher l'entretien
        self.__event_entretien.set()

    async def run(self):
        self.__logger.info("run()")
        while self.__event_stop.is_set() is False:
            self.__logger.debug("run() debut execution cycle")

            await self.__tache_initialisation.run()
            await self.__tache_certificats.run()
            await self.__tache_passwords.run()
            await self.__tache_services.run()
            await self.__tache_mq.run()

            try:
                self.__logger.debug("run() fin execution cycle")
                await asyncio.wait_for(self.__event_entretien.wait(), 30)
                self.__event_entretien.clear()
            except TimeoutError:
                pass
        self.__logger.info("Fin run()")

    async def get_configuration_services(self) -> dict:
        path_configuration = self.__etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, CONFIG_MODULES_PROTEGES)

        # map configuration certificat
        services = dict()
        for c in configurations:
            try:
                nom = c['name']
                services[nom] = c
            except KeyError:
                pass

        return services

    async def get_configuration_certificats(self) -> dict:
        path_configuration = self.__etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, CONFIG_MODULES_PROTEGES)

        # map configuration certificat
        config_certificats = dict()
        for c in configurations:
            try:
                certificat = c['certificat']
                nom = c['name']
                config_certificats[nom] = certificat
            except KeyError:
                pass

        return config_certificats

    async def get_configuration_passwords(self) -> list:
        path_configuration = self.__etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, CONFIG_MODULES_PROTEGES)

        # map configuration certificat
        liste_noms_passwords = list()
        for c in configurations:
            try:
                p = c['passwords']
                liste_noms_passwords.extend(p)
            except KeyError:
                pass

        return liste_noms_passwords

    async def docker_initialisation(self):
        self.__logger.debug("docker_initialisation debut")
        await self.__etat_docker.initialiser_docker()
        self.__logger.debug("docker_initialisation fin")

    async def entretien_certificats(self):
        self.__logger.debug("entretien_certificats debut")
        configuration = await self.get_configuration_certificats()
        await generer_certificats_modules(self.__client_session, self.__etat_instance, self.__etat_docker,
                                          configuration)
        self.__logger.debug("entretien_certificats fin")
        self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self.__etat_instance, self.__etat_docker, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_services(self):
        self.__logger.debug("entretien_services attente certificats et passwords")
        await asyncio.wait_for(self.__event_setup_initial_certificats.wait(), 50)
        await asyncio.wait_for(self.__event_setup_initial_passwords.wait(), 10)
        self.__logger.debug("entretien_services debut")
        services = await self.get_configuration_services()
        await self.__etat_docker.entretien_services(services)
        self.__logger.debug("entretien_services fin")

    async def entretien_mq(self):
        if self.__entretien_rabbitmq:
            await self.__entretien_rabbitmq.entretien()


class TacheEntretien:

    def __init__(self, intervalle: datetime.timedelta, callback):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__intervalle = intervalle
        self.__callback = callback
        self.__dernier_entretien: Optional[datetime.datetime] = None

    def reset(self):
        """
        Force une execution a la prochaine occasion
        :return:
        """
        self.__dernier_entretien = None

    async def run(self):
        if self.__dernier_entretien is None:
            pass
        elif datetime.datetime.utcnow() - self.__intervalle > self.__dernier_entretien:
            pass
        else:
            return

        self.__dernier_entretien = datetime.datetime.utcnow()

        try:
            await self.__callback()
        except:
            self.__logger.exception("Erreur execution tache entretien")


async def charger_configuration_docker(path_configuration: str, fichiers: list) -> list:
    configuration = []
    for filename in fichiers:
        path_fichier = path.join(path_configuration, filename)
        try:
            with open(path_fichier, 'rb') as fichier:
                contenu = json.load(fichier)
            configuration.append(contenu)
        except FileNotFoundError:
            logger.error("Fichier de module manquant : %s" % path_fichier)

    return configuration


async def generer_certificats_modules(client_session: ClientSession, etat_instance: EtatInstance,
                                      etat_docker: EtatDockerInstanceSync, configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_certificat = 'pki.%s.cert' % nom_module
        nom_cle = 'pki.%s.cle' % nom_module
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)
        combiner_keycert = value.get('combiner_keycert') or False

        sauvegarder = False
        try:
            clecertificat = CleCertificat.from_files(path_cle, path_certificat)
            enveloppe = clecertificat.enveloppe

            # Ok, verifier si le certificat doit etre renouvele
            detail_expiration = enveloppe.calculer_expiration()
            if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
                sauvegarder = True

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_module)
            clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
            sauvegarder = True

        # Verifier si le certificat et la cle sont stocke dans docker
        if sauvegarder is True:

            cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
            with open(path_cle, 'wb') as fichier:
                fichier.write(clecertificat.private_key_bytes())
                if combiner_keycert is True:
                    fichier.write(cert_str.encode('utf-8'))
            with open(path_certificat, 'w') as fichier:
                cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
                fichier.write(cert_str)

        await etat_docker.assurer_clecertificat(nom_module, clecertificat, combiner_keycert)


async def generer_nouveau_certificat(client_session: ClientSession, etat_instance: EtatInstance, nom_module: str,
                                     configuration: dict) -> CleCertificat:
    instance_id = etat_instance.instance_id
    idmg = etat_instance.certificat_millegrille.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = etat_instance.nom_domaine
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = etat_instance.formatteur_message
    message_signe, _uuid = formatteur_message.signer_message(configuration)

    logger.debug("Demande de signature de certificat pour %s => %s\n%s" % (nom_module, message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    async with client_session.post(path_csr, json=message_signe) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    logger.debug("Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
    return clecertificat


async def generer_passwords(etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync,
                            liste_noms_passwords: list):
    """
    Generer les passwords manquants.
    :param etat_instance:
    :param etat_docker:
    :param liste_noms_passwords:
    :return:
    """
    path_secrets = etat_instance.configuration.path_secrets
    configurations = await etat_docker.get_configurations_datees()
    secrets_dict = configurations['secrets']

    for nom_password in liste_noms_passwords:
        prefixe = 'passwd.%s' % nom_password
        path_password = path.join(path_secrets, prefixe + '.txt')

        try:
            with open(path_password, 'r') as fichier:
                password = fichier.read().strip()
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime
        except FileNotFoundError:
            # Fichier non trouve, on doit le creer
            password = base64.b64encode(secrets.token_bytes(24)).decode('utf-8').replace('=', '')
            with open(path_password, 'w') as fichier:
                fichier.write(password)
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime

        logger.debug("Date password : %s" % date_password)
        date_password = datetime.datetime.utcfromtimestamp(date_password)
        date_password_str = date_password.strftime('%Y%m%d%H%M%S')

        label_passord = '%s.%s' % (prefixe, date_password_str)
        try:
            secrets_dict[label_passord]
            continue  # Mot de passe existe
        except KeyError:
            pass  # Le mot de passe n'existe pas

        # Ajouter mot de passe
        await etat_docker.ajouter_password(nom_password, date_password_str, password)
