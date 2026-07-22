import asyncio
import logging

from asyncio import TaskGroup

from millegrilles_instance.Context import InstanceContext


class AppManager:

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
        self.__logger.debug("SystemStatus thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("SystemStatus thread done")
