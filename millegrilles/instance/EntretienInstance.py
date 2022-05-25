# Module d'entretien de l'instance protegee
import asyncio
import logging

from typing import Optional

from asyncio import Event, TimeoutError

from millegrilles.messages import Constantes
from millegrilles.instance.EtatInstance import EtatInstance
from millegrilles.instance.InstanceDocker import EtatDockerInstanceSync


def get_module_execution(etat_instance: EtatInstance):
    securite = etat_instance.niveau_securite

    if securite == Constantes.SECURITE_PROTEGE:
        return InstanceProtegee()

    return None


class InstanceProtegee:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_stop: Optional[Event] = None
        self.__etat_instance: Optional[EtatInstance] = None
        self.__etat_docker: Optional[EtatDockerInstanceSync] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self.__event_stop = Event()
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

    async def fermer(self):
        self.__event_stop.set()

    async def run(self):
        self.__logger.info("run()")
        while self.__event_stop.is_set() is False:
            self.__logger.debug("run() debut execution cycle")

            try:
                self.__logger.debug("run() fin execution cycle")
                await asyncio.wait_for(self.__event_stop.wait(), 30)
            except TimeoutError:
                pass
        self.__logger.info("Fin run()")
