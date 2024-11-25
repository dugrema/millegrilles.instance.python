import asyncio
import datetime
import logging
import json
import os
import pathlib

from os import path

from typing import Optional

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.MaintenanceApplicationService import list_images, pull_images
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur, MessageWrapper
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.Exceptions import InstallationModeException
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance import Constantes as ConstantesInstance
# from millegrilles_instance.Configuration import sauvegarder_configuration_webapps

LOGGER = logging.getLogger(__name__)


class ApplicationsHandler:

    def __init__(self, context: InstanceContext, docker_handler: Optional[InstanceDockerHandler]):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__docker_handler = docker_handler

    async def installer_application(self, app_configuration: dict, reinstaller=False, command: Optional[MessageWrapper] = None):
        nom_application = app_configuration['nom']
        web_links = app_configuration.get('web')
        if web_links:
            raise NotImplementedError('todo')
            #sauvegarder_configuration_webapps(nom_application, web_links, self.__context)

        path_docker_apps = self.__context.configuration.path_docker_apps
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
        with open(path_app, 'w') as fichier:
            json.dump(app_configuration, fichier, indent=2)

        producer = await self.__context.get_producer()
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.installer_application(self.__context, app_configuration, reinstaller)
            if command:
                # Emit OK response, installation is beginning
                await producer.reply(resultat, command.reply_to, command.correlation_id)
            raise NotImplementedError('todo')
            #await self.__docker_handler.emettre_presence(producer)
            #return resultat
        else:
            resultat = await installer_application_sansdocker(self.__context, app_configuration)
            raise NotImplementedError('todo')
            #await self.__context.emettre_presence(producer)
            #return resultat

    async def upgrade_application(self, configuration: dict, command: Optional[MessageWrapper] = None):
        nom_application = configuration['nom']
        web_links = configuration.get('web')

        # Downloader toutes les images a l'avance
        images = list_images(configuration)
        all_found = await pull_images(self.__context, self.__docker_handler, images, nom_application)

        # if command:
        #     # Emettre reponse OK, upgrade commence
        #     producer = await self.__etat_instance.get_producer(timeout=5)
        #     await producer.repondre({"ok": all_found}, command.reply_to, command.correlation_id)

        if all_found is False:
            return {"ok": False, "err": "Some images missing: %s" % images}

        if web_links:
            raise NotImplementedError('todo')
            # sauvegarder_configuration_webapps(nom_application, web_links, self.__context)

        path_docker_apps = self.__context.configuration.path_docker_apps
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
        with open(path_app, 'w') as fichier:
            json.dump(configuration, fichier, indent=2)

        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.installer_application(self.__context, configuration, True)
            raise NotImplementedError('todo')
            # await self.__docker_handler.emettre_presence(producer)
            # return resultat
        else:
            resultat = await installer_application_sansdocker(self.__context, configuration)
            raise NotImplementedError('todo')
            #await self.__context.emettre_presence(producer)
            #return resultat

    async def demarrer_application(self, nom_application: str):
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.demarrer_application(nom_application)

            raise NotImplementedError('todo')
            #await self.__docker_handler.emettre_presence(producer)
            #return resultat
        else:
            return {'ok': False, 'err': 'Non supporte'}

    async def arreter_application(self, nom_application: str):
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.arreter_application(nom_application)

            #await self.__docker_handler.emettre_presence(producer)
            #return resultat
        else:
            return {'ok': False, 'err': 'Non supporte'}

    async def supprimer_application(self, nom_application: str):
        path_conf_applications = pathlib.Path(
            self.__context.configuration.path_configuration,
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
            path_docker_apps = self.__context.configuration.path_docker_apps
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
                path_nginx_modules = pathlib.Path(self.__context.configuration.path_nginx, 'modules')
                for nginx_file in nginx_conf.keys():
                    self.__logger.info("Delete nginx file %s" % nginx_file)
                    path_nginx_file = pathlib.Path(path_nginx_modules, nginx_file)
                    try:
                        path_nginx_file.unlink()
                        nginx_restart = True
                    except FileNotFoundError:
                        pass  # OK
            except (TypeError,KeyError):
                pass

        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.supprimer_application(nom_application)
            raise NotImplementedError('todo')
            #await self.__docker_handler.emettre_presence(producer)
            #reponse = resultat
        else:
            path_docker_apps = self.__context.configuration.path_docker_apps
            path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
            self.__logger.debug("Supprimer configuration pour app %s vers %s" % (nom_application, path_app))
            os.unlink(path_app)
            raise NotImplementedError('todo')
            #await self.__context.emettre_presence(producer)
            #reponse = {'ok': True}

        #if nginx_restart:
        #    self.__logger.warning("Restarting nginx after removing %s" % nom_application)
        #    await self.__etat_docker.redemarrer_nginx("Application %s retiree" % nom_application)

        return reponse

    # async def get_producer(self, timeout=5):
    #     if self.__context.securite is None:
    #         raise InstallationModeException('Installation mode')
    #
    #     if self.__rabbitmq_dao is None:
    #         raise Exception('producer non disponible (rabbitmq non initialie)')
    #     producer = self.__rabbitmq_dao.get_producer()
    #
    #     date_debut = datetime.datetime.utcnow()
    #     intervalle = datetime.timedelta(seconds=timeout)
    #     while producer is None:
    #         await asyncio.sleep(0.5)
    #         if datetime.datetime.utcnow() - intervalle > date_debut:
    #             raise Exception('producer non disponible (aucune connection)')
    #         producer = self.__rabbitmq_dao.get_producer()
    #
    #     pret = producer.producer_pret()
    #     if pret.is_set() is False:
    #         try:
    #             await asyncio.wait_for(pret.wait(), timeout)
    #         except asyncio.TimeoutError:
    #             raise Exception('producer non disponible (timeout sur pret)')
    #
    #     return producer


async def installer_application_sansdocker(context: InstanceContext, configuration: dict):
    """ Installe un certificat d'application sur une instance sans docker (e.g. RPi) """
    nom_application = configuration['nom']
    dependances = configuration['dependances']
    path_secrets = context.configuration.path_secrets

    # Generer certificats/passwords
    for dep in dependances:
        try:
            certificat = dep['certificat']

            # Verifier si certificat/cle existent deja
            path_cert = path.join(path_secrets, 'pki.%s.cert' % nom_application)
            path_cle = path.join(path_secrets, 'pki.%s.cle' % nom_application)
            if path.exists(path_cert) is False or path.exists(path_cle) is False:
                LOGGER.info("generer_valeurs Generer certificat/secret pour %s" % nom_application)
                clecertificat = await context.generateur_certificats.demander_signature(
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
                    await context.generer_passwords(None, [passwd_gen])

        except KeyError:
            pass

    return {'ok': True}
