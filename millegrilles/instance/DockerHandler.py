import asyncio
import logging

from asyncio import Event as EventAsyncio
from asyncio.events import AbstractEventLoop
from docker import DockerClient
from threading import Thread, Event
from typing import Optional

from millegrilles.instance.DockerState import DockerState


class CommandeDocker:

    def __init__(self, callback=None, aio=False):
        self.callback = callback

        self.__event_loop: Optional[AbstractEventLoop] = None
        self.__event_asyncio: Optional[EventAsyncio] = None
        self.__resultat = None
        self.__is_error = False

        if aio is True:
            self.__initasync()

    def executer(self, docker_client: DockerClient):
        if self.callback is not None:
            self.callback()

    def erreur(self, e: Exception):
        self.__is_error = True
        if self.callback is not None:
            self.callback(e, is_error=True)

    def __callback_asyncio(self, *args, **argv):
        self.__resultat = {'args': args, 'argv': argv}
        self.__event_loop.call_soon_threadsafe(self.__event_asyncio.set)

    def __initasync(self):
        self.__event_loop = asyncio.get_event_loop()
        self.__event_asyncio = EventAsyncio()
        self.callback = self.__callback_asyncio

    async def attendre(self):
        if self.__event_asyncio is not None:
            await self.__event_asyncio.wait()
            try:
                if self.__resultat['argv']['is_error'] is True:
                    raise self.__resultat['args'][0]
            except KeyError:
                pass
            return self.__resultat


class DockerHandler:

    def __init__(self, docker_state: DockerState):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__docker = docker_state.docker

        self.__stop_event = Event()
        self.__action_pending = Event()
        self.__thread: Optional[Thread] = None
        self.__throttle_actions: Optional[float] = None

        self.__action_fifo = list()

    def start(self):
        self.__thread = Thread(name="docker", target=self.run, daemon=True)
        self.__thread.start()

    def run(self):
        while self.__stop_event.is_set() is False:

            # Traiter actions
            while len(self.__action_fifo) > 0:
                action: CommandeDocker = self.__action_fifo.pop(0)
                self.__logger.debug("Traiter action docker %s" % action)
                try:
                    action.executer(self.__docker)
                except Exception as e:
                    self.__logger.exception("Erreur execution action docker")
                    try:
                        action.erreur(e)
                    except:
                        pass

                if self.__throttle_actions is not None:
                    # Appliquer le throttle (slow mode) pour docker au besoin
                    self.__stop_event.wait(self.__throttle_actions)

                if self.__stop_event.is_set() is True:
                    return  # Abort thread

            self.__action_pending.wait(30)
            self.__action_pending.clear()

    def ajouter_action(self, action: CommandeDocker):
        self.__action_fifo.append(action)
        self.__action_pending.set()
