import asyncio
import datetime
import logging
import json

from threading import Event

from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.Notifications import EmetteurNotifications

logger = logging.getLogger(__name__)

LOGGING_FORMAT = '%(asctime)s %(threadName)s %(levelname)s: %(message)s'


async def main():
    logger.info("Debut main()")
    stop_event = Event()

    # Preparer resources consumer
    reply_res = RessourcesConsommation(callback_reply_q)

    messages_thread = MessagesThread(stop_event)
    messages_thread.set_reply_ressources(reply_res)

    enveloppe_ca = EnveloppeCertificat.from_file('/var/opt/millegrilles/configuration/pki.millegrille.cert')

    notifications = EmetteurNotifications(enveloppe_ca, champ_from='NotificationsTest')

    # Demarrer traitement messages
    await messages_thread.start_async()

    tasks = [
        asyncio.create_task(messages_thread.run_async()),
        asyncio.create_task(run_tests(messages_thread, stop_event, notifications)),
    ]

    # Execution de la loop avec toutes les tasks
    await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)


async def run_tests(messages_thread, stop_event, notifications):
    # Demarrer test (attendre connexion prete)
    await messages_thread.attendre_pret()

    logger.info("emettre notifications")

    await emettre_notifications(messages_thread, notifications)

    stop_event.set()

    logger.info("Fin main()")


async def emettre_notifications(messages_thread, notifications: EmetteurNotifications):
    producer = messages_thread.get_producer()
    contenu = """
    <p>Message de notification</p>
    <p>Check bein ca!</p>
    """
    await notifications.emettre_notification(producer, contenu, 'Un test de notifications')
    await notifications.emettre_notification(producer, contenu, 'Un test de notifications 2')
    await notifications.emettre_notification(producer, contenu, 'Un test de notifications 3')


async def callback_reply_q(message, messages_module):
    logger.info("Message recu : %s" % message)
    # wait_event.wait(0.7)


if __name__ == '__main__':
    logging.basicConfig(format=LOGGING_FORMAT, level=logging.WARN)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)
    logging.getLogger('millegrilles_messages.messages').setLevel(logging.DEBUG)

    asyncio.run(main())
