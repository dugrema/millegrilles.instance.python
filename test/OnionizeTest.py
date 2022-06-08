import asyncio
import logging

from millegrilles_messages.docker.DockerHandler import DockerState, DockerHandler
from millegrilles_instance.TorHandler import CommandeOnionizeGetHostname

logger = logging.getLogger("__main__")
logger.setLevel(logging.DEBUG)

docker_state = DockerState()
docker_handler = DockerHandler(docker_state)
docker_handler.start()


async def test_get_hostname():
    commande = CommandeOnionizeGetHostname()
    docker_handler.ajouter_commande(commande)
    hostname = await commande.get_resultat()

    logger.info("Resultat hostname onion %s" % hostname)


async def run_tests():
    logger.debug("run_tests debut")
    await test_get_hostname()
    logger.debug("run_tests fin")


def main():
    logging.basicConfig()
    logging.getLogger('millegrilles_messages').setLevel(logging.DEBUG)
    logging.getLogger('millegrilles_instance').setLevel(logging.DEBUG)

    logger.debug("Running main")

    asyncio.run(run_tests())


if __name__ == '__main__':
    main()
