# Module d'entretien de l'instance protegee
import asyncio
import datetime
import json
import logging

from os import path
from typing import Optional

from asyncio import Event, TimeoutError

from millegrilles.messages import Constantes
from millegrilles.instance.EtatInstance import EtatInstance
from millegrilles.instance.InstanceDocker import EtatDockerInstanceSync

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
        await generer_certificats_modules(self.__etat_instance, self.__etat_docker, configuration)
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


async def generer_certificats_modules(etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync,
                                      configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for key, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % key)
