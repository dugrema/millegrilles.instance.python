import asyncio
import datetime
import logging
import json
import os

from os import path

import pytz

from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync


class GestionnaireApplications:

    def __init__(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker
        self.__rabbitmq_dao = None

        # Initialiser le prochain backup
        self.__prochain_backup_applications = datetime.datetime.now(tz=pytz.UTC) + datetime.timedelta(seconds=30)
        self.__intervalle_backup_applications = datetime.timedelta(days=1)  # Intervalle backup suivants

    def set_rabbitmq_dao(self, rabbitmq_dao):
        self.__rabbitmq_dao = rabbitmq_dao

    async def entretien(self):
        self.__logger.debug("entretien")
        date_courante = datetime.datetime.now(tz=pytz.UTC)
        if self.__prochain_backup_applications < date_courante:
            try:
                await self.backup_applications()
            finally:
                self.__prochain_backup_applications = datetime.datetime.now(tz=pytz.UTC) + self.__intervalle_backup_applications

    async def installer_application(self, configuration: dict, reinstaller=False):
        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        nom_application = configuration['nom']
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))

        with open(path_app, 'w') as fichier:
            json.dump(configuration, fichier, indent=2)

        producer = self.__rabbitmq_dao.get_producer()
        if self.__etat_docker is not None:
            resultat = await self.__etat_docker.installer_application(producer, configuration, reinstaller)
            await self.__etat_docker.emettre_presence(producer)
            return resultat
        else:
            resultat = await installer_application_sansdocker(self.__etat_instance, producer, configuration)
            await self.__etat_instance.emettre_presence(producer)
            return resultat

    async def demarrer_application(self, nom_application: str):
        if self.__etat_docker is not None:
            resultat = await self.__etat_docker.demarrer_application(nom_application)

            producer = self.__rabbitmq_dao.get_producer()
            await self.__etat_docker.emettre_presence(producer)

            return resultat
        else:
            return {'ok': False, 'err': 'Non supporte'}

    async def arreter_application(self, nom_application: str):
        if self.__etat_docker is not None:
            resultat = await self.__etat_docker.arreter_application(nom_application)

            producer = self.__rabbitmq_dao.get_producer()
            await self.__etat_docker.emettre_presence(producer)

            return resultat
        else:
            return {'ok': False, 'err': 'Non supporte'}

    async def supprimer_application(self, nom_application: str):
        producer = self.__rabbitmq_dao.get_producer()
        if self.__etat_docker is not None:
            resultat = await self.__etat_docker.supprimer_application(nom_application)
            await self.__etat_docker.emettre_presence(producer)
            return resultat
        else:
            path_docker_apps = self.__etat_instance.configuration.path_docker_apps
            path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
            self.__logger.debug("Supprimer configuration pour app %s vers %s" % (nom_application, path_app))
            os.unlink(path_app)
            await self.__etat_instance.emettre_presence(producer)
            return {'ok': True}

    async def backup_applications(self):
        if self.__etat_docker is not None:
            await self.__etat_docker.backup_applications()

    async def get_producer(self, timeout=5):
        if self.__rabbitmq_dao is None:
            return
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            return None
        pret = producer.producer_pret()
        if pret.is_set() is False:
            try:
                await asyncio.wait_for(pret.wait(), timeout)
            except asyncio.TimeoutError:
                return None
        return producer

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


async def installer_application_sansdocker(etat_instance: EtatInstance, producer: MessageProducerFormatteur, configuration: dict):
    nom_application = configuration['nom']
    dependances = configuration['dependances']
    path_secrets = etat_instance.configuration.path_secrets

    # Generer certificats/passwords
    for dep in dependances:
        try:
            certificat = dep['certificat']

            # Verifier si certificat/cle existent deja
            path_cert = path.join(path_secrets, 'pki.%s.cert' % nom_application)
            path_cle = path.join(path_secrets, 'pki.%s.cle' % nom_application)
            if path.exists(path_cert) is False or path.exists(path_cle) is False:
                await etat_instance.generer_certificats_module_satellite(producer, None, nom_application, certificat)

        except KeyError:
            pass

        try:
            generateur = dep['generateur']
            for passwd_gen in generateur:
                if isinstance(passwd_gen, str):
                    label = passwd_gen
                else:
                    label = passwd_gen['label']

                path_password = path.join(path_secrets, 'passwd.%s.txt' % label)
                if path.exists(path_password) is False:
                    await etat_instance.generer_passwords(None, [passwd_gen])

        except KeyError:
            pass

    return {'ok': True}
