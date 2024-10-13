import asyncio
import datetime
import logging
import json
import os
import pathlib

from os import path

from typing import Optional

from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur, MessageWrapper
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.Exceptions import InstallationModeException
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.Configuration import sauvegarder_configuration_webapps

LOGGER = logging.getLogger(__name__)


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

    async def installer_application(self, configuration: dict, reinstaller=False, command: Optional[MessageWrapper] = None):
        nom_application = configuration['nom']
        web_links = configuration.get('web')
        if web_links:
            sauvegarder_configuration_webapps(nom_application, web_links, self.__etat_instance)

        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
        with open(path_app, 'w') as fichier:
            json.dump(configuration, fichier, indent=2)

        if command:
            # Emit OK response, installation is beginning
            producer = await self.__etat_instance.get_producer(timeout=5)
            await producer.repondre({"ok": True}, command.reply_to, command.correlation_id)

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

        path_conf_applications = pathlib.Path(
            self.__etat_instance.configuration.path_configuration,
            ConstantesInstance.CONFIG_NOMFICHIER_CONFIGURATION_WEB_APPLICATIONS)

        try:
            with open(path_conf_applications, 'rt+') as fichier:
                config_apps_json = json.load(fichier)
                webapp_config = config_apps_json[nom_application]
                del config_apps_json[nom_application]
                fichier.seek(0)
                json.dump(config_apps_json, fichier)
                fichier.truncate()

                # webapp_config['']
                # path_webapps = pathlib.Path(self.__etat_instance.configuration.path_nginx, 'html/applications')
                # path_app = pathlib.Path(path_webapps, nom_application)
                # shutil_rmtree()

        except (KeyError, FileNotFoundError):
            pass  # App or configuration file was already deleted

        nginx_restart = False
        # Charger configuration application
        try:
            path_docker_apps = self.__etat_instance.configuration.path_docker_apps
            path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
            self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
            with open(path_app, 'rt') as fichier:
                app_config = json.load(fichier)
        except FileNotFoundError:
            pass  # Fichier supprime, OK
        else:
            # Supprimer fichiers nginx au besoin
            try:
                nginx_conf = app_config['nginx']['conf']
                path_nginx_modules = pathlib.Path(self.__etat_instance.configuration.path_nginx, 'modules')
                for nginx_file in nginx_conf.keys():
                    self.__logger.info("Delete nginx file %s" % nginx_file)
                    path_nginx_file = pathlib.Path(path_nginx_modules, nginx_file)
                    try:
                        path_nginx_file.unlink()
                        nginx_restart = True
                    except FileNotFoundError:
                        pass  # OK
            except KeyError:
                pass

        if self.__etat_docker is not None:
            resultat = await self.__etat_docker.supprimer_application(nom_application)
            await self.__etat_docker.emettre_presence(producer)
            reponse = resultat
        else:
            path_docker_apps = self.__etat_instance.configuration.path_docker_apps
            path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
            self.__logger.debug("Supprimer configuration pour app %s vers %s" % (nom_application, path_app))
            os.unlink(path_app)
            await self.__etat_instance.emettre_presence(producer)
            reponse = {'ok': True}

        if nginx_restart:
            self.__logger.warning("Restarting nginx after removing %s" % nom_application)
            await self.__etat_docker.redemarrer_nginx()

        return reponse

    async def get_producer(self, timeout=5):
        if self.__etat_instance.niveau_securite is None:
            raise InstallationModeException('Installation mode')

        if self.__rabbitmq_dao is None:
            raise Exception('producer non disponible (rabbitmq non initialie)')
        producer = self.__rabbitmq_dao.get_producer()

        date_debut = datetime.datetime.utcnow()
        intervalle = datetime.timedelta(seconds=timeout)
        while producer is None:
            await asyncio.sleep(0.5)
            if datetime.datetime.utcnow() - intervalle > date_debut:
                raise Exception('producer non disponible (aucune connection)')
            producer = self.__rabbitmq_dao.get_producer()

        pret = producer.producer_pret()
        if pret.is_set() is False:
            try:
                await asyncio.wait_for(pret.wait(), timeout)
            except asyncio.TimeoutError:
                raise Exception('producer non disponible (timeout sur pret)')

        return producer


async def installer_application_sansdocker(etat_instance: EtatInstance, producer: MessageProducerFormatteur, configuration: dict):
    """ Installe un certificat d'application sur une instance sans docker (e.g. RPi) """
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
                LOGGER.info("generer_valeurs Generer certificat/secret pour %s" % nom_application)
                clecertificat = await etat_instance.generateur_certificats.demander_signature(
                    nom_application, certificat)
                if clecertificat is None:
                    raise Exception("generer_valeurs Erreur creation certificat %s" % nom_application)

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
