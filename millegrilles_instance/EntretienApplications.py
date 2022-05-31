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
        self.__rabbitmq_dao = None

    def set_rabbitmq_dao(self, rabbitmq_dao):
        self.__rabbitmq_dao = rabbitmq_dao

    async def entretien(self):
        self.__logger.debug("entretien")

    async def installer_application(self, configuration: dict, reinstaller=False):
        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        nom_application = configuration['nom']
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))

        with open(path_app, 'w') as fichier:
            json.dump(configuration, fichier, indent=2)

        resultat = await self.__etat_docker.installer_application(configuration, reinstaller)

        producer = self.__rabbitmq_dao.get_producer()
        await self.__etat_docker.emettre_presence(producer)

        return resultat

    async def demarrer_application(self, nom_application: str):
        resultat = await self.__etat_docker.demarrer_application(nom_application)

        producer = self.__rabbitmq_dao.get_producer()
        await self.__etat_docker.emettre_presence(producer)

        return resultat

    async def arreter_application(self, nom_application: str):
        resultat = await self.__etat_docker.arreter_application(nom_application)

        producer = self.__rabbitmq_dao.get_producer()
        await self.__etat_docker.emettre_presence(producer)

        return resultat

    async def supprimer_application(self, nom_application: str):
        resultat = await self.__etat_docker.supprimer_application(nom_application)
        producer = self.__rabbitmq_dao.get_producer()
        await self.__etat_docker.emettre_presence(producer)
        return resultat

    # async def get_liste_configurations(self) -> list:
    #     """
    #     Charge l'information de configuration de toutes les applications connues.
    #     :return:
    #     """
    #     info_configuration = list()
    #     path_docker_apps = self.__etat_instance.configuration.path_docker_apps
    #     for fichier_config in listdir(path_docker_apps):
    #         if not fichier_config.startswith('app.'):
    #             continue  # Skip, ce n'est pas une application
    #         with open(path.join(path_docker_apps, fichier_config), 'rb') as fichier:
    #             contenu = json.load(fichier)
    #         nom = contenu['nom']
    #         version = contenu['version']
    #         info_configuration.append({'nom': nom, 'version': version})
    #
    #     return info_configuration
