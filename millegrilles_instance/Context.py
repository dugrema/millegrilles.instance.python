import aiohttp
import asyncio
import logging

from asyncio import TaskGroup

from typing import Optional, Callable

from millegrilles_messages.messages import Constantes
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Interfaces import DockerHandlerInterface
from millegrilles_instance.Structs import ApplicationInstallationStatus
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.IpUtils import get_ip, get_hostnames
from millegrilles_messages.bus.BusContext import MilleGrillesBusContext, ForceTerminateExecution
from millegrilles_messages.bus.PikaConnector import MilleGrillesPikaConnector
from millegrilles_messages.bus.PikaMessageProducer import MilleGrillesPikaMessageProducer
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages.EnveloppeCertificat import CertificatExpire

LOGGER = logging.getLogger(__name__)


class InstanceContext(MilleGrillesBusContext):

    CONST_RUNLEVEL_INIT = 0  # Nothing finished loading yet
    CONST_RUNLEVEL_INSTALLING = 1  # No configuration (idmg, securite), waiting for admin
    CONST_RUNLEVEL_EXPIRED = 2  # Instance certificate is expired, auto-renewal not possible
    CONST_RUNLEVEL_NORMAL = 3  # Everything is ok, do checkup and then run until stopped

    def __init__(self, configuration: ConfigurationInstance):
        super().__init__(configuration, False)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__bus_connector: Optional[MilleGrillesPikaConnector] = None
        self.__docker_handler: Optional[DockerHandlerInterface] = None

        self.__instance_id: Optional[str] = None
        self.__securite: Optional[str] = None
        self.__idmg: Optional[str] = None
        self.__ip_address: Optional[str] = None
        self.__hostname: Optional[str] = None
        self.__hostnames: Optional[list[str]] = None
        self.__csr_genere: Optional[CleCsrGenere] = None

        self.__reload_q: asyncio.Queue[Optional[float]] = asyncio.Queue(maxsize=2)
        self.__reload_listeners: list[Callable[[], None]] = list()
        self.__application_status = ApplicationInstallationStatus()
        self.__reload_done = asyncio.Event()

        self.__current_system_state: Optional[dict] = None  # Property set externally by the SystemStatus thread
        self.__runlevel = InstanceContext.CONST_RUNLEVEL_INIT
        self.__loop = asyncio.get_event_loop()

    @property
    def configuration(self) -> ConfigurationInstance:
        return super().configuration

    async def run(self):
        self.__logger.debug("InstanceContext thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(super().run())
                group.create_task(self.__reload_thread())
                group.create_task(self.__presence_thread())
                group.create_task(self.__stop_thread())
        except *Exception:  # Stop on any thread exception
            self.__logger.exception("InstanceContext Error")
            if self.stopping is False:
                self.__logger.exception("Context Unhandled error, closing")
                self.stop()
                await asyncio.sleep(1)
                raise ForceTerminateExecution()
        self.__logger.debug("InstanceContext thread done")

    async def __reload_thread(self):
        while self.stopping is False:
            reload_value = await self.__reload_q.get()
            if reload_value is None:
                return  # Done
            if reload_value > 0:
                await asyncio.sleep(reload_value)
            try:
                await asyncio.to_thread(self.reload)
            except CertificatExpire:
                self.__logger.exception("Certificate expired - context only partially reloaded")

    async def __presence_thread(self):
        while self.stopping is False:
            try:
                producer = await self.get_producer()
            except asyncio.TimeoutError:
                # Producer not ready yet
                await self.wait(5)
                continue

            event_security_level = self.__securite
            if event_security_level == Constantes.SECURITE_SECURE:
                # Downgrade 4.secure a niveau 3.protege
                event_security_level = Constantes.SECURITE_PROTEGE

            status_content = {
                'hostname': self.hostname,
                'hostnames': self.hostnames,
                'ip': self.ip_address,
                'security': self.securite,
            }
            status_content.update(self.__current_system_state)
            event_content = {'status': status_content}
            try:
                await producer.event(event_content, Constantes.DOMAINE_INSTANCE,
                                     ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE_V2, exchange=event_security_level)
            except asyncio.TimeoutError:
                self.__logger.debug("Timeout sending presence event")
            except asyncio.CancelledError as e:
                raise e
            except:
                self.__logger.exception("Unhandled error sending presence event")
            await self.wait(20)

    async def __stop_thread(self):
        await self.wait()
        await self.__reload_q.put(None)
        raise ForceTerminateExecution()  # Kick out the __presence_thread thread if stuck on get_producer

    def add_reload_listener(self, listener: Callable[[], None]):
        self.__reload_listeners.append(listener)

    def update_application_status(self, app_name: str, status: dict):
        self.__application_status.update(app_name, status)

    @property
    def runlevel(self):
        return self.__runlevel

    @runlevel.setter
    def runlevel(self, value: int):
        self.__runlevel = value

    @property
    def bus_connector(self) -> MilleGrillesPikaConnector:
        if self.__bus_connector is None:
            raise Exception('not initialized')
        return self.__bus_connector

    @bus_connector.setter
    def bus_connector(self, value: MilleGrillesPikaConnector):
        self.__bus_connector = value

    @property
    def docker_actif(self) -> bool:
        return self.__docker_handler is not None

    @property
    def docker_handler(self) -> DockerHandlerInterface:
        if self.__docker_handler is None:
            raise Exception('not initialized')
        return self.__docker_handler

    @docker_handler.setter
    def docker_handler(self, value: DockerHandlerInterface):
        self.__docker_handler = value

    async def get_producer(self) -> MilleGrillesPikaMessageProducer:
        return await self.__bus_connector.get_producer()

    @property
    def instance_id(self):
        if self.__instance_id is None:
            raise ValueNotAvailable()
        return self.__instance_id

    @property
    def securite(self):
        if self.__securite is None:
            raise ValueNotAvailable()
        return self.__securite

    @property
    def idmg(self):
        if self.__idmg is None:
            raise ValueNotAvailable()
        return self.__idmg

    @property
    def hostname(self):
        return self.__hostname

    @property
    def hostnames(self):
        return self.__hostnames

    @property
    def ip_address(self):
        return self.__ip_address

    @property
    def csr_genere(self):
        if self.__csr_genere is None:
            self.__csr_genere = CleCsrGenere.build(self.instance_id)
        return self.__csr_genere

    @property
    def application_status(self) -> ApplicationInstallationStatus:
        return self.__application_status

    @property
    def current_system_state(self) -> dict:
        return self.__current_system_state

    @current_system_state.setter
    def current_system_state(self, value: dict):
        self.__current_system_state = value

    def clear_csr_genere(self):
        self.__csr_genere = None

    async def delay_reload(self, delay: float):
        self.__reload_done.clear()
        await self.__reload_q.put(delay)

    async def reload_wait(self):
        self.__reload_done.clear()
        await self.__reload_q.put(0)
        await self.__reload_done.wait()

    def reload(self):
        configuration: ConfigurationInstance = self.configuration

        instance_id = configuration.get_instance_id()
        self.__instance_id = instance_id

        try:
            try:
                securite = configuration.get_securite()
                idmg = configuration.get_idmg()

                self.__securite = securite
                self.__idmg = idmg
            except FileNotFoundError:
                # System not configured yet
                self.__securite = None
                self.__idmg = None

            try:
                super().reload()
            except FileNotFoundError:
                # System not configured yet
                self.__logger.info("Certificate not available yet, MQ Bus unavailable")
            except CertificatExpire:
                # The system certificate is expired
                self.__logger.info("Certificate is expired, MQ Bus unavailable")

            self.__ip_address = get_ip()
            self.__logger.debug("Local IP: %s" % self.__ip_address)
            self.__hostname, self.__hostnames = get_hostnames(fqdn=True)
            self.__logger.debug("Local domain: %s, domaines : %s" % (self.__hostname, self.__hostnames))

            # Call reload listeners
            for listener in self.__reload_listeners:
                listener()
        finally:
            self.__loop.call_soon_threadsafe(self.__reload_done.set)

    def ssl_session(self, timeout: Optional[aiohttp.ClientTimeout] = None):
        ssl_context = self.ssl_context
        if ssl_context is None:
            raise ValueNotAvailable()
        connector = aiohttp.TCPConnector(ssl=ssl_context)
        session = aiohttp.ClientSession(timeout=timeout, connector=connector)
        return session



class ValueNotAvailable(Exception):
    pass
