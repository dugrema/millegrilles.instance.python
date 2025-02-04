import asyncio
import json
import logging
import lzma
import pathlib

from asyncio import TaskGroup
from os import path, makedirs
from typing import Optional
from uuid import uuid4

from cryptography.x509 import ExtensionNotFound
from docker.errors import APIError

from millegrilles_instance import ModulesRequisInstance
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance.Interfaces import MgbusHandlerInterface
from millegrilles_instance.MaintenanceApplicationService import ServiceStatus
from millegrilles_instance.NginxHandler import NginxHandler
from millegrilles_instance.millegrilles_acme.AcmeClient import AcmeHandler
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.messages import Constantes
from millegrilles_instance.Certificats import GenerateurCertificatsHandler, preparer_certificats_web
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.MaintenanceApplications import ApplicationsHandler
from millegrilles_messages.messages.EnveloppeCertificat import CertificatExpire
from millegrilles_messages.messages.MessagesModule import MessageWrapper

LOGGER = logging.getLogger(__name__)


class InstanceManager:
    """
    Facade for system handlers. Used by access modules (mq, web).
    """

    def __init__(self, context: InstanceContext, generateur_certificats: GenerateurCertificatsHandler,
                 docker_handler: Optional[InstanceDockerHandler], gestionnaire_applications: ApplicationsHandler,
                 nginx_handler: NginxHandler, acme_handler: Optional[AcmeHandler]):

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__generateur_certificats = generateur_certificats
        self.__docker_handler = docker_handler
        self.__gestionnaire_applications = gestionnaire_applications
        self.__mgbus_handler: Optional[MgbusHandlerInterface] = None
        self.__nginx_handler: NginxHandler = nginx_handler
        self.__acme_handler: Optional[AcmeHandler] = acme_handler

        # self.__reload_configuration = threading.Event()

        # self.__runlevel = CONST_RUNLEVEL_INIT
        self.__runlevel_changed = asyncio.Event()

        self.__loop = asyncio.get_event_loop()
        self.__reload_configuration = asyncio.Event()

    @property
    def context(self) -> InstanceContext:
        return self.__context

    async def setup(self, mgbus_handler: MgbusHandlerInterface):
        """
        Call this before starting run threads.
        """
        self.__mgbus_handler = mgbus_handler
        await self.__prepare_configuration()

    async def run(self):
        self.__logger.debug("InstanceManager thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__reload_configuration_thread())
                group.create_task(self.__runlevel_thread())
                group.create_task(self.__entretien_inital_attente_thread())
        except *Exception:  # Stop on any thread exception
            self.__logger.exception("InstanceManager Unhandled error, closing")

        if self.__context.stopping is False:
            self.__logger.error("InstanceManager stopping without stop flag set - force quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

        self.__logger.debug("InstanceManager thread done")

    async def __change_runlevel(self, level: int):
        self.__context.runlevel = level
        # self.__runlevel = level
        self.__runlevel_changed.set()

    async def __runlevel_thread(self):
        previous_runlevel = InstanceContext.CONST_RUNLEVEL_INIT
        while self.__context.stopping is False:
            self.__runlevel_changed.clear()
            runlevel = self.context.runlevel
            if runlevel != previous_runlevel:
                self.__logger.info("Changing runlevel from %d to %d" % (previous_runlevel, runlevel))

                try:
                    if previous_runlevel == InstanceContext.CONST_RUNLEVEL_INSTALLING:
                        await self.__stop_runlevel_installation()
                    elif previous_runlevel == InstanceContext.CONST_RUNLEVEL_NORMAL:
                        await self.__stop_normal_operation()

                    if runlevel == InstanceContext.CONST_RUNLEVEL_EXPIRED:
                        await self.__start_runlevel_expired()
                    elif runlevel == InstanceContext.CONST_RUNLEVEL_INSTALLING:
                        await self.__start_runlevel_installation()
                    elif runlevel == InstanceContext.CONST_RUNLEVEL_LOCAL:
                        await self.__start_runlevel_local()
                    elif runlevel == InstanceContext.CONST_RUNLEVEL_NORMAL:
                        await self.__start_runlevel_normal()
                except (asyncio.CancelledError, ForceTerminateExecution) as e:
                    raise e
                except:
                    self.__logger.exception("Error during runlevel change - quitting")
                    self.__context.stop()

                # Wait for next change
                previous_runlevel = runlevel

            await self.__runlevel_changed.wait()

    def callback_changement_configuration(self):
        # self.__reload_configuration.set()
        self.__loop.call_soon_threadsafe(self.__reload_configuration.set)

    async def __entretien_inital_attente_thread(self):
        await self.__generateur_certificats.event_entretien_initial.wait()
        # Initial maintenance done
        self.__context.initial_application_configuration_update.set()
        self.__logger.debug("__entretien_inital_attente_thread DONE")

    async def __reload_configuration_thread(self):
        while self.context.stopping is False:
            # await asyncio.to_thread(self.__reload_configuration.wait)
            await self.__reload_configuration.wait()
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
        try:
            await asyncio.to_thread(self.context.reload)
        except CertificatExpire:
            self.__logger.warning("__prepare_configuration Certificate is expired - context only partially loaded")

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
            if securite:
                # System is set-up but no certificate was loaded - it is expired/invalid
                expired = True
            else:
                expired = None  # No valid certificate

        docker_present = self.__docker_handler is not None
        current_runlevel = self.context.runlevel

        disabled_file = pathlib.Path(self.context.configuration.path_configuration, 'disabled_modules.json')
        try:
            with open(disabled_file, 'rt') as fp:
                file_content = json.load(fp)
            disabled_modules = file_content['disabled']
            self.__logger.info("Disabling required modules: %s", disabled_modules)
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            disabled_modules = list()

        if securite is None:
            if docker_present:
                self.__logger.info("Installation mode with docker")
                self.__context.application_status.required_modules = ModulesRequisInstance.CONFIG_MODULES_INSTALLATION
                await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_INSTALLING)
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
                await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_EXPIRED)
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

            # Change runlevel to local. This will run through the process to make system operational.
            await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_LOCAL)

        for disabled_module in disabled_modules:
            self.__context.application_status.required_modules.modules.remove(disabled_module)

        if current_runlevel != InstanceContext.CONST_RUNLEVEL_INIT:
            # Trigger application maintenance
            await self.__gestionnaire_applications.callback_changement_applications()

        pass

    async def __start_runlevel_installation(self):
        self.__logger.info("Starting runlevel INSTALLATION")

        # Read current application status
        try:
            await self.__gestionnaire_applications.update_application_status()
        except APIError as e:
            if e.status_code == 503:
                # Not a swarm manager, nothing is installed yet
                await self.__docker_handler.initialiser_docker()
                await self.__gestionnaire_applications.update_application_status()
            else:
                raise e

        # Release configuration/app update threads
        self.__docker_handler.callback_changement_configuration()
        self.__context.initial_application_configuration_update.set()
        await self.__gestionnaire_applications.callback_changement_applications()

        await wait_for_application(self.__context, 'nginxinstall')
        await wait_for_application(self.__context, 'coupdoeil2')
        self.__logger.info("Ready to install\nGo to https://%s or https://%s using a web browser to begin." % (self.__context.hostname, self.__context.ip_address))

    async def __stop_runlevel_installation(self):
        # Installation just completed, reload all configuration
        await self.__context.delay_reload(0)  # Reload without waiting
        self.__logger.info("Stopped runlevel INSTALLATION")

    async def __start_runlevel_expired(self):
        self.__logger.info("Starting runlevel EXPIRED")

        # Read current application status
        await self.__gestionnaire_applications.update_application_status()

        # self.__context.initial_application_configuration_update.set()  # Release app update thread
        await self.__gestionnaire_applications.callback_changement_applications()
        # await wait_for_application(self.__context, 'nginx')
        self.__logger.info("Ready for recovery\nGo to https://%s or https://%s using a web browser to begin." % (self.__context.hostname, self.__context.ip_address))

    async def __start_runlevel_local(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            self.__logger.error("Security level not available, downgrading to installation mode")
            await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_INSTALLING)
            return

        self.__logger.info("Starting runlevel LOCAL")

        # Read current application status
        await self.__gestionnaire_applications.update_application_status()

        # 1. Nginx Cleanup from installation
        await self.__docker_handler.nginx_installation_cleanup()
        await asyncio.to_thread(self.__nginx_handler.generer_configuration_nginx)
        await self.__nginx_handler.refresh_configuration(
            "Switching to runlevel %d" % InstanceContext.CONST_RUNLEVEL_LOCAL)

        if securite in [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_SECURE]:
            # Renew certificates locally with certissuer
            try:
                await self.__generateur_certificats.entretien_certificat_instance()
                await self.__generateur_certificats.entretien_modules()
                await self.context.wait(2)
            except:
                self.__logger.exception("Error maintaining certificates - quitting")
                self.context.stop()

        if securite == Constantes.SECURITE_SECURE:
            # Ensure that the remote mq host is available
            while self.context.configuration.mq_hostname == 'localhost':
                # We don't have a confgured server yet, wait
                await self.__reload_configuration.wait()

        self.__logger.info("Runlevel LOCAL done")
        await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_NORMAL)

    async def __start_runlevel_normal(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            self.__logger.error("Security level not available, downgrading to installation mode")
            await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_INSTALLING)
            return

        self.__logger.info("Starting runlevel NORMAL")

        if securite == Constantes.SECURITE_PROTEGE:
            # Ensure middleware is running (nginx, mq, mongo, redis, midcompte)
            await self.__gestionnaire_applications.callback_changement_applications()

            # Note - only wait on the 3.protege instance because it is the one with the bus. This avoids connection errors.
            # All other server instances should connect as soons as possible.
            # Check that MQ and midcompte are running. Mongo is optional but is done before midcompte when required.
            await wait_for_application(self.__context, 'nginx')
            await wait_for_application(self.__context, 'mq')
            await wait_for_application(self.__context, 'midcompte')

            # Restart nginx to ensure configuration is ready for creating bus account
            await self.__docker_handler.redemarrer_nginx('Midcompte ready - ensure configuration is updated')
            await self.__context.wait(3)

        # Connect to mgbus (MQ)
        if self.__context.validateur_message is None:
            self.__logger.info("Runlevel normal - reload configuration")
            await self.__context.reload_wait()
            if self.__context.validateur_message is None:
                self.__logger.error("Error initializing context - stopping")
                self.__context.stop()
                raise ForceTerminateExecution()

        self.__logger.info("Runlevel normal - register on mgbus")
        await self.__mgbus_handler.register()

        # 5. Exchange updated information
        try:
            self.__logger.info("Runlevel normal - exchange information")
            for i in range(0, 3):
                try:
                    await self.__docker_handler.emettre_presence(timeout=20)  # Wait 20 secs max for connection to mqbus
                    await self.request_fiche_json()
                    if securite == Constantes.SECURITE_PROTEGE:
                        await self.send_application_packages()
                    break
                except asyncio.TimeoutError:
                    await self.context.wait(5)
        except:
            self.__logger.exception("Error during initial information exchange after connection to mgbus")

        self.__logger.info("Runlevel normal READY")

    async def __stop_normal_operation(self):
        # Disconnect from mgbus
        await self.__mgbus_handler.unregister()
        self.__logger.info("Stopped runlevel NORMAL")

    async def update_fiche_publique(self, message: MessageWrapper):
        contenu = message.contenu
        await asyncio.to_thread(self.__nginx_handler.sauvegarder_fichier_data, 'fiche.json', contenu, True)

    async def send_application_packages(self):
        self.__logger.info("Transmettre catalogues")
        path_catalogues = self.context.configuration.path_catalogues
        producer = await asyncio.wait_for(self.__context.get_producer(), 3)
        for f in path_catalogues.iterdir():
            if f.is_file() and f.name.endswith('.json.xz'):
                with lzma.open(f, 'rt') as fichier:
                    app_transaction = json.load(fichier)
                commande = {"catalogue": app_transaction}
                await producer.command(commande,
                                       domain=Constantes.DOMAINE_CORE_CATALOGUES,
                                       action='catalogueApplication',
                                       exchange=Constantes.SECURITE_PROTEGE,
                                       nowait=True)

        return {'ok': True}

    async def get_instance_passwords(self, message: MessageWrapper):
        enveloppe = message.certificat

        try:
            delegation_globale = enveloppe.get_delegation_globale
        except ExtensionNotFound:
            delegation_globale = None

        if delegation_globale != 'proprietaire':
            return {"ok": False, "err": "Access denied"}

        path_secrets = pathlib.Path(self.__context.configuration.path_secrets)
        secrets = dict()
        for file in path_secrets.iterdir():
            if file.is_file() and file.name.startswith('passwd'):
                with open(file, 'rt') as fichier:
                    file_content = fichier.read(10240)
                secrets[file.name] = file_content

        # Retourner la reponse chiffree
        producer = await self.__context.get_producer()
        await producer.encrypt_reply(enveloppe, {"secrets": secrets}, message.reply_to, message.correlation_id)

        return None

    async def request_fiche_json(self):
        producer = await asyncio.wait_for(self.__context.get_producer(), 3)
        idmg = self.context.idmg
        fiche_response = await producer.request({'idmg': idmg}, Constantes.DOMAINE_CORE_TOPOLOGIE,
                                                'ficheMillegrille',
                                                exchange=Constantes.SECURITE_PUBLIC)
        contenu = fiche_response.contenu
        await asyncio.to_thread(self.__nginx_handler.sauvegarder_fichier_data, 'fiche.json', contenu, True)

    async def install_application(self, message: MessageWrapper):
        configuration = message.parsed['configuration']
        app_status = ServiceStatus(configuration)
        return await self.__gestionnaire_applications.installer_application(app_status, command=message)

    async def upgrade_application(self, message: MessageWrapper):
        configuration = message.parsed['configuration']
        return await self.__gestionnaire_applications.upgrade_application(configuration, command=message)

    async def remove_application(self, message: MessageWrapper):
        nom_application = message.parsed['nom_application']
        return await self.__gestionnaire_applications.supprimer_application(nom_application)

    async def start_application(self, message: MessageWrapper):
        nom_application = message.parsed['nom_application']
        return await self.__gestionnaire_applications.demarrer_application(nom_application)

    async def stop_application(self, message: MessageWrapper):
        nom_application = message.parsed['nom_application']
        return await self.__gestionnaire_applications.arreter_application(nom_application)

    async def get_acme_configuration(self) -> Optional[dict]:
        try:
            response = self.__acme_handler.get_configuration()
            response['ok'] = True
            return response
        except AttributeError:
            # No handler
            return {'ok': False, 'err': 'Acme disabled'}

    async def update_acme_configuration(self, message: MessageWrapper) -> dict:
        try:
            config = message.parsed
            await self.__acme_handler.update_configuration(config)
            return {'ok': True}
        except AttributeError:
            return {'ok': False, 'err': 'Acme disabled'}

    async def issue_acme_certificate(self, message: MessageWrapper):
        try:
            config = message.parsed
            await self.__acme_handler.update_configuration(config)
        except AttributeError:
            return {'ok': False, 'err': 'Acme disabled'}
        try:
            await self.__acme_handler.issue_certificate()
            # Trigger installation on new certificate
            await self.__docker_handler.verifier_certificat_web()
            await self.__generateur_certificats.entretien_modules()
            return {'ok': True}
        except Exception as e:
            self.__logger.exception("Error issuing ACME certificate")
            return {'ok': False, 'err': str(e)}


async def wait_for_application(context: InstanceContext, app_name: str):
    while context.stopping is False:
        app = context.application_status.apps.get(app_name)
        try:
            if app['status']['running'] is True:
                break
            elif app['status']['disabled'] is True:
                break  # Not applicable
        except (TypeError, KeyError):
            pass
        LOGGER.info("Waiting for application %s" % app_name)
        await context.wait(5)
