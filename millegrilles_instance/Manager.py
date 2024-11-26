import asyncio
import logging
import threading
import pathlib

from asyncio import TaskGroup
from os import path, makedirs
from typing import Optional
from uuid import uuid4

from millegrilles_instance import ModulesRequisInstance
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance.MaintenanceApplicationService import charger_configuration_docker, \
    charger_configuration_application
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.docker.DockerCommandes import CommandeListerServices
from millegrilles_messages.messages import Constantes
from millegrilles_instance.Certificats import GenerateurCertificatsHandler, preparer_certificats_web
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.MaintenanceApplications import ApplicationsHandler
from millegrilles_messages.messages.Constantes import SECURITE_SECURE

LOGGER = logging.getLogger(__name__)

CONST_RUNLEVEL_INIT = 0         # Nothing finished loading yet
CONST_RUNLEVEL_INSTALLING = 1   # No configuration (idmg, securite), waiting for admin
CONST_RUNLEVEL_EXPIRED = 2      # Instance certificate is expired, auto-renewal not possible
CONST_RUNLEVEL_NORMAL = 3       # Everything is ok, do checkup and then run until stopped


class InstanceManager:
    """
    Facade for system handlers. Used by access modules (mq, web).
    """

    def __init__(self, context: InstanceContext, generateur_certificats: GenerateurCertificatsHandler,
                 docker_handler: Optional[InstanceDockerHandler], gestionnaire_applications: Optional[ApplicationsHandler]):

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__generateur_certificats = generateur_certificats
        self.__docker_handler = docker_handler
        self.__gestionnaire_applications = gestionnaire_applications

        self.__reload_configuration = threading.Event()

        self.__runlevel = CONST_RUNLEVEL_INIT
        self.__runlevel_changed = asyncio.Event()

    @property
    def context(self) -> InstanceContext:
        return self.__context

    async def setup(self):
        """
        Call this before starting run threads.
        """
        await self.__prepare_configuration()

    async def run(self):
        async with TaskGroup() as group:
            group.create_task(self.__stop_thread())
            group.create_task(self.__reload_configuration_thread())
            group.create_task(self.__runlevel_thread())

        if self.__context.stopping is False:
            self.__logger.error("InstanceManager stopping without stop flag set - force quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

        self.__logger.info("run() stopping")

    async def __change_runlevel(self, level: int):
        self.__runlevel = level
        self.__runlevel_changed.set()

    async def __runlevel_thread(self):
        previous_runlevel = CONST_RUNLEVEL_INIT
        while self.__context.stopping is False:
            self.__runlevel_changed.clear()
            runlevel = self.__runlevel
            if runlevel != previous_runlevel:
                self.__logger.info("Changing runlevel from %d to %d" % (previous_runlevel, self.__runlevel))

                try:
                    if previous_runlevel == CONST_RUNLEVEL_NORMAL:
                        await self.stop_normal_operation()

                    if runlevel == CONST_RUNLEVEL_EXPIRED:
                        await self.__start_runlevel_expired()
                    elif runlevel == CONST_RUNLEVEL_INSTALLING:
                        await self.__start_runlevel_installation()
                    elif runlevel == CONST_RUNLEVEL_NORMAL:
                        await self.__start_runlevel_normal()
                except:
                    self.__logger.exception("Error during runlevel change - quitting")
                    self.__context.stop()

                # Wait for next change
                previous_runlevel = runlevel

            await self.__runlevel_changed.wait()

    def callback_changement_configuration(self):
        self.__reload_configuration.set()

    async def __reload_configuration_thread(self):
        while self.context.stopping is False:
            await asyncio.to_thread(self.__reload_configuration.wait)
            if self.context.stopping:
                return  # Exit condition
            self.__reload_configuration.clear()

            # Note: this may change the runlevel
            try:
                await self.__load_application_list()
            except:
                self.__logger.exception("Error loading application list - quitting")
                self.context.stop()

    async def __stop_thread(self):
        await self.context.wait()
        # Release threads
        self.__reload_configuration.set()
        self.__runlevel_changed.set()

    async def __prepare_configuration(self):
        """
        Initial preparation of folders and files for a new system. Idempotent.
        Reloads the context configuration.
        """
        configuration: ConfigurationInstance = self.__context.configuration
        self.__logger.info("Prepare folders and files under %s" % configuration.path_millegrilles)
        await asyncio.to_thread(makedirs, configuration.path_secrets, 0o700, exist_ok=True)
        await asyncio.to_thread(makedirs, configuration.path_secrets_partages, 0o700, exist_ok=True)
        await self.__prepare_folder_configuration()
        await self.__prepare_self_signed_web_certificates()

        # Initial load of the configuration
        await asyncio.to_thread(self.context.reload)

    # async def __preparer_environnement(self):
    #     """
    #     Examine environnement, preparer au besoin (folders, docker, ports, etc)
    #     :return:
    #     """
    #     self.__logger.info("Preparer l'environnement")
    #
    #     makedirs(self.__configuration.path_secrets, 0o700, exist_ok=True)
    #     makedirs(self.__configuration.path_secrets_partages, 0o710, exist_ok=True)
    #
    #     self.preparer_folder_configuration()
    #     await self.__etat_instance.reload_configuration()  # Genere les certificats sur premier acces
    #
    #     self.__etat_instance.ajouter_listener(self.changer_etat_execution)
    #
    #     self.__etat_instance.generateur_certificats = GenerateurCertificatsHandler(self.__etat_instance)
    #
    #     self.__web_server = WebServer(self.__etat_instance)
    #     self.__web_server.setup()
    #
    #     await self.demarrer_client_docker()  # Demarre si docker est actif
    #
    #     await self.__etat_instance.reload_configuration()

    async def __prepare_folder_configuration(self):
        configuration: ConfigurationInstance = self.__context.configuration
        await asyncio.to_thread(makedirs, configuration.path_configuration, 0o700, exist_ok=True)

        # Verifier si on a les fichiers de base (instance_id.txt)
        path_instance_txt = path.join(configuration.path_configuration, 'instance_id.txt')
        if path.exists(path_instance_txt) is False:
            uuid_instance = str(uuid4())
            with open(path_instance_txt, 'w') as fichier:
                fichier.write(uuid_instance)

    async def __prepare_self_signed_web_certificates(self):
        configuration: ConfigurationInstance = self.__context.configuration
        await asyncio.to_thread(preparer_certificats_web, str(configuration.path_secrets))

    async def __load_application_list(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            securite = None  # System not initialized

        try:
            clecert = self.__context.signing_key
            expiration = clecert.enveloppe.calculer_expiration()
            expired = expiration is None or expiration.get('expire') is True
        except AttributeError:
            expired = None  # No valid certificate

        docker_present = self.__docker_handler is not None
        current_runlevel = self.__runlevel

        if securite is None:
            if docker_present:
                self.__logger.info("Installation mode with docker")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_INSTALLATION
                await self.__change_runlevel(CONST_RUNLEVEL_INSTALLING)
            else:
                self.__logger.info("Installation mode without docker")
                raise NotImplementedError('Installation mode without docker not supported')
        elif expired:
            if docker_present:
                self.__logger.info("Recovery mode with docker")
                if securite in [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_SECURE]:
                    self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_SECURE_EXPIRE
                else:
                    self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_CERTIFICAT_EXPIRE
                await self.__change_runlevel(CONST_RUNLEVEL_EXPIRED)
            else:
                self.__logger.info("Recovery mode without docker")
                raise NotImplementedError('Recovery mode without docker not supported')
        elif docker_present is False:
            # No docker, just plain application mode
            self.__logger.info("Applications without docker mode")
            raise NotImplementedError('Applications without docker not supported')
        else:
            # Normal operation mode with docker
            if securite == Constantes.SECURITE_PUBLIC:
                self.__logger.info("Docker mode 1.public")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_PUBLICS
            elif securite == Constantes.SECURITE_PRIVE:
                self.__logger.info("Docker mode 2.prive")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_PRIVES
            elif securite == Constantes.SECURITE_PROTEGE:
                self.__logger.info("Docker mode 3.protege")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_PROTEGES
            elif securite == Constantes.SECURITE_SECURE:
                self.__logger.info("Docker mode 4.secure")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_SECURES
            else:
                raise ValueError('Unsupported security mode: %s' % securite)

            # Change runlevel to normal. This will run through the process to make system operational.
            await self.__change_runlevel(CONST_RUNLEVEL_NORMAL)

        if current_runlevel != CONST_RUNLEVEL_INIT:
            # Trigger application maintenance
            await self.__docker_handler.callback_changement_applications()

        pass

    async def __start_runlevel_installation(self):
        await self.__docker_handler.callback_changement_applications()

    async def __start_runlevel_expired(self):
        raise NotImplementedError('todo')

    async def __start_runlevel_normal(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            self.__logger.error("Security level not available, downgrading to installation mode")
            await self.__change_runlevel(CONST_RUNLEVEL_INSTALLING)
            return

        # 1. Cleanup from installation
        await self.__docker_handler.nginx_installation_cleanup()

        # 2. Renew certificates locally with certissuer
        try:
            await self.__generateur_certificats.entretien_certificat_instance()
            await self.__generateur_certificats.entretien_modules()
            await self.context.wait(2)
        except:
            self.__logger.exception("Error maintaining certificates - quitting")
            self.context.stop()

        # 3. Ensure middleware is running (nginx, mq, mongo, redis, midcompte)
        await self.__docker_handler.callback_changement_applications()
        await wait_for_application(self.__context, 'nginx')  # Always first application to start up
        if securite == Constantes.SECURITE_PROTEGE:
            # Check that MQ and midcompte are running. Mongo is optional but is done before midcompte when required.
            await wait_for_application(self.__context, 'mq')
            await wait_for_application(self.__context, 'midcompte')

        # 4. Connect to mgbus (MQ)
        raise NotImplementedError('todo')  # TODO - trouver comment appeler MgbusHandler.register()

    async def stop_normal_operation(self):
        # Disconnect from mgbus
        raise NotImplementedError('todo')  # TODO - trouver comment appeler MgbusHandler.unregister()


async def wait_for_application(context: InstanceContext, app_name: str):
    while True:
        app = context.application_status.apps.get(app_name)
        try:
            if app['running'] is True:
                break
        except (TypeError, KeyError):
            pass
        LOGGER.info("Waiting for application %s" % app_name)
        await context.wait(7)
        if context.stopping:
            raise ForceTerminateExecution()
