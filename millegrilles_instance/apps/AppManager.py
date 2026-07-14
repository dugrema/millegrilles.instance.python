import asyncio
import logging

from asyncio import TaskGroup

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.NginxHandler import NginxHandler
from millegrilles_instance.apps.Certificates import renew_certificates


class AppManager:

    def __init__(self, context: InstanceContext, nginx_handler: NginxHandler):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context
        self.__nginx_handler = nginx_handler

        self.__applications_changed = asyncio.Event()
        self.__stopping = asyncio.Event()

        self.__initial_refresh_done = asyncio.Event()

    async def wait_initial_refresh_done(self):
        await self.__initial_refresh_done.wait()

    async def __stop_thread(self):
        await self.__context.wait()
        self.__stopping.set()

    async def run(self):
        self.__logger.debug("SystemStatus thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__maintenance_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("SystemStatus thread done")

    async def __maintenance_thread(self):
        while not self.__stopping.is_set():
            await self.maintenance()
            self.__initial_refresh_done.set()
            try:
                await asyncio.wait_for(self.__stopping.wait(), 900)
                return  # Stopping
            except asyncio.TimeoutError:
                pass  # Run maintenance

    async def maintenance(self):
        await self.renew_certificates()

    async def renew_certificates(self):
        """
        Loads all base docker compose files and recursively goes through includes to cumulate the x-certificate-configuration elements.
        Each certificate under secrets/ that matches the configuration is checked and appropriate certificates are created/renewed.
        """
        changes_pending = await asyncio.to_thread(renew_certificates, self.__context)
        if changes_pending:
            # Some changes were applied
            self.__applications_changed.set()

    async def reload_nginx(self):
        self.__logger.warning("NginxHandler refresh_nginx called - NOT IMPLEMENTED")
