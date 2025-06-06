import asyncio
import logging

from asyncio import Event as EventAsyncio, TimeoutError
from threading import Event

from millegrilles_messages.docker_obsolete.DockerHandler import DockerHandler, DockerState
from millegrilles_messages.docker_obsolete.DockerCommandes import CommandeGetConfigurationsDatees, CommandeListerConfigs, \
    CommandeListerSecrets, CommandeEnsureNodeLabels

logger = logging.getLogger(__name__)


def callback_liste(liste):
    logger.info("Liste recue : %s", liste)


def test_sync():
    wait_event = Event()

    state = DockerState()
    handler = DockerHandler(state)
    handler.start()

    liste = state.docker.services.list()
    for item in liste:
        image_name = item.attrs['Spec']['TaskTemplate']['ContainerSpec']['Image'].split('@')[0]
        try:
            image_version = image_name.split('/')[1].split(':')[1]
        except IndexError:
            try:
                image_version = image_name.split(':')[1]
            except IndexError:
                image_version = image_name
        print("Images %s, version: %s" % (image_name, image_version))
        pass

    # action_services = CommandeListerServices(callback_liste)
    # handler.ajouter_commande(action_services)
    # action_services = CommandeListerServices(callback_liste, filters={'name': 'mongo'})
    # handler.ajouter_commande(action_services)
    # action_services = CommandeListerServices(callback_liste, filters={'name': 'nginx'})
    # handler.ajouter_commande(action_services)
    # wait_event.wait(5)
    # action_services = CommandeListerContainers(callback_liste)
    # handler.ajouter_commande(action_services)
    #
    # wait_event.wait(5)


async def test_async():
    wait_event = EventAsyncio()

    state = DockerState()
    handler = DockerHandler(state)
    handler.start()

    # action_services = CommandeListerServices(aio=True)
    # handler.ajouter_commande(action_services)
    # resultat = await action_services.get_liste()
    # logger.debug("Resultat services async : %s" % resultat)
    #
    # action_containers = CommandeListerContainers(aio=True)
    # handler.ajouter_commande(action_containers)
    # resultat = await action_containers.get_liste()
    # logger.debug("Resultat containers async : %s" % resultat)
    #
    # action_creer_configuration = CommandeAjouterConfiguration('test.config', 'mon test', {'label': 'moui!'}, aio=True)
    # handler.ajouter_commande(action_creer_configuration)
    # config = await action_creer_configuration.get_resultat()
    # logger.debug("Resultat creer configuration : %s" % config.id)
    #
    # action_get_configuration = CommandeGetConfiguration('test.config', aio=True)
    # handler.ajouter_commande(action_get_configuration)
    # data_config = await action_get_configuration.get_data()
    # logger.debug("Resultat get configuration : %s" % data_config)
    #
    # action_supprimer_configuration = CommandeSupprimerConfiguration('test.config', aio=True)
    # handler.ajouter_commande(action_supprimer_configuration)
    # resultat = await action_supprimer_configuration.get_resultat()
    # logger.debug("Resultat supprimer configuration : %s" % resultat)
    #
    # action_creer_secret = CommandeAjouterSecret('test.secret', 'mon test', {'label': 'moui!'}, aio=True)
    # handler.ajouter_commande(action_creer_secret)
    # config = await action_creer_secret.get_resultat()
    # logger.debug("Resultat creer secret : %s" % config.id)
    #
    # action_supprimer_secret = CommandeSupprimerSecret('test.secret', aio=True)
    # handler.ajouter_commande(action_supprimer_secret)
    # resultat = await action_supprimer_secret.get_resultat()
    # logger.debug("Resultat supprimer secret : %s" % resultat)
    #
    # action_get_image = CommandeGetImage('docker.maceroc.com/mg_rabbitmq:3.9-management_1', pull=True, aio=True)
    # handler.ajouter_commande(action_get_image)
    # resultat = await action_get_image.get_resultat()
    # logger.debug("Resultat get image : %s" % resultat)

    action_ensure_nodelabels = CommandeEnsureNodeLabels(['millegrilles.test'], aio=True)
    handler.ajouter_commande(action_ensure_nodelabels)
    await action_ensure_nodelabels.attendre()

    try:
        await asyncio.wait_for(wait_event.wait(), 60)
    except TimeoutError:
        pass


async def test_config():

    wait_event = EventAsyncio()

    state = DockerState()
    handler = DockerHandler(state)
    handler.start()

    action_configurations = CommandeListerConfigs(aio=True)
    handler.ajouter_commande(action_configurations)
    resultat = await action_configurations.get_resultat()
    logger.debug("Resultat configurations (id only) : %s" % resultat)

    action_secrets = CommandeListerSecrets(aio=True)
    handler.ajouter_commande(action_secrets)
    resultat = await action_secrets.get_resultat()
    logger.debug("Resultat secrets (id only) : %s" % resultat)

    action_datees = CommandeGetConfigurationsDatees(aio=True)
    handler.ajouter_commande(action_datees)
    resultat = await action_datees.get_resultat()
    logger.debug("Resultat configurations datees : %s" % resultat)

    try:
        await asyncio.wait_for(wait_event.wait(), 5)
    except TimeoutError:
        pass


def main():
    test_sync()
    # asyncio.run(test_async())
    # asyncio.run(test_config())


if __name__ == '__main__':
    logging.basicConfig()
    logger.setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    main()
