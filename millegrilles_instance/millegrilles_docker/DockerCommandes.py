import os
import os
import asyncio
import base64
import docker
import json
import logging
import math
from typing import Optional, Union, Callable, Coroutine, Any
from docker import DockerClient
from docker.errors import APIError, NotFound
from docker.models.volumes import Volume

from millegrilles_instance.millegrilles_docker.DockerHandler import CommandeDocker

LOGGER = logging.getLogger(__name__)

class DockerComposeCommand(CommandeDocker):
    def __init__(self, service_name: Optional[str] = None):
        super().__init__()
        self.__service_name = service_name
        self.facteur_throttle = 1.0

    async def _run_compose_command(self, args: list[str]) -> str:
        cmd = ["docker", "compose"] + args
        if self.__service_name:
            cmd += [self.__service_name]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            err_msg = stderr.decode().strip()
            raise Exception(f"Docker Compose error: {err_msg}")
            
        return stdout.decode().strip()

class CommandeListerServices(DockerComposeCommand):
    def __init__(self, filters: dict = None):
        super().__init__()
        self.__filters = filters

    async def executer(self, docker_client: DockerClient):
        output = await self._run_compose_command(["ps"])
        await self._callback_asyncio(output)

    def __repr__(self):
        return 'CommandeListerServices'

class CommandeRedemarrerService(DockerComposeCommand):
    def __init__(self, nom_service: str):
        super().__init__(nom_service)
        self.facteur_throttle = 1.5

    async def executer(self, docker_client: DockerClient):
        await self._run_compose_command(["restart"])
        await self._callback_asyncio(True)

    def __repr__(self):
        return f'CommandeRedemarrerService {self.__service_name}'

class CommandeMajService(DockerComposeCommand):
    def __init__(self, nom_service: str):
        super().__init__(nom_service)
        self.facteur_throttle = 1.5

    async def executer(self, docker_client: DockerClient):
        await self._run_compose_command(["up", "-d"])
        await self._callback_asyncio(True)

    def __repr__(self):
        return f'CommandeMajService {self.__service_name}'

class CommandeDemarrerService(DockerComposeCommand):
    def __init__(self, nom_service: str):
        super().__init__(nom_service)
        self.facteur_throttle = 1.5

    async def executer(self, docker_client: DockerClient):
        await self._run_compose_command(["start"])
        await self._callback_asyncio(True)

    def __repr__(self):
        return f'CommandeDemarrerService {self.__service_name}'

class CommandeArreterService(DockerComposeCommand):
    def __init__(self, nom_service: str):
        super().__init__(nom_service)
        self.facteur_throttle = 0.5

    async def executer(self, docker_client: DockerClient):
        await self._run_compose_command(["stop"])
        await self._callback_asyncio(True)

    def __repr__(self):
        return f'CommandeArreterService {self.__service_name}'

class CommandeSupprimerService(DockerComposeCommand):
    def __init__(self, nom_service: str):
        super().__init__(nom_service)
        self.facteur_throttle = 0.5

    async def executer(self, docker_client: DockerClient):
        await self._run_compose_command(["rm", "-f"])
        await self._callback_asyncio(True)

    def __repr__(self):
        return f'CommandeSupprimerService {self.__service_name}'

class PullStatus:
    def __init__(self):
        self.initialized = False
        self.total_size = 0
        self.current_size = 0
        self.incomplete = 0
        self.all_totals_known = False
        self.pct = 0
        self.done = False

    def __dict__(self) -> dict:
        return {
            'total_size': self.total_size,
            'current_size': self.current_size,
            'incomplete': self.incomplete,
            'all_totals_known': self.all_totals_known,
            'pct': self.pct,
            'done': self.done,
        }

    def update(self, layers: dict[str, dict]):
        self.initialized = True
        self.all_totals_known = True
        self.current_size = 0
        self.total_size = 0
        self.incomplete = 0
        for key, value in layers.items():
            if value.get('complete') is not True:
                self.incomplete = self.incomplete + 1
            try:
                self.total_size = self.total_size + value['total']
            except KeyError:
                if value.get('complete') is not True:
                    self.all_totals_known = False
            try:
                self.current_size = self.current_size + value['current']
            except KeyError:
                pass
        
        if self.all_totals_known and self.total_size > 0:
            self.pct = math.floor(self.current_size / self.total_size * 100)

    def set_done(self):
        self.initialized = True
        self.current_size = self.total_size
        self.incomplete = 0
        self.all_totals_known = True
        self.pct = 100
        self.done = True

    def status_str(self) -> str:
        if self.initialized is False:
            return 'Checking'
        if self.done:
            return "Downloading: DONE"
        if self.pct:
            return "Downloading: %d%% (%d/%d bytes), left to process: %d" % (self.pct, self.current_size, self.total_size, self.incomplete)
        else:
            return "Downloading: %d/%d+ bytes, left to process: %d" % (self.current_size, self.total_size, self.incomplete)

