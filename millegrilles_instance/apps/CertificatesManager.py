import asyncio
import logging

from asyncio import TaskGroup

from millegrilles_messages.messages import Constantes as MilleGrillesConstantes

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.SystemdUtil import restart_compose_applications, restart_middleware, restart_nginx
from millegrilles_instance.apps.Certificates import renew_certificates


class CertificatesManager:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context

        self.__applications_changed = asyncio.Event()
        self.__stopping = asyncio.Event()

        self.__initial_refresh_done = asyncio.Event()

    async def wait_initial_refresh_done(self):
        await self.__initial_refresh_done.wait()

    async def __stop_thread(self):
        await self.__context.wait()
        self.__stopping.set()

    async def run(self):
        self.__logger.debug("CertificatesManager thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__renew_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("CertificatesManager thread done")

    async def __renew_thread(self):
        """
        Thread that manages certificates that are about to expire. Refreshes the certificates and reloads the
        docker compose services.
        """
        await self.__context.wait(10)
        self.__logger.info("Starting certificate renewal check thread")
        while self.__context.stopping is False:
            try:
                await self.__renew_certificates()
            except Exception:
                self.__logger.exception("Error renewing certificates in manager")
            await self.__context.wait(3600)
        self.__logger.info("Stopping certificate renewal check thread")

    async def __renew_certificates(self):
        renewed_config = await renew_certificates(self.__context)
        if len(renewed_config) == 0:
            self.__logger.debug("No certificates to renew")
            return  # Done

        names_renewed: set[str] = set([c['name'] for c in renewed_config])

        # Possible improvements:
        #   - read .yml files and extract service names directly
        #   - use docker compose restart on individual services

        try:
            names_renewed.remove('nginx')  # Hard-coded module name
            nginx_renewed = True
        except KeyError:
            nginx_renewed = False

        middleware_renewed = False
        # Hard-coded module names
        if self.__context.securite == MilleGrillesConstantes.SECURITE_PROTEGE:
            middleware_list = ['mq', 'mongo', 'midcompte', 'redis', 'ceduleur', 'webauth']
        else:
            middleware_list = ['redis', 'webauth']
        for name in middleware_list:
            try:
                names_renewed.remove(name)
                middleware_renewed = True
            except KeyError:
                pass

        # Anything left is in the applications.yml file
        applications_renewed = len(names_renewed) > 0

        instance_name = self.__context.configuration.instance_name
        if nginx_renewed:
            self.__logger.info("Certificates updated, reloading nginx")
            await asyncio.to_thread(restart_nginx, instance_name)

        if applications_renewed:
            self.__logger.info("Certificates updated, restarting applications")
            await asyncio.to_thread(restart_compose_applications, instance_name)

        if middleware_renewed:
            # Note : restarting the middleware potentially cuts the connection to MQ (closes the manager)
            self.__logger.warning("Certificates updated, restarting middleware (MQ may restart - this crashes the manager)")
            await asyncio.to_thread(restart_middleware, instance_name)

        self.__logger.info("Modules have been restarted after certificate renewal")
