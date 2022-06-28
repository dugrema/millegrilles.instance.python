import asyncio
import datetime
import logging

from threading import Event

import pytz

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

    logger.info("emettre commandes cedule")

    await cedule_heure_specifique(messages_thread)

    stop_event.set()

    logger.info("Fin main()")


async def cedule_heure_specifique(messages_thread):
    action = 'cedule'
    producer = messages_thread.get_producer()
    estampille = datetime.datetime(2022, 6, 19, 4, 0, 0, tzinfo=pytz.UTC)  # Complet
    # estampille = datetime.datetime(2022, 6, 20, 8, 0, 0, tzinfo=pytz.UTC)  # Incremental
    evenement = {
        "estampille": int(estampille.timestamp()),
        "date_string": estampille.isoformat(),
        "flag_annee": False,
        "flag_heure": False,
        "flag_jour": False,
        "flag_mois": False,
        "flag_semaine": False
    }
    await producer.emettre_evenement(evenement, 'global', action=action, exchanges=[Constantes.SECURITE_PRIVE])


async def callback_reply_q(message, messages_module):
    logger.info("Message recu : %s" % message)
    # wait_event.wait(0.7)


if __name__ == '__main__':
    logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARN)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    asyncio.run(main())
