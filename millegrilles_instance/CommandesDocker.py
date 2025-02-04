import asyncio
import logging
import time
from asyncio import TaskGroup

from typing import Optional

from docker import DockerClient
from docker.errors import ContainerError
from docker.models.containers import Container
from docker.models.services import Service
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
        # containers = parse_liste_containers(docker_client.containers.list(all=True))
        containers_list = await asyncio.to_thread(docker_client.containers.list, all=True)
        containers = parse_liste_containers(containers_list)
        # services = parse_list_service(docker_client.services.list())
        services_list = await asyncio.to_thread(docker_client.services.list)
        services = parse_list_service(services_list)
        await self._callback_asyncio({'info': info, 'containers': containers, 'services': services})

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
        containers = docker_client.containers.list(filters={"name": "^%s\\." % self.__nom_service})
        container = None
        for i in range(0, 5):
            try:
                container: Container = containers.pop()
                break
            except IndexError:
                # Container non-trouve, on attend avant de reessayer
                self.__logger.debug("Container de service %s non trouve, on attend 5 secondes" % self.__nom_service)
                try:
                    time.sleep(5)
                except asyncio.TimeoutError:
                    pass
                containers = docker_client.containers.list(filters={"name": self.__nom_service})

        if container is None:
            self.__logger.debug("Container de service %s non trouve, on abandonne" % self.__nom_service)
            return await self._callback_asyncio({'code': -1, 'output': 'Container %s introuvable' % self.__nom_service})

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


# class CommandeGetServicesBackup(CommandeDocker):
#     """
#     Retourne la liste de tous les services avec un label "backup_scripts"
#     """
#
#     def __init__(self):
#         super().__init__()
#         self.facteur_throttle = 0.25
#
#     async def executer(self, docker_client: DockerClient):
#         liste_services = docker_client.services.list(filters={"label": "backup_scripts"})
#         services = parse_list_service(liste_services)
#         await self._callback_asyncio(services)
#
#     async def get_services(self) -> dict:
#         resultat = await self.attendre()
#         info = resultat['args'][0]
#         return info


def parse_list_service(services: list) -> dict:
    # Mapper services et etat
    dict_services = dict()
    for service in services:
        attrs = service.attrs
        spec = attrs['Spec']

        image_name = spec['TaskTemplate']['ContainerSpec']['Image'].split('@')[0]
        try:
            image_version = image_name.split('/')[1].split(':')[1]
        except IndexError:
            try:
                image_version = image_name.split(':')[1]
            except IndexError:
                image_version = image_name

        info_service = {
            'creation_service': service.attrs['CreatedAt'],
            'maj_service': service.attrs['UpdatedAt'],
            'image': image_name,
            'version': image_version,
        }
        labels = spec.get('Labels')
        if labels:
            info_service['labels'] = labels
        mode = spec.get('Mode')
        if mode:
            replicated = mode.get('Replicated')
            if replicated:
                replicas = replicated.get('Replicas')
                if replicas:
                    info_service['replicas'] = replicas

        tasks = [task for task in service.tasks() if task['DesiredState'] == 'running']
        if len(tasks) > 0:
            task = tasks[-1]
            info_service['etat'] = task['Status']['State']
            info_service['message_tache'] = task['Status']['Message']

        dict_services[service.name] = info_service

    return dict_services


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


def check_service_running(service: Service) -> int:
    tasks = [task for task in service.tasks() if task['DesiredState'] == 'running']
    return len(tasks)

def check_service_preparing(service: Service) -> int:
    tasks = [task for task in service.tasks() if task['DesiredState'] == 'preparing']
    return len(tasks)

def check_replicas(service: Service):
    attrs = service.attrs
    spec = attrs['Spec']
    mode = spec['Mode']
    try:
        replicated = mode['Replicated']
        return replicated['Replicas']
    except KeyError:
        return None


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
    except TypeError:
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