import asyncio
import logging

from asyncio import TaskGroup
from subprocess import CalledProcessError
from typing import Optional

from cryptography.x509 import ExtensionNotFound

from millegrilles_instance.Interfaces import MgbusHandlerInterface
from millegrilles_instance.NginxUtil import publish_to_nginx
from millegrilles_instance.SystemdUtil import reload_nginx, reload_compose_applications, reload_middleware, \
    restart_nginx, restart_compose_applications
from millegrilles_instance.apps.AppManager import AppManager
from millegrilles_instance.apps.Certificates import check_certissuer_available, renew_certificates
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.messages import Constantes
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_messages.messages.EnveloppeCertificat import CertificatExpire
from millegrilles_messages.messages.MessagesModule import MessageWrapper

LOGGER = logging.getLogger(__name__)


class InstanceManager:
    """
    Facade for system handlers. Used by access modules (mq, web).
    """
    def __init__(self, context: InstanceContext, app_manager: AppManager):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__app_manager = app_manager
        self.__mgbus_handler: Optional[MgbusHandlerInterface] = None
        self.__runlevel_changed = asyncio.Event()
        self.__loop = asyncio.get_event_loop()
        self.__reload_configuration = asyncio.Event()
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
        except *Exception:  # Stop on any thread exception
            self.__logger.exception("InstanceManager Unhandled error, closing")

        if self.__context.stopping is False:
            self.__logger.error("InstanceManager stopping without stop flag set - force quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

        self.__logger.debug("InstanceManager thread done")

    async def __change_runlevel(self, level: int):
        self.__context.runlevel = level
        self.__runlevel_changed.set()

    async def __runlevel_thread(self):
        previous_runlevel = InstanceContext.CONST_RUNLEVEL_INIT
        while self.__context.stopping is False:
            self.__runlevel_changed.clear()
            runlevel = self.context.runlevel
            if runlevel != previous_runlevel:
                self.__logger.info("Changing runlevel from %d to %d" % (previous_runlevel, runlevel))

                try:
                    if previous_runlevel == InstanceContext.CONST_RUNLEVEL_NORMAL:
                        await self.__stop_normal_operation()

                    if runlevel == InstanceContext.CONST_RUNLEVEL_EXPIRED:
                        raise Exception("Manager certificate is expired")
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
        self.__loop.call_soon_threadsafe(self.__reload_configuration.set)

    async def __reload_configuration_thread(self):
        while self.context.stopping is False:
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
        # Initial load of the configuration
        try:
            await asyncio.to_thread(self.context.reload)
        except CertificatExpire:
            self.__logger.warning("__prepare_configuration Certificate is expired - context only partially loaded")

    async def __load_application_list(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            raise ValueError(f"Instance at {self.__context.configuration.path_millegrilles} is not configured properly, SECURITE is not set")

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

        if expired:
            raise Exception("Expired manager certificate. Run the Signing CA or Manager certificate creation script.")
        else:
            if securite == Constantes.SECURITE_PUBLIC:
                self.__logger.info("Mode 1.public")
            elif securite == Constantes.SECURITE_PRIVE:
                self.__logger.info("Mode 2.prive")
            elif securite == Constantes.SECURITE_PROTEGE:
                self.__logger.info("Mode 3.protege")
            elif securite == Constantes.SECURITE_SECURE:
                self.__logger.info("Mode 4.secure")
            else:
                raise ValueError('Unsupported security mode: %s' % securite)

            # Change runlevel to local. This will run through the process to make system operational.
            await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_LOCAL)

        pass

    async def __start_runlevel_local(self):
        self.__logger.info("Starting runlevel LOCAL")

        # Try to refresh local certificates when local certissuer is available
        if await asyncio.to_thread(check_certissuer_available, self.context.configuration):
            await renew_certificates(self.context)
            self.context.certificates_generated.set()

        self.__logger.info("Runlevel LOCAL done")
        await self.__change_runlevel(InstanceContext.CONST_RUNLEVEL_NORMAL)

    async def __start_runlevel_normal(self):
        self.__logger.info("Starting runlevel NORMAL")

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
                    # await self.__docker_handler.emettre_presence(timeout=20)  # Wait 20 secs max for connection to mqbus
                    await self.update_fiche_json()
                    break
                except asyncio.TimeoutError:
                    await self.context.wait(5)
        except:
            self.__logger.exception("Error during initial information exchange after connection to mgbus")

        # Refresh certificates using bus (e.g. when local certissuer not available)
        await renew_certificates(self.context)

        # Always release this flag to let Certificate thread proceed
        self.context.certificates_generated.set()

        # Reload all systemd services (force restart if reload fails)
        instance_name = self.context.configuration.instance_name
        if not self.context.configuration.is_secure_manager:
            try:
                await asyncio.to_thread(reload_nginx, instance_name)
            except CalledProcessError:
                # Try restart
                self.__logger.warning("Error during nginx reload, trying nginx restart")
                await asyncio.to_thread(restart_nginx, instance_name)

        reload_middleware(instance_name)
        try:
            reload_compose_applications(instance_name, update_certs=False)
        except CalledProcessError:
            try:
                restart_compose_applications(instance_name)
            except CalledProcessError:
                self.__logger.exception("Error during applications restart - applications will not be available until fixed")

        self.__logger.info("Runlevel normal READY")

    async def __stop_normal_operation(self):
        # Disconnect from mgbus
        await self.__mgbus_handler.unregister()
        self.__logger.info("Stopped runlevel NORMAL")

    async def update_fiche_publique(self, message: MessageWrapper):
        contenu = message.contenu
        path_etc_fiche = self.__context.configuration.path_millegrilles / "etc" / "fiche.json"
        await asyncio.to_thread(publish_to_nginx, self.context.configuration, 'fiche.json', contenu)
        with open(path_etc_fiche, 'wb') as f:
            f.write(contenu)

    async def get_instance_passwords(self, message: MessageWrapper):
        enveloppe = message.certificat
        if enveloppe is None:
            raise ValueError("Certificate has not been initialized")

        try:
            delegation_globale = enveloppe.get_delegation_globale
        except ExtensionNotFound:
            delegation_globale = None

        if delegation_globale != 'proprietaire':
            return {"ok": False, "err": "Access denied"}

        path_secrets = self.__context.configuration.path_millegrilles / "secrets"
        secrets = dict()
        for file in path_secrets.iterdir():
            if file.is_file() and file.name.endswith('.txt'):
                with open(file, 'rt') as fichier:
                    file_content = fichier.read(4096)
                secrets[file.name] = file_content

        # Retourner la reponse chiffree
        producer = await self.__context.get_producer()
        await producer.encrypt_reply(enveloppe, {"secrets": secrets}, message.reply_to, message.correlation_id)

        return None

    async def update_fiche_json(self, retries=3):
        producer = await asyncio.wait_for(self.__context.get_producer(), 3)
        idmg = self.context.idmg
        for i in range(0, retries):
            try:
                fiche_response = await producer.request({'idmg': idmg}, Constantes.DOMAINE_CORE_TOPOLOGIE,
                                                        'ficheMillegrille',
                                                        exchange=Constantes.SECURITE_PUBLIC,
                                                        timeout=5)
                if fiche_response:
                    await self.update_fiche_publique(fiche_response)
                    return
            except asyncio.TimeoutError:
                if i < retries - 1:
                    self.__logger.warning("Timeout requesting ficheMillegrille, retrying ...")
                    await asyncio.sleep(15)
                else:
                    self.__logger.error("Timed out requesting ficheMillegrille, fiche not updated")
                    return