class CommandeGetImage(CommandeDocker):
    def __init__(self, nom_image: str, pull=False):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__nom_image = nom_image
        self.__pull = pull
        self.pull_status = PullStatus()
        if pull is True:
            self.facteur_throttle = 1.0
        else:
            self.facteur_throttle = 0.5

    async def executer(self, docker_client: DockerClient):
        try:
            reponse = await asyncio.to_thread(docker_client.images.get, self.__nom_image)
            await self._callback_asyncio({'id': reponse.id, 'tags': reponse.tags})
            return
        except NotFound:
            pass
        
        if self.__pull is True:
            try:
                repository, nom_image_tag = self.__nom_image.split('/')
            except ValueError:
                repository = None
                nom_image_tag = self.__nom_image
            
            try:
                nom_image, tag = nom_image_tag.split(':')
            except ValueError:
                nom_image = nom_image_tag
                tag = None
            
            if nom_image is None:
                raise Exception("Incorrect image name : %s" % self.__nom_image)
            
            if repository is not None:
                image_repository = '%s/%s' % (repository, nom_image)
            else:
                image_repository = nom_image
            
            try:
                await asyncio.to_thread(self.download_package, docker_client, image_repository, tag)
                reponse = await asyncio.to_thread(docker_client.images.get, self.__nom_image)
                await self._callback_asyncio({'id': reponse.id, 'tags': reponse.tags})
                return
            except NotFound:
                pass
        
        await self._callback_asyncio(None)

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        return resultat['args'][0]

    def download_package(self, client: docker.client.DockerClient, repository: str, tag: Optional[str] = None):
        pull_generator = client.api.pull(repository, tag, stream=True)
        layers = dict()
        for line in pull_generator:
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                self.__logger.debug("Error parsing download info: %s" % line)
                continue
            try:
                status = value['status']
                layer_id = value['id']
            except KeyError:
                continue
            try:
                progress_detail = value['progressDetail']
            except KeyError:
                progress_detail = None
            if status == 'Downloading':
                try:
                    layers[layer_id].update(progress_detail)
                except KeyError:
                    layers[layer_id] = progress_detail
            elif status == 'Pull complete':
                layers[layer_id]['complete'] = True
            elif status == 'Already exists':
                layers[layer_id] = {'complete': True}
            elif status == 'Pulling fs layer':
                layers[layer_id] = {'complete': False, 'current': 0}
            self.pull_status.update(layers)
        self.pull_status.set_done()

    async def progress_coro(self, cb: Callable[[PullStatus], Coroutine[Any, Any, None]]):
        while self._event_asyncio.is_set() is False:
            status = self.pull_status.status_str()
            if cb:
                try:
                    await cb(self.pull_status)
                except:
                    self.__logger.exception("CommandeGetImage.progress_coro Error running callback")
            self.__logger.debug("CommandeGetImage %s status: %s" % (self.__nom_image, status))
            try:
                await asyncio.wait_for(self._event_asyncio.wait(), 3)
            except asyncio.TimeoutError:
                pass
        self.__logger.debug("CommandeGetImage %s status: Done" % self.__nom_image)
        if cb:
            try:
                await cb(self.pull_status)
            except:
                self.__logger.exception("CommandeGetImage.progress_coro Error running callback")

    def __repr__(self):
        return f'CommandeGetImage {self.__nom_image}'

class CommandeRunContainer(CommandeDocker):
    def __init__(self, image: str, command: Optional[str] = None, environment: Optional[dict] = None, mounts: Optional[list[docker.types.Mount]] = None):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__image = image
        self.__command = command
        self.__environment = environment
        self.__mounts = mounts
        self.facteur_throttle = 1.0

    def ajouter_mount(self, source: str, target: str, mount_type='volume', read_only=False):
        if self.__mounts is None:
            self.__mounts = list()
        mount = docker.types.Mount(target, source, type=mount_type, read_only=read_only)
        self.__mounts.append(mount)

    async def executer(self, docker_client: DockerClient, attendre=True):
        params = {
            'environment': self.__environment,
            'mounts': self.__mounts,
            'network': os.environ.get("INSTANCE_NAME", "millegrille") + "_net",
            'auto_remove': True,
        }
        self.__logger.debug("Run %s %s" % (self.__image, self.__command))
        resultat = await asyncio.to_thread(docker_client.containers.run, self.__image, command=self.__command, stdout=True, stderr=True, **params)
        await self._callback_asyncio(resultat)

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        return resultat['args'][0]

    def __repr__(self):
        return f'CommandeRunContainer {self.__image}: {self.__command}'

class CommandeReloadNginx(CommandeDocker):
    def __init__(self, service_name: str = "nginx"):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__service_name = service_name
        self.facteur_throttle = 1.0

    async def executer(self, docker_client: DockerClient, attendre=True):
        try:
            cmd = ["docker", "compose", "exec", self.__service_name, "nginx", "-s", "reload"]
            process = await asyncio.create_subprocess_exec(*cmd)
            await process.wait()
            await self._callback_asyncio(True)
        except Exception as e:
            self.__logger.exception("Error reloading nginx")
            await self._callback_asyncio(e)

    def __repr__(self):
        return f'CommandeReloadNginx {self.__service_name}'

class CommandPruneCleanup(CommandeDocker):
    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.facteur_throttle = 1.0

    async def executer(self, docker_client: DockerClient, attendre=True):
        await asyncio.to_thread(docker_client.containers.prune)
        volumes: list[Volume] = await asyncio.to_thread(docker_client.volumes.list, filters={'dangling': True})
        for volume in volumes:
            try:
                label_anonymous = volume.attrs['Labels']['com.docker.volume.anonymous'] is not None
            except(TypeError, KeyError):
                label_anonymous = False
            if label_anonymous and len(volume.name) == 64:
                try:
                    await asyncio.to_thread(volume.remove)
                except APIError as e:
                    if e.status_code == 500:
                        pass
                    elif e.status_code == 409:
                        pass
                    else:
                        raise e
        await self._callback_asyncio(True)

    def __repr__(self):
        return 'CommandPruneCleanup'
