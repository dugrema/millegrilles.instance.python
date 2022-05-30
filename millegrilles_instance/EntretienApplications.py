import logging

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync


class GestionnaireApplications:

    def __init__(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

    async def entretien(self):
        self.__logger.debug("entretien")

    async def installer_application(self):
        raise NotImplementedError('todo')

    async def demarrer_application(self):
        raise NotImplementedError('todo')

    async def arreter_application(self):
        raise NotImplementedError('todo')

    async def supprimer_application(self):
        raise NotImplementedError('todo')
