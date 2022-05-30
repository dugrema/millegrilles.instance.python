import asyncio
import json
import logging
import lzma

from asyncio import Event
from typing import Optional
from os import listdir, path

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation, MessageProducerFormatteur
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

    async def executer_commande(self, producer: MessageProducerFormatteur, message: MessageWrapper):
        reponse = None

        if message.est_valide is False:
            return {'ok': False, 'err': 'Signature ou certificat invalide'}

        routing_key = message.routing_key
        action = routing_key.split('.').pop()
        exchange = message.exchange
        enveloppe = message.certificat
        exchanges = enveloppe.get_exchanges
        roles = enveloppe.get_roles

        if exchange == Constantes.SECURITE_PROTEGE and Constantes.SECURITE_PROTEGE in exchanges:
            if Constantes.ROLE_CORE in roles:
                if action == ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES:
                    return await self.transmettre_catalogue(producer, message)

        if reponse is None:
            reponse = {'ok': False, 'err': 'Commande inconnue ou acces refuse'}

        return reponse

    async def transmettre_catalogue(self, producer: MessageProducerFormatteur, message: MessageWrapper):
        self.__logger.info("Transmettre catalogues")
        path_catalogues = self._etat_instance.configuration.path_catalogues

        liste_fichiers_apps = listdir(path_catalogues)

        info_apps = [path.join(path_catalogues, f) for f in liste_fichiers_apps if f.endswith('.json.xz')]
        for app_path in info_apps:
            with lzma.open(app_path, 'rt') as fichier:
                app_transaction = json.load(fichier)

            commande = {"catalogue": app_transaction}
            await producer.executer_commande(commande, domaine=Constantes.DOMAINE_CORE_CATALOGUES,
                                             action='catalogueApplication', exchange=Constantes.SECURITE_PROTEGE,
                                             nowait=False)

        return {'ok': True}
