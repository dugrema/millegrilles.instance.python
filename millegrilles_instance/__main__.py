import asyncio
import logging
import sys

from asyncio import TaskGroup
from concurrent.futures.thread import ThreadPoolExecutor
from typing import Awaitable

from millegrilles_instance.SystemStatus import SystemStatus
from millegrilles_messages.bus.BusContext import ForceTerminateExecution, StopListener
from millegrilles_messages.bus.BusExceptions import ConfigurationFileError
from millegrilles_messages.bus.PikaConnector import MilleGrillesPikaConnector
from millegrilles_messages.docker.DockerHandler import DockerState
from millegrilles_instance.NginxHandler import NginxHandler
from millegrilles_instance.Certificats import GenerateurCertificatsHandler
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance.MaintenanceApplications import ApplicationsHandler
from millegrilles_instance.Manager import InstanceManager
from millegrilles_instance.WebServer import WebServer
from millegrilles_instance.MgbusHandler import MgbusHandler

LOGGER = logging.getLogger(__name__)


async def force_terminate_task_group():
    """Used to force termination of a task group."""
    raise ForceTerminateExecution()


async def main():
    config = ConfigurationInstance.load()
    try:
        context = InstanceContext(config)
    except ConfigurationFileError as e:
        LOGGER.error("Error loading configuration files %s, quitting" % str(e))
        sys.exit(1)  # Quit

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
    system_status = SystemStatus(context)

    docker_state = DockerState(context)
    if docker_state.docker_present() is False:
        # Docker not supported
        raise Exception('Docker environment not detected')

    docker_handler = InstanceDockerHandler(context, docker_state)
    context.add_reload_listener(docker_handler.callback_changement_configuration)

    generateur_certificats = GenerateurCertificatsHandler(context, docker_handler)
    nginx_handler = NginxHandler(context, docker_handler)
    applications_handler = ApplicationsHandler(context, docker_handler)

    # Facade
    manager = InstanceManager(context, generateur_certificats, docker_handler, applications_handler, nginx_handler)
    context.add_reload_listener(manager.callback_changement_configuration)

    # Access modules
    web_server = WebServer(manager)
    bus_handler = MgbusHandler(manager)

    # Setup / injecting dependencies
    await docker_handler.setup(generateur_certificats)
    await manager.setup(bus_handler)
    await web_server.setup()
    await nginx_handler.setup()

    # Create tasks
    coros = [
        context.run(),
        generateur_certificats.run(),
        system_status.run(),
        applications_handler.run(),
        manager.run(),
        web_server.run(),
        bus_handler.run(),
        nginx_handler.run(),
    ]

    if docker_handler:
        coros.append(docker_handler.run())

    return coros


if __name__ == '__main__':
    asyncio.run(main())
    LOGGER.info("Stopped")
