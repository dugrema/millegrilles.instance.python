import logging

from asyncio import TaskGroup
from typing import Optional, Callable, Coroutine, Any

from cryptography.x509 import ExtensionNotFound

from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.Interfaces import MgbusHandlerInterface
from millegrilles_instance.Manager import InstanceManager
from millegrilles_messages.bus.BusContext import MilleGrillesBusContext
from millegrilles_messages.messages import Constantes
from millegrilles_messages.bus.PikaChannel import MilleGrillesPikaChannel
from millegrilles_messages.bus.PikaQueue import MilleGrillesPikaQueueConsumer, RoutingKey
from millegrilles_messages.messages.MessagesModule import MessageWrapper


class MgbusHandler(MgbusHandlerInterface):
    """
    MQ access module
    """

    def __init__(self, manager: InstanceManager):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)
        self.__manager = manager
        self.__task_group: Optional[TaskGroup] = None

    async def run(self):
        async with TaskGroup() as group:
            self.__task_group = group
            group.create_task(self.__stop_thread())
        self.__task_group = None

    async def __stop_thread(self):
        await self.__manager.context.wait()

    async def register(self):
        self.__logger.info("Register with the MQ Bus")

        context = self.__manager.context

        instance_id = context.instance_id
        niveau_securite = context.securite

        # RK uniquement 3.protege
        if niveau_securite == Constantes.SECURITE_SECURE:
            # Downgrade securite a 3.protege pour recevoir les commandes
            niveau_securite_ajuste = Constantes.SECURITE_PROTEGE
        else:
            niveau_securite_ajuste = niveau_securite

        channel_exclusive = create_exclusive_q_channel(context, self.on_exclusive_message)
        await self.__manager.context.bus_connector.add_channel(channel_exclusive)

        channel_applications = create_applications_channel(instance_id, niveau_securite_ajuste, context, self.on_application_message)
        await self.__manager.context.bus_connector.add_channel(channel_applications)

        channel_requests = create_requests_channel(instance_id, niveau_securite_ajuste, context, self.on_request_message)
        await self.__manager.context.bus_connector.add_channel(channel_requests)

        # channel_certificates = create_certificates_channel(instance_id, niveau_securite_ajuste, context, self.on_certificate_message)
        # await self.__manager.context.bus_connector.add_channel(channel_certificates)

        # Start mgbus connector thread
        self.__task_group.create_task(self.__manager.context.bus_connector.run())

    async def unregister(self):
        self.__logger.info("Unregister from the MQ Bus")
        # await self.__manager.context.bus_connector.()
        raise NotImplementedError('Stop mgbus thread / unregister all channels')

    async def on_exclusive_message(self, message: MessageWrapper):
        # Authorization check - 3.protege/CoreTopologie
        enveloppe = message.certificat
        try:
            domaines = enveloppe.get_domaines
        except ExtensionNotFound:
            domaines = list()
        try:
            exchanges = enveloppe.get_exchanges
        except ExtensionNotFound:
            exchanges = list()

        if 'CoreTopologie' in domaines and Constantes.SECURITE_PROTEGE in exchanges:
            pass  # CoreTopologie
        else:
            return  # Ignore message

        action = message.routage['action']

        # if action == 'filehostingUpdate':
        #     # File hosts updated, reload configuration
        #     pass  # return await self.__solr_manager.reload_filehost_configuration()

        self.__logger.info("on_exclusive_message Ignoring unknown action %s" % action)

    async def on_application_message(self, message: MessageWrapper):
        raise NotImplementedError()

    async def on_request_message(self, message: MessageWrapper):
        # Authorization check
        enveloppe = message.certificat
        try:
            domaines = enveloppe.get_domaines
        except ExtensionNotFound:
            domaines = list()
        try:
            exchanges = enveloppe.get_exchanges
        except ExtensionNotFound:
            exchanges = list()

        if 'GrosFichiers' in domaines and Constantes.SECURITE_PROTEGE in exchanges:
            pass  # GrosFichiers
        else:
            return  # Ignore message

        payload = message.parsed
        action = message.routage['action']

        # if action == ConstantesRelaiSolr.REQUETE_FICHIERS:
        #     pass  # return await self.__solr_manager.query(user_id, payload)

        self.__logger.info("on_request_message Ignoring unknown action %s" % action)

    async def on_certificate_message(self, message: MessageWrapper):
        raise NotImplementedError()


def create_exclusive_q_channel(context: MilleGrillesBusContext,
                               on_message: Callable[[MessageWrapper], Coroutine[Any, Any, None]]) -> MilleGrillesPikaChannel:
    exclusive_q_channel = MilleGrillesPikaChannel(context, prefetch_count=20)
    exclusive_q = MilleGrillesPikaQueueConsumer(context, on_message, None, exclusive=True, arguments={'x-message-ttl': 60_000})

    exclusive_q.add_routing_key(RoutingKey(Constantes.SECURITE_PUBLIC, 'evenement.MaitreDesCles.certMaitreDesCles'))
    exclusive_q.add_routing_key(RoutingKey(Constantes.SECURITE_PUBLIC,
                                           f'evenement.CoreTopologie.{ConstantesInstance.EVENEMENT_TOPOLOGIE_FICHEPUBLIQUE}'))

    exclusive_q_channel.add_queue(exclusive_q)

    return exclusive_q_channel

