import base64
import json
import logging

from typing import Union

from docker import DockerClient
from docker.errors import APIError, NotFound

from millegrilles_messages.docker.DockerHandler import CommandeDocker


class CommandeListeTopologie(CommandeDocker):

    def __init__(self, callback=None, aio=True):
        super().__init__(callback, aio)

        self.facteur_throttle = 0.25  # Utilise pour throttling, represente un cout relatif de la commande

    def executer(self, docker_client: DockerClient):
        info = docker_client.info()
        containers = docker_client.containers.list()
        services = docker_client.services.list()
        self.callback({'info': info, 'containers': containers, 'services': services})

    async def get_info(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info
