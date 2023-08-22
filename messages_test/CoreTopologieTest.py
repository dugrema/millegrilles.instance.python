import asyncio
import logging
import json

from threading import Event

from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation

logger = logging.getLogger(__name__)

LOGGING_FORMAT = '%(asctime)s %(threadName)s %(levelname)s: %(message)s'


async def main():
    logger.info("Debut main()")
    stop_event = asyncio.Event()

    # Preparer resources consumer
    reply_res = RessourcesConsommation(callback_reply_q)

    messages_thread = MessagesThread(stop_event)
    messages_thread.set_reply_ressources(reply_res)

    # Demarrer traitement messages
    await messages_thread.start_async()

    tasks = [
        asyncio.create_task(messages_thread.run_async()),
        asyncio.create_task(run_tests(messages_thread, stop_event)),
    ]

    # Execution de la loop avec toutes les tasks
    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)


async def run_tests(messages_thread, stop_event):
    # Demarrer test (attendre connexion prete)
    logger.info("run tests attendre pret")
    await messages_thread.attendre_pret()

    logger.info("run tests emettre messages")

    # await resolve_idmg(messages_thread)
    # await requete_fiche(messages_thread)
    await requete_fiche_locale(messages_thread)
    # await requete_consignation_fichiers(messages_thread)
    # await requete_configuration_fichiers(messages_thread)

    stop_event.set()

    logger.info("Fin main()")


async def resolve_idmg(messages_thread):
    action = 'resolveIdmg'
    requete = {'dns': ['mg-int1.maple.maceroc.com']}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'CoreTopologie', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def requete_fiche(messages_thread):
    action = 'ficheMillegrille'
    requete = {'idmg': 'zeYncRqEqZ6eTEmUZ8whJFuHG796eSvCTWE4M432izXrp22bAtwGm7Jf'}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'CoreTopologie', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def requete_fiche_locale(messages_thread):
    action = 'ficheMillegrille'
    requete = {'idmg': 'zeYncRqEqZ6eTEmUZ8whJFuHG796eSvCTWE4M432izXrp22bAtwGm7Jf'}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'CoreTopologie', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def requete_consignation_fichiers(messages_thread):
    action = 'getConsignationFichiers'
    requete = {"primaire": True}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'CoreTopologie', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def requete_configuration_fichiers(messages_thread):
    action = 'getConfigurationFichiers'
    requete = {}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'CoreTopologie', action=action, exchange=Constantes.SECURITE_PROTEGE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def callback_reply_q(message, messages_module):
    logger.info("Message recu : %s" % message)
    # wait_event.wait(0.7)


if __name__ == '__main__':
    logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARN)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)
    logging.getLogger('millegrilles_messages').setLevel(logging.DEBUG)

    asyncio.run(main())
