# Gestion des configs/secrets de l'instance dans docker
from docker import DockerClient

from millegrilles.instance.DockerHandler import DockerHandler
from millegrilles.instance.EtatInstance import EtatInstance


class EtatDockerInstanceSync:

    def __init__(self, etat_instance: EtatInstance, docker: DockerHandler):
        self.__etat_instance = etat_instance
        self.__docker = docker

    async def entretien(self):
        pass

    async def verifier_date_certificats(self):
        pass

    async def verifier_config_instance(self):
        pass
