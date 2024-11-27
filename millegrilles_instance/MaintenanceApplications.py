import asyncio
import logging
import json
import os
import pathlib

from asyncio import TaskGroup
from os import path
from typing import Optional

from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.MaintenanceApplicationService import list_images, pull_images, get_service_status, \
    download_docker_images, ServiceInstallCommand, ServiceStatus
from millegrilles_instance.MaintenanceApplicationWeb import sauvegarder_configuration_webapps
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.messages.MessagesModule import MessageWrapper
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance import Constantes as ConstantesInstance

LOGGER = logging.getLogger(__name__)


class ApplicationsHandler:

    def __init__(self, context: InstanceContext, docker_handler: Optional[InstanceDockerHandler]):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context: InstanceContext = context
        self.__docker_handler = docker_handler

        self.__applications_changed = asyncio.Event()

    async def run(self):
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__application_maintenance_thread())
                group.create_task(self.__application_restart_thread())
        except *Exception as e:
            if self.__context.stopping:
                self.__logger.info('Exception on close %s' % str(e))
            else:
                self.__logger.exception("Unhandled exception - quitting")
                self.__context.stop()
                raise ForceTerminateExecution()

    async def __stop_thread(self):
        await self.__context.wait()

    async def installer_application(self, app_configuration: ServiceStatus, reinstaller=False, command: Optional[MessageWrapper] = None):
        nom_application = app_configuration.name
        self.__logger.info("Installing application %s" % nom_application)
        web_links = app_configuration.web_config
        if web_links:
            sauvegarder_configuration_webapps(self.__context, nom_application, web_links)

        path_docker_apps = self.__context.configuration.path_docker_apps
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
        with open(path_app, 'w') as fichier:
            json.dump(app_configuration.to_dict(), fichier, indent=2)

        producer = await self.__context.get_producer()
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.installer_application(app_configuration, reinstaller)
            if command:
                # Emit OK response, installation is beginning
                await producer.reply(resultat, command.reply_to, command.correlation_id)
            await self.__docker_handler.emettre_presence()
            self.__logger.info("Application %s installed" % nom_application)
            return resultat
        else:
            resultat = await installer_application_sansdocker(self.__context, app_configuration)
            self.__logger.info("Application %s installed" % nom_application)
            return resultat

    async def upgrade_application(self, app_value: dict, command: Optional[MessageWrapper] = None):
        app_status = ServiceStatus(app_value)
        nom_application = app_status.name
        web_links = app_status.web_config

        # Downloader toutes les images a l'avance
        images = list_images(app_status)
        all_found = await pull_images(self.__context, self.__docker_handler, images, nom_application)

        if all_found is False:
            return {"ok": False, "err": "Some images missing: %s" % images}

        if web_links:
            sauvegarder_configuration_webapps(self.__context, nom_application, web_links)

        path_docker_apps = self.__context.configuration.path_docker_apps
        path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        self.__logger.debug("Sauvegarder configuration pour app %s vers %s" % (nom_application, path_app))
        with open(path_app, 'w') as fichier:
            json.dump(app_status.to_dict(), fichier, indent=2)

        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.installer_application(app_status, True)
            await self.__docker_handler.emettre_presence()
            return resultat
        else:
            return await installer_application_sansdocker(self.__context, app_status)

    async def demarrer_application(self, nom_application: str):
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.demarrer_application(nom_application)
            await self.__docker_handler.emettre_presence()
            return resultat
        else:
            return {'ok': False, 'err': 'Non supporte'}

    async def arreter_application(self, nom_application: str):
        if self.__docker_handler is not None:
            resultat = await self.__docker_handler.arreter_application(nom_application)
            await self.__docker_handler.emettre_presence()
            return resultat
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
            await self.__docker_handler.emettre_presence()
            reponse = resultat
        else:
            path_docker_apps = self.__context.configuration.path_docker_apps
            path_app = path.join(path_docker_apps, 'app.%s.json' % nom_application)
            self.__logger.debug("Supprimer configuration pour app %s vers %s" % (nom_application, path_app))
            os.unlink(path_app)
            reponse = {'ok': True}

        if nginx_restart:
           self.__logger.warning("Restarting nginx after removing %s" % nom_application)
           await self.__docker_handler.redemarrer_nginx("Application %s retiree" % nom_application)

        return reponse

    async def __run_application_maintenance(self):
        # Configure and install missing services
        missing_services = await get_service_status(self.__context, self.__docker_handler, missing_only=True)
        if len(missing_services) > 0:
            LOGGER.info("Install %d missing or stopped services" % len(missing_services))
            LOGGER.debug("Missing services\n%s" % missing_services)

            restart_services_queue = asyncio.Queue()
            missing_services_queue = asyncio.Queue()
            download_done_queue = asyncio.Queue()

            # Run download, configure and install in parallel. If install fails, download keeps going.
            try:
                async with TaskGroup() as group:
                    group.create_task(download_docker_images(self.__context, self.__docker_handler, missing_services_queue, download_done_queue))
                    group.create_task(self.__restart_service_process(restart_services_queue))
                    group.create_task(self.__install_service_process(download_done_queue))

                    # Fill the missing services queue to start processing
                    for s in missing_services:
                        if s.installed:
                            # Restart only
                            await restart_services_queue.put(s)
                        else:
                            await missing_services_queue.put(s)

                    # Done, stop all processing
                    await restart_services_queue.put(None)
                    await missing_services_queue.put(None)

            except *Exception as e:  # Fail immediately on first exception
                raise e

            # Emit updated system status
            try:
                await self.__docker_handler.emettre_presence()
            except ValueNotAvailable:
                pass   # System not initialized (e.g. installation mode)

            LOGGER.debug("Install missing or stopped services DONE")

        pass

    async def __restart_service_process(self, input_q: asyncio.Queue[Optional[ServiceStatus]]):
        while True:
            service_status = await input_q.get()
            if service_status is None:
                return  # Exit condition
            await self.__docker_handler.demarrer_application(service_status.name)
        pass

    async def __install_service_process(self, input_q: asyncio.Queue[Optional[ServiceInstallCommand]]):
        while True:
            command = await input_q.get()
            if command is None:
                return  # Exit condition
            # app_name = command.status.name
            # app_configuration = {'nom': app_name, 'dependances': [command.status.configuration]}
            self.__logger.info("Installing application %s" % command.status.name)
            await self.__docker_handler.installer_application(command.status)
        pass

    async def callback_changement_applications(self):
        self.__applications_changed.set()

    async def __application_restart_thread(self):
        """
        Monitors stopped applications to trigger a restart
        """
        while self.__context.stopping is False:
            for app_name, value in self.__context.application_status.apps.items():
                try:
                    status = value['status']
                except KeyError:
                    pass
                else:
                    if status.get('disabled') is False and status.get('running') is False:
                        self.__logger.info("Restarting stopped services")
                        self.__applications_changed.set()  # Trigger application maintenance cycle
                        break

            await self.__context.wait(5)

    async def __application_maintenance_thread(self):
        while self.__context.stopping is False:
            try:
                await asyncio.wait_for(self.__applications_changed.wait(), 900)
            except asyncio.TimeoutError:
                pass

            if self.__context.stopping:
                return  # Stopping

            self.__logger.debug("__application_maintenance Debut Entretien")
            self.__applications_changed.clear()
            try:
                await self.__run_application_maintenance()
            except asyncio.CancelledError as e:
                raise e
            except:
                self.__logger.exception("__application_maintenance Error during maintenance")
            self.__logger.debug("Fin Entretien EtatDockerInstanceSync")

        self.__logger.info("__application_maintenance Thread terminee")


