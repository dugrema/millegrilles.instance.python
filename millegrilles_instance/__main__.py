import asyncio
import logging
import sys

from asyncio import TaskGroup
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Awaitable

from millegrilles_instance.ManagerSetup import setup_manager
from millegrilles_instance.SystemStatus import SystemStatus
from millegrilles_instance.apps.AppManager import AppManager
from millegrilles_instance.apps.CertificatesManager import CertificatesManager
from millegrilles_messages.bus.BusContext import ForceTerminateExecution, StopListener
from millegrilles_messages.bus.BusExceptions import ConfigurationFileError
from millegrilles_messages.bus.PikaConnector import MilleGrillesPikaConnector
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.Manager import InstanceManager
from millegrilles_instance.MgbusHandler import MgbusHandler

LOGGER = logging.getLogger(__name__)


async def force_terminate_task_group():
    """Used to force termination of a task group."""
    raise ForceTerminateExecution()


async def run_manager(context: InstanceContext) -> None:
    LOGGER.setLevel(logging.INFO)
    LOGGER.info("Starting")

    # Wire classes together, gets awaitables to run
    try:
        coros = await wiring(context)
    except PermissionError as e:
        LOGGER.error("Permission denied on loading configuration and preparing folders : %s" % str(e))
        sys.exit(2)  # Quit

    try:
        # Use taskgroup to run all threads
        async with TaskGroup() as group:
            # Create a listener that fires a task to cancel all other tasks
            async def stop_group():
                group.create_task(force_terminate_task_group())

            stop_listener = StopListener(stop_group)
            context.register_stop_listener(stop_listener)

            for coro in coros:
                group.create_task(coro)

        return  # All done, quitting with no errors
    except* (ForceTerminateExecution, asyncio.CancelledError):
        # Result of the termination task
        LOGGER.error("__main__ Force termination exception")
        context.stop()

    sys.exit(3)


async def wiring(context: InstanceContext) -> list[Awaitable]:
    # Some executor threads get used to handle threading.Event triggers for the duration of the execution.
    # Ensure there are enough.
    loop = asyncio.get_event_loop()
    loop.set_default_executor(ThreadPoolExecutor(max_workers=15))

    # Handlers (services)
    bus_connector = MilleGrillesPikaConnector(context)
    context.bus_connector = bus_connector
    # system_status = SystemStatus(context)
    app_manager = AppManager(context)
    certificate_manager = CertificatesManager(context)

    # Facade
    manager = InstanceManager(context, app_manager)
    context.add_reload_listener(manager.callback_changement_configuration)

    # Access modules
    bus_handler = MgbusHandler(manager)

    # Setup / injecting dependencies
    await manager.setup(bus_handler)

    # Create tasks
    coros = [
        context.run(),
        # system_status.run(),
        app_manager.run(),
        manager.run(),
        bus_handler.run(),
        certificate_manager.run(),
    ]

    return coros


async def main():
    config = ConfigurationInstance.load()
    if config.verbose:
        LOGGER.setLevel(logging.DEBUG)
    else:
        LOGGER.setLevel(logging.INFO)

    try:
        context = InstanceContext(config)
    except ConfigurationFileError as e:
        LOGGER.error("Error loading configuration files %s, quitting" % str(e))
        sys.exit(1)  # Quit

    if config.init_only:
        LOGGER.info("Starting maintenance of the environment")
        try:
            await setup_manager(context)
        except Exception as e:
            LOGGER.exception("Error initializing manager")
            sys.exit(2)
        LOGGER.info("Manager initialization completed")
    else:
        await run_manager(context)


if __name__ == '__main__':
    asyncio.run(main())
    LOGGER.info("Stopped")
