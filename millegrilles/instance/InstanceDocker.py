import asyncio
import logging

from asyncio import Event, TimeoutError
from docker.errors import NotFound

from millegrilles.docker.DockerHandler import DockerHandler
from millegrilles.docker.DockerCommandes import CommandeAjouterConfiguration, CommandeGetConfiguration
from millegrilles.instance import Constantes
from millegrilles.instance.EtatInstance import EtatInstance


class EtatDockerInstanceSync:

    def __init__(self, etat_instance: EtatInstance, docker_handler: DockerHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__docker_handler = docker_handler  # DockerHandler

    async def entretien(self, stop_event: Event):
        while stop_event.is_set() is False:
            self.__logger.debug("Debut Entretien EtatDockerInstanceSync")
            await self.verifier_config_instance()
            await self.verifier_date_certificats()
            self.__logger.debug("Fin Entretien EtatDockerInstanceSync")

            try:
                await asyncio.wait_for(stop_event.wait(), 60)
            except TimeoutError:
                pass

        self.__logger.info("Thread Entretien InstanceDocker terminee")

    async def verifier_date_certificats(self):
        pass

    async def verifier_config_instance(self):
        instance_id = self.__etat_instance.instance_id
        if instance_id is not None:
            # S'assurer d'avoir une config instance.instance_id
            commande_instanceid = CommandeGetConfiguration(Constantes.DOCKER_CONFIG_INSTANCE_ID, aio=True)
            self.__docker_handler.ajouter_commande(commande_instanceid)
            try:
                docker_instance_id = await commande_instanceid.get_data()
                self.__logger.debug("Docker instance_id : %s", docker_instance_id)
                if docker_instance_id != instance_id:
                    raise Exception("Erreur configuration, instance_id mismatch")
            except NotFound:
                self.__logger.debug("Docker instance NotFound")
                commande_ajouter = CommandeAjouterConfiguration(Constantes.DOCKER_CONFIG_INSTANCE_ID, instance_id, aio=True)
                self.__docker_handler.ajouter_commande(commande_ajouter)
                await commande_ajouter.attendre()
