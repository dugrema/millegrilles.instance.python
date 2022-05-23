import asyncio
import logging

from asyncio import Event as EventAsyncio, TimeoutError
from threading import Event

from millegrilles.instance.DockerState import DockerState
from millegrilles.instance.DockerHandler import DockerHandler
from millegrilles.instance.DockerCommandes import CommandeListerServices, CommandeListerContainers

logger = logging.getLogger(__name__)


def callback_liste(liste):
    logger.info("Liste recue : %s", liste)


def test_sync():
    wait_event = Event()

    state = DockerState()
    handler = DockerHandler(state)
    handler.start()

    action_services = CommandeListerServices(callback_liste)
    handler.ajouter_action(action_services)
    action_services = CommandeListerServices(callback_liste, filters={'name': 'mongo'})
    handler.ajouter_action(action_services)
    action_services = CommandeListerServices(callback_liste, filters={'name': 'nginx'})
    handler.ajouter_action(action_services)
    wait_event.wait(5)
    action_services = CommandeListerContainers(callback_liste)
    handler.ajouter_action(action_services)

    wait_event.wait(5)


async def test_async():
    wait_event = EventAsyncio()

    state = DockerState()
    handler = DockerHandler(state)
    handler.start()

    action_services = CommandeListerServices(aio=True)
    handler.ajouter_action(action_services)
    resultat = await action_services.get_liste()
    logger.debug("Resultat services async : %s" % resultat)

    action_containers = CommandeListerContainers(aio=True)
    handler.ajouter_action(action_containers)
    resultat = await action_containers.get_liste()
    logger.debug("Resultat containers async : %s" % resultat)

    try:
        await asyncio.wait_for(wait_event.wait(), 5)
    except TimeoutError:
        pass


def main():
    test_sync()
    asyncio.run(test_async())


if __name__ == '__main__':
    logging.basicConfig()
    logger.setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    main()
