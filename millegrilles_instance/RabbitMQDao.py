from asyncio import Event

from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_messages.messages import Constantes


class RabbitMQDao:

    def __init__(self, event_stop: Event, etat_instance: EtatInstance):
        self.__event_stop = event_stop
        self.__etat_instance = etat_instance

    async def run(self):

        # reply_res = RessourcesConsommation(callback_reply_q)
        # q1 = RessourcesConsommation(callback_q_1, 'CoreBackup/tada')
        # q1.ajouter_rk('3.protege', 'commande.CoreBackup.m1')
        # q1.ajouter_rk('2.prive', 'commande.CoreBackup.m2')

        env_configuration = {
            Constantes.ENV_CA_PEM: self.__etat_instance.configuration.instance_ca_pem_path,
            Constantes.ENV_CERT_PEM: self.__etat_instance.configuration.instance_cert_pem_path,
            Constantes.ENV_KEY_PEM: self.__etat_instance.configuration.instance_key_pem_path,
            Constantes.ENV_REDIS_PASSWORD_PATH: self.__etat_instance.configuration.redis_key_path,
            Constantes.ENV_MQ_HOSTNAME: '127.0.0.1',
            Constantes.ENV_MQ_PORT: '5673',
            Constantes.ENV_REDIS_HOSTNAME: '127.0.0.1',
        }

        messages_thread = MessagesThread(self.__event_stop)
        messages_thread.set_env_configuration(env_configuration)

        # messages_thread.set_reply_ressources(reply_res)
        # messages_thread.ajouter_consumer(q1)

        # Demarrer traitement messages
        await messages_thread.start_async()
        fut_run = messages_thread.run_async()

        await fut_run
        # return fut_run

