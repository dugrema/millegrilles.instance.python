import asyncio
import json
import logging

from asyncio import TaskGroup
from typing import Optional

from millegrilles_instance.Context import InstanceContext
from millegrilles_messages.messages import Constantes as MilleGrillesConstantes


class AppManager:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context

        self.__applications_changed = asyncio.Event()
        self.__stopping = asyncio.Event()

        self.__initial_refresh_done = asyncio.Event()

        self.__securite: Optional[str] = None

    async def wait_initial_refresh_done(self):
        await self.__initial_refresh_done.wait()

    async def __stop_thread(self):
        await self.__context.wait()
        self.__stopping.set()

    async def setup(self):
        self.__securite = self.__context.securite if self.__context.securite != MilleGrillesConstantes.SECURITE_SECURE else MilleGrillesConstantes.SECURITE_PROTEGE

    async def run(self):
        self.__logger.debug("SystemStatus thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__emit_application_list_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("SystemStatus thread done")

    async def __emit_application_list_thread(self):
        """
        Thread that reads the list of installed applications and sends it to CoreTopology.
        """
        await self.__context.wait(4)
        self.__logger.info("Starting emit applications thread")
        while self.__context.stopping is False:
            try:
                await self.__emit_application_list()
            except Exception:
                self.__logger.exception("Error sending installed application list")
            await self.__context.wait(30)
        self.__logger.info("Stopping emit applications thread")

    async def __emit_application_list(self):
        try:
            producer = await asyncio.wait_for(self.__context.get_producer(), 1)
        except asyncio.TimeoutError:
            self.__logger.warning("Timeout waiting for producer to emit applications list")
            return

        installed_applications_path = self.__context.configuration.path_millegrilles / "etc" / "installed_applications.json"
        with open(installed_applications_path, 'r') as f:
            content = await asyncio.to_thread(json.load, f)

        event_message = {
            'applications': content,
        }

        await producer.event(
            event_message,
            'instance',
            'presenceInstanceApplicationsV2',
            partition=self.__context.instance_id,
            exchange=self.__securite,
        )

# from typing import Dict, List, Optional, TypedDict
#
# # Language-specific labels
# ApplicationLabels = Dict[str, str]
#
# # An item within the 'portal' list
# class PortalItem(TypedDict):
#     admin: Optional[bool]
#     port: Optional[int]
#     path: Optional[str]
#     labels: Optional[ApplicationLabels]
#     api: Optional[bool]
#
# # Metadata for a single application
# class ApplicationInfo(TypedDict):
#     name: str
#     version: str
#     securite: str
#     labels: ApplicationLabels
#     path: Optional[str]       # e.g., "millegrilles" or "apps"
#     web: Optional[List[PortalItem]] # Always a list, or not present
#
# # Top-level mapping: app_id -> application_data
# InstalledApplications = Dict[str, ApplicationInfo]