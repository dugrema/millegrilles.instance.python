import asyncio
import logging

from asyncio import Event
from typing import Optional

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_messages.messages.MessagesModule import MessageWrapper


class CommandHandler:

    def __init__(self, entretien_instance, etat_instance: EtatInstance,
                 etat_docker: EtatDockerInstanceSync):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._entretien_instance = entretien_instance
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

    async def executer_commande(self, message: MessageWrapper):
        reponse = None

        if reponse is None:
            reponse = {'ok': True}

        return reponse


