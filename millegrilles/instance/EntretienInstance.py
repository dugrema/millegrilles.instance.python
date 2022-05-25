# Module d'entretien de l'instance protegee
import aiohttp
import asyncio
import datetime
import json
import logging

from os import path
from typing import Optional

from aiohttp import web, ClientSession
from asyncio import Event, TimeoutError

from millegrilles.messages import Constantes
from millegrilles.instance.EtatInstance import EtatInstance
from millegrilles.instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles.messages.CleCertificat import CleCertificat
from millegrilles.certificats.Generes import CleCsrGenere

logger = logging.getLogger(__name__)


def get_module_execution(etat_instance: EtatInstance):
    securite = etat_instance.niveau_securite

    if securite == Constantes.SECURITE_PROTEGE:
        return InstanceProtegee()

    return None


CONFIG_MODULES_PROTEGES = [
    'docker.certissuer.json',
    'docker.acme.json',
    'docker.nginx.json',
    'docker.redis.json',
    'docker.mq.json',
    'docker.mongo.json',
    'docker.core.json',
    'docker.coupdoeil.json',
]


class InstanceProtegee:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_stop: Optional[Event] = None
        self.__etat_instance: Optional[EtatInstance] = None
        self.__etat_docker: Optional[EtatDockerInstanceSync] = None

        self.__tache_certificats = TacheEntretien(datetime.timedelta(minutes=30), self.entretien_certificats)

        self.__client_session = aiohttp.ClientSession()

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self.__event_stop = Event()
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

    async def fermer(self):
        self.__event_stop.set()

    async def run(self):
        self.__logger.info("run()")
        while self.__event_stop.is_set() is False:
            self.__logger.debug("run() debut execution cycle")

            await self.__tache_certificats.run()

            try:
                self.__logger.debug("run() fin execution cycle")
                await asyncio.wait_for(self.__event_stop.wait(), 30)
            except TimeoutError:
                pass
        self.__logger.info("Fin run()")

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

    async def entretien_certificats(self):
        self.__logger.debug("entretien_certificats debut")
        configuration = await self.get_configuration_certificats()
        await generer_certificats_modules(self.__client_session, self.__etat_instance, self.__etat_docker, configuration)
        self.__logger.debug("entretien_certificats fin")


class TacheEntretien:

    def __init__(self, intervalle: datetime.timedelta, callback):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__intervalle = intervalle
        self.__callback = callback
        self.__dernier_entretien: Optional[datetime.datetime] = None

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


async def generer_certificats_modules(client_session: ClientSession, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync,
                                      configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_certificat = 'pki.%s.cert' % nom_module
        nom_cle = 'pki.%s.cle' % nom_module
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)

        try:
            clecertificat = CleCertificat.from_files(path_cle, path_certificat)
            enveloppe = clecertificat.enveloppe

            # Ok, verifier si le certificat doit etre renouvele
            detail_expiration = enveloppe.calculer_expiration()
            if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_module)
            clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)

        # Verifier si le certificat et la cle sont stocke dans docker


async def generer_nouveau_certificat(client_session: ClientSession, etat_instance: EtatInstance, nom_module: str, configuration: dict):
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

    # Signer avec notre certificat (instance), requis par le certissuer
    configuration['csr'] = csr_str

    logger.debug("Demande de signature de certificat pour %s => %s\n%s" % (nom_module, configuration, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    async with client_session.post(path_csr, json=configuration) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    certificat = reponse['certificat']

    logger.debug("Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
