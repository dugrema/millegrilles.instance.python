import asyncio
import logging

from asyncio import Event as EventAsyncio, TimeoutError
from threading import Event

from millegrilles.instance.DockerState import DockerState
from millegrilles.instance.DockerHandler import DockerHandler
from millegrilles.instance.DockerCommandes import CommandeListerServices, CommandeListerContainers, \
    CommandeAjouterConfiguration, CommandeSupprimerConfiguration, CommandeGetConfiguration, \
    CommandeAjouterSecret, CommandeSupprimerSecret

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

    action_creer_configuration = CommandeAjouterConfiguration('test.config', 'mon test', {'label': 'moui!'}, aio=True)
    handler.ajouter_action(action_creer_configuration)
    config = await action_creer_configuration.get_resultat()
    logger.debug("Resultat creer configuration : %s" % config.id)

    action_get_configuration = CommandeGetConfiguration('test.config', aio=True)
    handler.ajouter_action(action_get_configuration)
    data_config = await action_get_configuration.get_data()
    logger.debug("Resultat get configuration : %s" % data_config)

    action_supprimer_configuration = CommandeSupprimerConfiguration('test.config', aio=True)
    handler.ajouter_action(action_supprimer_configuration)
    resultat = await action_supprimer_configuration.get_resultat()
    logger.debug("Resultat supprimer configuration : %s" % resultat)

    action_creer_secret = CommandeAjouterSecret('test.secret', 'mon test', {'label': 'moui!'}, aio=True)
    handler.ajouter_action(action_creer_secret)
    config = await action_creer_secret.get_resultat()
    logger.debug("Resultat creer secret : %s" % config.id)

    action_supprimer_secret = CommandeSupprimerSecret('test.secret', aio=True)
    handler.ajouter_action(action_supprimer_secret)
    resultat = await action_supprimer_secret.get_resultat()
    logger.debug("Resultat supprimer secret : %s" % resultat)

    try:
        await asyncio.wait_for(wait_event.wait(), 5)
    except TimeoutError:
        pass


def main():
    # test_sync()
    asyncio.run(test_async())


if __name__ == '__main__':
    logging.basicConfig()
    logger.setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    main()
