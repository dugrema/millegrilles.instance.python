import asyncio
import logging

from asyncio import TaskGroup
from os import path, makedirs
from typing import Optional
from uuid import uuid4

from millegrilles_instance.Certificats import GenerateurCertificatsHandler, preparer_certificats_web
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.docker.DockerHandler import DockerHandler


class InstanceManager:
    """
    Facade for system handlers. Used by access modules (mq, web).
    """

    def __init__(self, context: InstanceContext, generateur_certificats: GenerateurCertificatsHandler, docker_handler: Optional[DockerHandler]):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__generateur_certificats = generateur_certificats
        self.__docker_handler = docker_handler

    @property
    def context(self) -> InstanceContext:
        return self.__context

    async def setup(self):
        await self.__prepare_configuration()

    async def run(self):
        async with TaskGroup() as group:
            group.create_task(self.__stop_thread())

        if self.__context.stopping is False:
            self.__logger.error("InstanceManager stopping without stop flag set - force quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

        self.__logger.info("run() stopping")

    async def __stop_thread(self):
        await self.context.wait()

    async def __prepare_configuration(self):
        """
        Initial preparation of folders and files for a new system. Idempotent.
        Reloads the context configuration.
        """
        configuration: ConfigurationInstance = self.__context.configuration
        self.__logger.info("Prepare folders and files under %s" % configuration.path_millegrilles)
        await asyncio.to_thread(makedirs, configuration.path_secrets, 0o700, exist_ok=True)
        await asyncio.to_thread(makedirs, configuration.path_secrets_partages, 0o700, exist_ok=True)
        await self.preparer_folder_configuration()
        await self.preparer_certificats()

        # Initial load of the configuration
        await asyncio.to_thread(self.context.reload)

    # async def __preparer_environnement(self):
    #     """
    #     Examine environnement, preparer au besoin (folders, docker, ports, etc)
    #     :return:
    #     """
    #     self.__logger.info("Preparer l'environnement")
    #
    #     makedirs(self.__configuration.path_secrets, 0o700, exist_ok=True)
    #     makedirs(self.__configuration.path_secrets_partages, 0o710, exist_ok=True)
    #
    #     self.preparer_folder_configuration()
    #     await self.__etat_instance.reload_configuration()  # Genere les certificats sur premier acces
    #
    #     self.__etat_instance.ajouter_listener(self.changer_etat_execution)
    #
    #     self.__etat_instance.generateur_certificats = GenerateurCertificatsHandler(self.__etat_instance)
    #
    #     self.__web_server = WebServer(self.__etat_instance)
    #     self.__web_server.setup()
    #
    #     await self.demarrer_client_docker()  # Demarre si docker est actif
    #
    #     await self.__etat_instance.reload_configuration()

    async def preparer_folder_configuration(self):
        configuration: ConfigurationInstance = self.__context.configuration
        await asyncio.to_thread(makedirs, configuration.path_configuration, 0o700, exist_ok=True)

        # Verifier si on a les fichiers de base (instance_id.txt)
        path_instance_txt = path.join(configuration.path_configuration, 'instance_id.txt')
        if path.exists(path_instance_txt) is False:
            uuid_instance = str(uuid4())
            with open(path_instance_txt, 'w') as fichier:
                fichier.write(uuid_instance)

    async def preparer_certificats(self):
        configuration: ConfigurationInstance = self.__context.configuration
        await asyncio.to_thread(preparer_certificats_web, str(configuration.path_secrets))