def create_applications_channel(instance_id: str, niveau_securite: str, context: InstanceContext,
                                on_message: Callable[[MessageWrapper], Coroutine[Any, Any, None]]) -> MilleGrillesPikaChannel:

    q_channel = MilleGrillesPikaChannel(context, prefetch_count=1)
    q = MilleGrillesPikaQueueConsumer(context, on_message, f'instance/{instance_id}/applications',
                                      arguments={'x-message-ttl': 300_000})

    if niveau_securite == Constantes.SECURITE_SECURE:
        # Downgrade securite a 3.protege pour recevoir les commandes
        niveau_securite_ajuste = Constantes.SECURITE_PROTEGE
    else:
        niveau_securite_ajuste = niveau_securite

    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_INSTALLER}'))
    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_UPGRADE}'))
    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_SUPPRIMER}'))
    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_DEMARRER}'))
    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_ARRETER}'))
    # q.add_routing_key(RoutingKey(niveau_securite_ajuste,
    #                              f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_REQUETE_CONFIG}'))
    # q.add_routing_key(RoutingKey(niveau_securite_ajuste,
    #                              f'commande.instance.{instance_id}.{ConstantesInstance.COMMANDE_APPLICATION_CONFIGURER}'))

    q_channel.add_queue(q)
    return q_channel


def create_requests_channel(instance_id: str, niveau_securite: str, context: InstanceContext,
                                on_message: Callable[[MessageWrapper], Coroutine[Any, Any, None]]) -> MilleGrillesPikaChannel:

    if niveau_securite == Constantes.SECURITE_SECURE:
        # Downgrade securite a 3.protege pour recevoir les commandes
        niveau_securite_ajuste = Constantes.SECURITE_PROTEGE
    else:
        niveau_securite_ajuste = niveau_securite

    q_channel = MilleGrillesPikaChannel(context, prefetch_count=3)
    q = MilleGrillesPikaQueueConsumer(context, on_message, None, exclusive=True, arguments={'x-message-ttl': 30_000})

    # q.add_routing_key(RoutingKey(Constantes.SECURITE_PUBLIC,
    #                              f'commande.instance.{instance_id}.{ConstantesInstance.REQUETE_CONFIGURATION_ACME}'))
    q.add_routing_key(RoutingKey(niveau_securite_ajuste,
                                 f'commande.instance.{instance_id}.{ConstantesInstance.REQUETE_GET_PASSWORDS}'))

    if niveau_securite == Constantes.SECURITE_PROTEGE:
        q.add_routing_key(RoutingKey(Constantes.SECURITE_PROTEGE,
                                     f'commande.instance.{ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES}'))

    # #         # RK Public pour toutes les instances
    # #         res_configuration.ajouter_rk(Constantes.SECURITE_PUBLIC, 'requete.instance.%s.%s' % (
    # #             instance_id, ConstantesInstance.REQUETE_CONFIGURATION_ACME))
    # #         res_installation.ajouter_rk(niveau_securite_ajuste, 'requete.instance.%s.%s' % (
    # #             instance_id, ConstantesInstance.REQUETE_GET_PASSWORDS))
    # #         if niveau_securite == Constantes.SECURITE_PROTEGE:
    # #             res_configuration.ajouter_rk(niveau_securite, 'commande.instance.%s' % ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES)

    q_channel.add_queue(q)
    return q_channel


# def create_certificates_channel(instance_id: str, niveau_securite: str, context: InstanceContext,
#                                 on_message: Callable[[MessageWrapper], Coroutine[Any, Any, None]]) -> MilleGrillesPikaChannel:
#
#     q_channel = MilleGrillesPikaChannel(context, prefetch_count=1)
#     q = MilleGrillesPikaQueueConsumer(context, on_message, f'instance/{instance_id}/certificates',
#                                       arguments={'x-message-ttl': 300_000})
#
#     # Configuration thread pour messages de signature de certificats
#     #         # res_signature = RessourcesConsommation(
#     #         #     self.callback_reply_q, channel_separe=True, est_asyncio=True, actif=True, auto_delete=True, exclusive=True)
#     #
#     #         # Commandes sur niveau 4.secure
#     #         # if niveau_securite == Constantes.SECURITE_SECURE:
#     #         #     res_signature.ajouter_rk(niveau_securite, 'commande.instance.%s' % ConstantesInstance.COMMANDE_SIGNER_CSR)
#     #         #     res_signature.ajouter_rk(niveau_securite, 'commande.instance.%s' % ConstantesInstance.COMMANDE_SIGNER_COMPTE_USAGER)
#     #         #     res_signature.ajouter_rk(niveau_securite, 'commande.instance.%s' % ConstantesInstance.COMMANDE_SIGNER_PUBLICKEY_DOMAINE)
#     #
#     pass
