import asyncio

from millegrilles.docker.DockerHandler import DockerHandler
from millegrilles.docker.DockerCommandes import CommandeGetConfiguration
from millegrilles.instance import Constantes
from millegrilles.instance.EtatInstance import EtatInstance


class EtatDockerInstanceSync:

    def __init__(self, etat_instance: EtatInstance, docker_handler: DockerHandler):
        self.__etat_instance = etat_instance
        self.__docker_handler = docker_handler  # DockerHandler

    async def entretien(self):
        await self.verifier_config_instance()
        await self.verifier_date_certificats()
        await asyncio.sleep(60)

    async def verifier_date_certificats(self):
        pass

    async def verifier_config_instance(self):
        instance_id = self.__etat_instance.instance_id
        if instance_id is not None:
            # S'assurer d'avoir une config instance.instance_id
            commande_instanceid = CommandeGetConfiguration(Constantes.CONFIG_INSTANCE_ID, aio=True)
            self.__docker_handler.ajouter_commande(commande_instanceid)
            config = await commande_instanceid.get_config()


