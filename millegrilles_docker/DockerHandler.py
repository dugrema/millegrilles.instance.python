import asyncio
import docker
import logging
import json
import psutil

from asyncio import TaskGroup
from docker import DockerClient
from docker.errors import APIError, DockerException
from typing import Optional

from millegrilles_messages.bus.BusContext import MilleGrillesBusContext, ForceTerminateExecution


class DockerState:

    def __init__(self, context: MilleGrillesBusContext):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        path_socket = '/run/docker.sock'
        try:
            self.__docker = docker.DockerClient('unix://' + path_socket)
        except DockerException:
            self.__docker = docker.from_env()  # On Windows

        self.__logger.info("Docker socket a connecte %s" % path_socket)

        self.__docker_actif: Optional[bool] = None

    @property
    def context(self) -> MilleGrillesBusContext:
        return self.__context

    def docker_present(self):
        try:
            version_docker = self.__docker.version()
        except AttributeError:
            # __docker = None
            return False

        self.__logger.debug("Version docker : %s" % json.dumps(version_docker, indent=2))
        return True

    def swarm_present(self):
        try:
            info_docker = self.__docker.info()
        except AttributeError:
            return False  # __docker est None

        try:
            swarm_config = info_docker['Swarm']
            self.__logger.info("Information swarm docker %s" % json.dumps(swarm_config, indent=2))
            return swarm_config['Nodes'] > 0
        except KeyError:
            self.__logger.info("Swarm docker n'est pas configure")
            return False

    def docker_actif(self):
        if self.__docker_actif is None:
            try:
                present = self.docker_present()
                swarm = self.swarm_present()
                if present is True and swarm is True:
                    self.__docker_actif = True
                else:
                    self.__docker_actif = False
            except Exception:
                self.__logger.exception("Erreur verification etat docker")
                self.__docker_actif = False

        return self.__docker_actif

    @property
    def docker(self):
        return self.__docker


class CommandeDocker:

    def __init__(self):
        self._event_asyncio = asyncio.Event()
        self.__resultat = None
        self.__is_error = False
        self.__exception = None

        self.facteur_throttle = 1.0  # Utilise pour throttling, represente un cout relatif de la commande

    async def executer(self, docker_client: DockerClient):
        raise NotImplementedError('must implement')

    async def erreur(self, e: Exception):
        self.__is_error = True
        self.__exception = e
        await self._callback_asyncio(e, is_error=True)

    async def _callback_asyncio(self, *args, **argv):
        self.__resultat = {'args': args, 'argv': argv}
        self._event_asyncio.set()

    async def attendre(self, timeout=60):
        await self._event_asyncio.wait()
        if self.__is_error:
            raise self.__exception
        return self.__resultat

    async def annuler(self):
        pass  # TODO


class DockerHandler:

    def __init__(self, docker_state: DockerState):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = docker_state.context
        self.__docker = docker_state.docker
        self.__action_fifo: asyncio.Queue[Optional[CommandeDocker]] = asyncio.Queue(maxsize=10)
        # self.__action_fifo: list[Optional[CommandeDocker]] = list()
        # self.__action_pending = threading.Event()

    @property
    def context(self) -> MilleGrillesBusContext:
        return self.__context

    async def run(self):
        async with TaskGroup() as group:
            group.create_task(self.__process_actions())

    def ajouter_commande(self, action: CommandeDocker):
        raise NotImplementedError('obsolete')
        # self.__action_fifo.append(action)
        # self.__action_pending.set()

    async def run_command(self, action: CommandeDocker):
        await self.__action_fifo.put(action)
        try:
            return await action.attendre()
        except asyncio.TimeoutError as e:
            await action.annuler()
            raise e

    async def __process_actions(self):
        while self.context.stopping is False:
            action = await self.__action_fifo.get()
            if action is None:
                return  # Exit condition

            # Traiter actions
            self.__logger.debug("Traiter action docker %s" % action)
            try:
                await action.executer(self.__docker)
            except APIError as e:
                # Monter silencieusement, erreur habituelle
                try:
                    await action.erreur(e)
                except:
                    self.__logger.exception("Error handling docker action exception")
                    await action.annuler()
            except DockerHandlerException as e:
                try:
                    # Bubble up sans logging
                    await action.erreur(e)
                except:
                    self.__logger.exception("Erreur emission action.erreur() commen reponse pour commande docker")
            except Exception as e:
                self.__logger.exception("Erreur execution action docker")
                try:
                    await action.erreur(e)
                except:
                    self.__logger.exception("Erreur emission action.erreur() commen reponse pour commande docker")
                finally:
                    continue

            # Throttling commandes docker en fonction du CPU load
            # Sous 1.5 de load, aucun throttling. Apres, c'est 3*cpu_load jusqu'a limite de 30.0 secondes
            cpu_load, _cpu_load5, _cpu_load10 = await asyncio.to_thread(psutil.getloadavg)
            cpu_load = max(cpu_load, 0.3)  # Fixer a au moins 0.3 pour creer un throttle sur chaque commande
            facteur_throttle = max(cpu_load, 0.3) * action.facteur_throttle
            wait_time = min(facteur_throttle, 30.0)  # Attendre load*n en secondes, max 30 secondes

            # self.__logger.debug(
            #     "Throttling commandes docker, cpu_load:%f attente %f secondes" % (cpu_load, wait_time))
            await self.__context.wait(wait_time)
            # self.__logger.debug("Throttling commandes docker, pret pour prochaine commande")

        if self.context.stopping is False:
            self.__logger.error("Docker thread stopping out of turn - quitting")
            self.context.stop()
            raise ForceTerminateExecution()


class DockerHandlerException(Exception):
    pass
