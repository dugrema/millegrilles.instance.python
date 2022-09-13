import asyncio
import datetime
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
    stop_event = Event()

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
    await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)


async def run_tests(messages_thread, stop_event):
    # Demarrer test (attendre connexion prete)
    await messages_thread.attendre_pret()

    logger.info("emettre requetes grosfichiers")

    # await get_documentsParFuuid(messages_thread)
    # await verifier_acces_fuuids(messages_thread)
    # await get_favoris(messages_thread)
    # await sync_collection(messages_thread)
    await sync_recents(messages_thread)
    # await sync_corbeille(messages_thread)

    stop_event.set()

    logger.info("Fin main()")


async def get_favoris(messages_thread):
    action = 'favoris'
    requete = {'user_id': 'z2i3XjxEBWbPQ8KptFX8DEA4BstgkwKghfR2fFznQEdW9zjc6qL'}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def get_documentsParFuuid(messages_thread):
    action = 'documentsParFuuid'
    requete = {'fuuids_documents': ['zSEfXUAmNoDiHaPaocwvfuAu78eQSejBDpmrif5Zw8QSo5SdK9mBuqBe7QQYEku5KiVNVEpQy8gHCpgDTywVLrKc4dfyPH']}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def verifier_acces_fuuids(messages_thread):
    action = 'verifierAccesFuuids'
    requete = {
        'user_id': 'z2i3XjxEBWbPQ8KptFX8DEA4BstgkwKghfR2fFznQEdW9zjc6qL',
        'fuuids': [
            #'zSEfXUAWF1A6WTjXYernnhZtjLswj6BRfRLHfGLjGbCUAVxaJYE3nbYEVQ6bAYmFNS5Q3tMRRXeg16Zb9oRYGHZuySRSKk',
            #'zSEfXUDbNyYCAvXXypa7QBSPFN9VmtiP2nPNRRXnkpsHYM4MRrfwqE4CJnnX6TsDCpVrYGLCzsoz7wbETU34fhYNEPjuPp',
            'zSEfXUD8p125rKUNbRmLcg5eSihuJtS24wCxSW941H6gDs2cAwZBNKuXZPvNUiDvyJmEmXUdMkwie35arDs3tAPLFaV3B1',
        ]
    }
    producer = messages_thread.get_producer()
    reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def sync_collection(messages_thread):
    action = 'syncCollection'
    skip = 0
    complete = False
    while complete is False:
        requete = {
            'cuuid': '085b8595-c8e6-480c-a451-b2515fcd38a7',
            'user_id': 'z2i3Xjx9Jv4LqevqLyEFoWib1TL9YrfdMczmWxXWrZdb1gN7fTb',
            'limit': 2,
            'skip': skip,
        }
        producer = messages_thread.get_producer()
        reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PROTEGE)
        contenu = json.dumps(reponse.parsed, indent=2)
        logger.info("Reponse recue : %s", contenu)
        complete = reponse.parsed['complete']
        skip = skip + len(reponse.parsed['fichiers'])

    logger.info("Nombre de fichiers : %d" % skip)


async def sync_recents(messages_thread):
    action = 'syncRecents'
    skip = 0
    complete = False
    while complete is False:
        requete = {
            'user_id': 'z2i3Xjx9Jv4LqevqLyEFoWib1TL9YrfdMczmWxXWrZdb1gN7fTb',
            'debut': round(datetime.datetime.utcnow().timestamp() - (14 * 24 * 60 * 60)),
            'fin': round(datetime.datetime.utcnow().timestamp() - (13 * 24 * 60 * 60)),
            'limit': 10,
            'skip': skip,
        }
        producer = messages_thread.get_producer()
        reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PROTEGE)
        contenu = json.dumps(reponse.parsed, indent=2)
        logger.info("Reponse recue : %s", contenu)
        complete = reponse.parsed['complete']
        compte = len(reponse.parsed['fichiers'])
        skip = skip + compte

    logger.info("Nombre de fichiers : %d" % skip)


async def sync_corbeille(messages_thread):
    action = 'syncCorbeille'
    skip = 0
    complete = False
    while complete is False:
        requete = {
            'user_id': 'z2i3Xjx9Jv4LqevqLyEFoWib1TL9YrfdMczmWxXWrZdb1gN7fTb',
            'debut': round(datetime.datetime.utcnow().timestamp() - (13 * 24 * 60 * 60)),
            'fin': round(datetime.datetime.utcnow().timestamp() - (12 * 24 * 60 * 60)),
            'limit': 10,
            'skip': skip,
        }
        producer = messages_thread.get_producer()
        reponse = await producer.executer_requete(requete, 'GrosFichiers', action=action, exchange=Constantes.SECURITE_PROTEGE)
        contenu = json.dumps(reponse.parsed, indent=2)
        logger.info("Reponse recue : %s", contenu)
        complete = reponse.parsed['complete']
        compte = len(reponse.parsed['fichiers'])
        skip = skip + compte

    logger.info("Nombre de fichiers : %d" % skip)


async def callback_reply_q(message, messages_module):
    logger.info("Message recu : %s" % message)
    # wait_event.wait(0.7)


if __name__ == '__main__':
    logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARN)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    asyncio.run(main())
