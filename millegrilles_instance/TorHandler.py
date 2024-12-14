import logging

from docker.models.containers import Container

from millegrilles_docker.DockerHandler import CommandeDocker, DockerClient, DockerHandlerException

ONIONIZE_HOSTNAME_PATH = '/var/lib/tor/onion_services/nginx/hostname'


class CommandeOnionizeGetHostname(CommandeDocker):
    """
    Copie les certificats vers un volume local
    """

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.facteur_throttle = 0.1

    async def executer(self, docker_client: DockerClient):
        container = trouver_onionize(docker_client)
        hostname = self.get_hostname(container)
        await self._callback_asyncio(hostname)

    def get_hostname(self, container: Container):
        exit_code, hostname = container.exec_run('cat %s' % ONIONIZE_HOSTNAME_PATH)
        if exit_code == 0:
            return hostname.decode('utf-8').strip()
        return None

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


def trouver_onionize(docker_client: DockerClient) -> Container:
    """
    Trouve un container onionize actif.
    :param docker_client:
    :return: Container acme
    """
    containers = docker_client.containers.list(filters={'label': 'onionize=true'})
    if len(containers) == 0:
        raise OnionizeNonDisponibleException("Container onionize introuvable")

    container = containers.pop()  # Prendre un containe onionize au hasard

    return container


class OnionizeNonDisponibleException(DockerHandlerException):
    pass
