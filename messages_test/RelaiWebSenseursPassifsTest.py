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

    logger.info("emettre requetes backup")

    # await relai_get(messages_thread)
    await relai_challenge(messages_thread)

    stop_event.set()

    logger.info("Fin main()")


async def relai_get(messages_thread):
    action = 'test'
    commande = {'texte': 'test'}
    producer = messages_thread.get_producer()
    reponse = await producer.executer_commande(commande, 'senseurspassifs_hub', action=action, partition='DUMMY', exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def relai_challenge(messages_thread):
    action = 'challengeAppareil'
    commande = {
        'uuid_appareil': 'rpi-pico-e6614104033e722b',
        'challenge': [2, 2, 1, 3],
    }
    producer = messages_thread.get_producer()
    reponse = await producer.executer_commande(commande, 'SenseursPassifs', action=action, exchange=Constantes.SECURITE_PRIVE)
    contenu = json.dumps(reponse.parsed, indent=2)
    logger.info("Reponse recue : %s", contenu)


async def callback_reply_q(message, messages_module):
    logger.info("Message recu : %s" % message)
    # wait_event.wait(0.7)


if __name__ == '__main__':
    logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARN)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    asyncio.run(main())