async def installer_application_sansdocker(context: InstanceContext, configuration: ServiceStatus):
    raise NotImplementedError('fix me')
    # """ Installe un certificat d'application sur une instance sans docker (e.g. RPi) """
    # nom_application = configuration['nom']
    # dependances = configuration['dependances']
    # path_secrets = context.configuration.path_secrets
    #
    # # Generer certificats/passwords
    # for dep in dependances:
    #     try:
    #         certificat = dep['certificat']
    #
    #         # Verifier si certificat/cle existent deja
    #         path_cert = path.join(path_secrets, 'pki.%s.cert' % nom_application)
    #         path_cle = path.join(path_secrets, 'pki.%s.key' % nom_application)
    #         if path.exists(path_cert) is False or path.exists(path_cle) is False:
    #             LOGGER.info("generer_valeurs Generer certificat/secret pour %s" % nom_application)
    #             clecertificat = await context.generateur_certificats.demander_signature(
    #                 nom_application, certificat)
    #             if clecertificat is None:
    #                 raise Exception("generer_valeurs Erreur creation certificat %s" % nom_application)
    #
    #     except KeyError:
    #         pass
    #
    #     try:
    #         generateur = dep['generateur']
    #         for passwd_gen in generateur:
    #             if isinstance(passwd_gen, str):
    #                 label = passwd_gen
    #             else:
    #                 label = passwd_gen['label']
    #
    #             path_password = path.join(path_secrets, 'passwd.%s.txt' % label)
    #             if path.exists(path_password) is False:
    #                 await context.generer_passwords(None, [passwd_gen])
    #
    #     except KeyError:
    #         pass
    #
    # return {'ok': True}
