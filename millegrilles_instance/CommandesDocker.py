import asyncio
import logging
import time
from asyncio import TaskGroup

from typing import Optional

from docker import DockerClient
from docker.errors import ContainerError
from docker.models.containers import Container
from docker.types import Mount

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.Interfaces import DockerHandlerInterface
from millegrilles_instance.millegrilles_docker import DockerCommandes
from millegrilles_instance.millegrilles_docker.DockerCommandes import PullStatus
from millegrilles_instance.millegrilles_docker.DockerHandler import CommandeDocker

LOGGER = logging.getLogger(__name__)


class CommandeListeTopologie(CommandeDocker):

    def __init__(self):
        super().__init__()

        self.facteur_throttle = 0.25  # Utilise pour throttling, represente un cout relatif de la commande

    async def executer(self, docker_client: DockerClient):
        info = await asyncio.to_thread(docker_client.info)
        containers_list = await asyncio.to_thread(
            docker_client.containers.list, 
            all=True, 
            filters={'label': 'com.millegrilles.module'}
        )
        containers = parse_liste_containers(containers_list)
        await self._callback_asyncio({'info': info, 'containers': containers})

    async def get_info(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info

    def __repr__(self):
        return 'CommandeListeTopologie'


class CommandeExecuterScriptDansService(CommandeDocker):

    def __init__(self, nom_service: str, path_script: str):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self.__nom_service = nom_service
        self.__path_script = path_script

        self.facteur_throttle = 2.0

    async def executer(self, docker_client: DockerClient):
        containers = docker_client.containers.list(filters={"name": self.__nom_service})
        if not containers:
            self.__logger.debug("Container for service %s not found" % self.__nom_service)
            return await self._callback_asyncio({'code': -1, 'output': f'Container for service {self.__nom_service} not found'})
        
        container = containers[0]
        self.__logger.debug("Container de service %s, on execute le script %s" % (self.__nom_service, self.__path_script))
        exit_code, output = container.exec_run(self.__path_script)
        self.__logger.debug("Resultat execution %s = %s" % (self.__path_script, exit_code))
        await self._callback_asyncio({'code': exit_code, 'output': output})

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info

    def __repr__(self):
        return f'CommandeExecuterScriptDansService {self.__nom_service}: {self.__path_script}'



class CommandeExecuterContainerInit(CommandeDocker):

    def __init__(self, config: ConfigurationInstance, image: str, params):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__config = config
        self.__image = image
        self.__container_init = params
        self.facteur_throttle = 2.0

    async def executer(self, docker_client: DockerClient):
        mounts = list()
        for mount in self.__container_init.mounts:
            mounts.append(Mount(type=mount['type'], source=mount['source'], target=mount['target']))

        # secret_values = pathlib.Path('/var/opt/millegrilles/secrets')
        secret_values = self.__config.path_secrets
        password_dict = dict()
        for file_path in secret_values.iterdir():
            if file_path.is_file() and file_path.name.endswith('.txt'):
                with open(file_path, 'rt') as fp:
                    password_dict[file_path.name] = fp.read().strip()

        environment = dict()
        for key, value in self.__container_init.env.items():
            if value.startswith("${SECRETS/"):
                secret_file_name = value.split("/")[1][:-1]
                password = password_dict.get(secret_file_name)
                environment[key] = password
            else:
                environment[key] = value

        try:
            result = await asyncio.to_thread(
                docker_client.containers.run, image=self.__image, command=self.__container_init.args,
                mounts=mounts, environment=environment)
        except ContainerError as e:
            await self._callback_asyncio({'done': True, 'code': e.exit_status, 'err': e.stderr})
            return

        await self._callback_asyncio({'done': True, 'ok': True})


async def get_docker_image_tag(context: InstanceContext, docker_handler: DockerHandlerInterface, image: str, pull=True, app_name: Optional[str] = None) -> str:
    commande_image = DockerCommandes.CommandeGetImage(image, pull=pull)

    async with TaskGroup() as group:
        if app_name:
            # Thread to read status from state
            group.create_task(download_update_callback(context, app_name, commande_image))

        # Create download task
        group.create_task(docker_handler.run_command(commande_image))

    try:
        image_info = await commande_image.get_resultat()
        image_tag = image_info['tags'][0]
    except (TypeError, IndexError):
        raise UnknownImage(image)
    return image_tag


async def download_update_callback(context: InstanceContext, app_name:str, commande_image: DockerCommandes.CommandeGetImage):
    log_update_count = 0
    while True:
        log_update_count += 1
        if log_update_count % 5 == 0:
            LOGGER.info("CommandeGetImage %s status: %s" % (app_name, commande_image.pull_status.status_str()))
        status = commande_image.pull_status.__dict__()
        context.update_application_status(app_name, {'download': status})
        try:
            await asyncio.wait_for(commande_image.attendre(), 1)
            break  # Done
        except asyncio.TimeoutError:
            pass
    status = commande_image.pull_status.__dict__()
    # status['done'] = True
    context.update_application_status(app_name, {'download': status})

class UnknownImage(Exception):
    pass

def parse_liste_containers(containers: list) -> dict:
    # Mapper services et etat
    dict_containers = dict()
    for container in containers:
        attrs = container.attrs
        info_container = {
            'creation': attrs['Created'],
            'restart_count': attrs['RestartCount'],
        }

        state = attrs['State']
        info_container['etat'] = state['Status']
        info_container['running'] = state['Running']
        info_container['dead'] = state['Dead']
        info_container['finished_at'] = state['FinishedAt']

        info_container['labels'] = attrs['Config']['Labels']

        dict_containers[attrs['Name']] = info_container

    return dict_containers
