import base64
import json

from typing import Union

from docker import DockerClient

from millegrilles.instance.DockerHandler import CommandeDocker


class CommandeListerContainers(CommandeDocker):

    def __init__(self, callback=None, aio=False, filters: dict = None):
        super().__init__(callback, aio)
        self.__filters = filters

    def executer(self, docker_client: DockerClient):
        liste = docker_client.containers.list(filters=self.__filters)
        self.callback(liste)

    async def get_liste(self) -> list:
        resultat = await self.attendre()
        liste = resultat['args'][0]
        return liste


class CommandeListerServices(CommandeDocker):

    def __init__(self, callback=None, aio=False, filters: dict = None):
        super().__init__(callback, aio)
        self.__filters = filters

    def executer(self, docker_client: DockerClient):
        liste = docker_client.services.list(filters=self.__filters)
        self.callback(liste)

    async def get_liste(self) -> list:
        resultat = await self.attendre()
        liste = resultat['args'][0]
        return liste


class CommandeAjouterConfiguration(CommandeDocker):

    def __init__(self, nom: str, data: Union[dict, str, bytes], labels: dict = None, callback=None, aio=False):
        super().__init__(callback, aio)
        self.__nom = nom
        self.__labels = labels

        if isinstance(data, dict):
            data_string = json.dumps(data).encode('utf-8')
        elif isinstance(data, str):
            data_string = data.encode('utf-8')
        elif isinstance(data, bytes):
            data_string = data
        else:
            raise ValueError("Type data non supporte")

        self.__data = data_string

    def executer(self, docker_client: DockerClient):
        reponse = docker_client.configs.create(name=self.__nom, data=self.__data, labels=self.__labels)
        self.callback(reponse)

    async def get_resultat(self) -> list:
        resultat = await self.attendre()
        return resultat['args'][0]


class CommandeSupprimerConfiguration(CommandeDocker):

    def __init__(self, nom: str, callback=None, aio=False):
        super().__init__(callback, aio)
        self.__nom = nom

    def executer(self, docker_client: DockerClient):
        config = docker_client.configs.get(self.__nom)
        reponse = config.remove()
        self.callback(reponse)

    async def get_resultat(self) -> list:
        resultat = await self.attendre()
        return resultat['args'][0]


class CommandeGetConfiguration(CommandeDocker):

    def __init__(self, nom: str, callback=None, aio=False):
        super().__init__(callback, aio)
        self.__nom = nom

    def executer(self, docker_client: DockerClient):
        config = docker_client.configs.get(self.__nom)
        self.callback(config)

    async def get_config(self) -> list:
        resultat = await self.attendre()
        return resultat['args'][0]

    async def get_data(self) -> str:
        resultat = await self.attendre()
        config = resultat['args'][0]
        data = config.attrs['Spec']['Data']
        data_str = base64.b64decode(data)
        if isinstance(data_str, bytes):
            data_str = data_str.decode('utf-8')

        return data_str


class CommandeAjouterSecret(CommandeDocker):

    def __init__(self, nom: str, data: Union[dict, str, bytes], labels: dict = None, callback=None, aio=False):
        super().__init__(callback, aio)
        self.__nom = nom
        self.__labels = labels

        if isinstance(data, dict):
            data_string = json.dumps(data).encode('utf-8')
        elif isinstance(data, str):
            data_string = data.encode('utf-8')
        elif isinstance(data, bytes):
            data_string = data
        else:
            raise ValueError("Type data non supporte")

        self.__data = data_string

    def executer(self, docker_client: DockerClient):
        reponse = docker_client.secrets.create(name=self.__nom, data=self.__data, labels=self.__labels)
        self.callback(reponse)

    async def get_resultat(self) -> list:
        resultat = await self.attendre()
        return resultat['args'][0]


class CommandeSupprimerSecret(CommandeDocker):

    def __init__(self, nom: str, callback=None, aio=False):
        super().__init__(callback, aio)
        self.__nom = nom

    def executer(self, docker_client: DockerClient):
        config = docker_client.secrets.get(self.__nom)
        reponse = config.remove()
        self.callback(reponse)

    async def get_resultat(self) -> list:
        resultat = await self.attendre()
        return resultat['args'][0]
