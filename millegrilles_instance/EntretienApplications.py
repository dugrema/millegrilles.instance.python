import logging
import json

from os import path

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync


class GestionnaireApplications:

    def __init__(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

    async def entretien(self):
        self.__logger.debug("entretien")

    async def installer_application(self, configuration: dict):
        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        nom_application = configuration['nom']
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))

        with open(path_app, 'w') as fichier:
            json.dump(configuration, fichier, indent=2)

        return await self.__etat_docker.installer_application(configuration)

    async def demarrer_application(self, nom_application: str):
        raise NotImplementedError('todo')

    async def arreter_application(self, nom_application: str):
        raise NotImplementedError('todo')

    async def supprimer_application(self, nom_application: str):
        raise NotImplementedError('todo')
