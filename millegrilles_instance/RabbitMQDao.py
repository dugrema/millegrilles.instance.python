import asyncio
import logging

from asyncio import Event
from typing import Optional

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation, MessageProducerFormatteur
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance.Commandes import CommandHandler
from millegrilles_messages.messages.MessagesModule import MessageWrapper
from millegrilles_instance.EntretienApplications import GestionnaireApplications


class MqThread:

    def __init__(self, event_stop: Event, etat_instance: EtatInstance, command_handler: CommandHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_stop = event_stop
        self.__etat_instance = etat_instance
        self.__command_handler = command_handler

        self.__mq_host: Optional[str] = None
        self.__messages_thread: Optional[MessagesThread] = None

    async def configurer(self):
        self.__mq_host = '127.0.0.1'

        env_configuration = {
            Constantes.ENV_CA_PEM: self.__etat_instance.configuration.instance_ca_pem_path,
            Constantes.ENV_CERT_PEM: self.__etat_instance.configuration.instance_cert_pem_path,
            Constantes.ENV_KEY_PEM: self.__etat_instance.configuration.instance_key_pem_path,
            Constantes.ENV_REDIS_PASSWORD_PATH: self.__etat_instance.configuration.redis_key_path,
            Constantes.ENV_MQ_HOSTNAME: self.__mq_host,
            Constantes.ENV_REDIS_HOSTNAME: self.__mq_host,
        }

        messages_thread = MessagesThread(self.__event_stop)
        messages_thread.set_env_configuration(env_configuration)
        self.creer_ressources_consommation(messages_thread)
        await messages_thread.start_async()  # Preparer le reste de l'environnement

        self.__messages_thread = messages_thread

    def creer_ressources_consommation(self, messages_thread: MessagesThread):
        instance_id = self.__etat_instance.instance_id
        niveau_securite = self.__etat_instance.niveau_securite
        reply_res = RessourcesConsommation(self.callback_reply_q)
        reply_res.ajouter_rk(niveau_securite, 'commande.instance.%s' % ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES)
        reply_res.ajouter_rk(niveau_securite, 'commande.instance.%s.%s' % (
            instance_id, ConstantesInstance.COMMANDE_APPLICATION_INSTALLER))
        reply_res.ajouter_rk(niveau_securite, 'commande.instance.%s.%s' % (
            instance_id, ConstantesInstance.COMMANDE_APPLICATION_SUPPRIMER))
        reply_res.ajouter_rk(niveau_securite, 'commande.instance.%s.%s' % (
            instance_id, ConstantesInstance.COMMANDE_APPLICATION_DEMARRER))
        reply_res.ajouter_rk(niveau_securite, 'commande.instance.%s.%s' % (
            instance_id, ConstantesInstance.COMMANDE_APPLICATION_ARRETER))

        # q1 = RessourcesConsommation(callback_q_1, 'CoreBackup/tada')

        messages_thread.set_reply_ressources(reply_res)
        # messages_thread.ajouter_consumer(q1)

    async def run(self):

        while not self.__event_stop.is_set():
            self.__logger.info("Debut thread asyncio MessagesThread")

            try:
                # coroutine principale d'execution MQ
                await self.__messages_thread.run_async()
            except Exception as e:
                self.__logger.exception("Erreur connexion MQ")

            # Attendre pour redemarrer execution module
            self.__logger.info("Fin thread asyncio MessagesThread, attendre 30 secondes pour redemarrer")
            try:
                await asyncio.wait_for(self.__event_stop.wait(), 30)
            except TimeoutError:
                pass

        self.__logger.info("Fin thread MessagesThread")

    async def callback_reply_q(self, message: MessageWrapper, module_messages):
        self.__logger.debug("RabbitMQ nessage recu : %s" % message)
        producer = self.__messages_thread.get_producer()
        reponse = await self.__command_handler.executer_commande(producer, message)

        if reponse is not None:
            reply_to = message.reply_to
            correlation_id = message.correlation_id
            producer = self.__messages_thread.get_producer()
            await producer.repondre(reponse, reply_to, correlation_id)

    def get_producer(self) -> Optional[MessageProducerFormatteur]:
        try:
            return self.__messages_thread.get_producer()
        except AttributeError:
            # Thread inactive
            return None


class RabbitMQDao:

    def __init__(self, event_stop: Event, entretien_instance, etat_instance: EtatInstance,
                 etat_docker: EtatDockerInstanceSync, gestionnaire_applications: GestionnaireApplications):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__event_stop = event_stop
        self.__entretien_instance = entretien_instance
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

        self.__command_handler = CommandHandler(entretien_instance, etat_instance, etat_docker,
                                                gestionnaire_applications)

        self.__mq_host: Optional[str] = None
        self.__producer: Optional[MessageProducerFormatteur] = None

    async def creer_thread(self):
        return MqThread(self.__event_stop, self.__etat_instance, self.__command_handler)

    def get_producer(self) -> Optional[MessageProducerFormatteur]:
        return self.__producer

    async def run(self):

        while not self.__event_stop.is_set():
            self.__logger.info("Debut thread asyncio MessagesThread")

            try:
                # Toujours tenter de creer le compte sur MQ - la detection n'est pas au point a l'interne
                resultat_creer_compte = await self.creer_compte_mq()
                self.__logger.info("Resultat creer compte MQ : %s" % resultat_creer_compte)

                # coroutine principale d'execution MQ
                mq_thread = await self.creer_thread()
                await mq_thread.configurer()
                self.__producer = mq_thread.get_producer()

                await mq_thread.run()
            except Exception as e:
                self.__logger.exception("Erreur connexion MQ")
            finally:
                self.__producer = None

            # Attendre pour redemarrer execution module
            self.__logger.info("Fin thread asyncio MessagesThread, attendre 30 secondes pour redemarrer")
            try:
                await asyncio.wait_for(self.__event_stop.wait(), 30)
            except TimeoutError:
                pass

        self.__logger.info("Fin thread MessagesThread")

    async def creer_compte_mq(self):
        """
        Creer un compte sur MQ via https (monitor).
        :return:
        """
        self.__logger.info("Creation compte MQ avec %s" % self.__mq_host)

        # Le monitor peut etre trouve via quelques hostnames :
        #  nginx : de l'interne, est le proxy web qui est mappe vers le monitor
        #  mq_host : de l'exterieur, est le serveur mq qui est sur le meme swarm docker que nginx
        hosts = ['nginx', self.__mq_host, self.__etat_instance.mq_hostname]
        port = 444  # 443
        path = 'administration/ajouterCompte'

        mq_cafile = self.__etat_instance.configuration.instance_ca_pem_path
        mq_certfile = self.__etat_instance.configuration.instance_cert_pem_path
        mq_keyfile = self.__etat_instance.configuration.instance_key_pem_path

        with open(mq_certfile, 'r') as fichier:
            chaine_cert = {'certificat': fichier.read()}

        cle_cert = (mq_certfile, mq_keyfile)
        self.__logger.debug("Creation compte MQ avec fichiers %s" % str(cle_cert))
        try:
            import requests
            for host in hosts:
                try:
                    path_complet = 'https://%s:%d/%s' % (host, port, path)
                    self.__logger.debug("Creation compte avec path %s" % path_complet)
                    reponse = requests.post(path_complet, json=chaine_cert, cert=cle_cert, verify=mq_cafile)
                    if reponse.status_code in [200, 201]:
                        return True
                    else:
                        self.__logger.error("Erreur creation compte MQ via https, code : %d", reponse.status_code)
                except requests.exceptions.SSLError as e:
                    self.__logger.exception("Erreur connexion https pour compte MQ")
                except requests.exceptions.ConnectionError:
                    # Erreur connexion au serveur, tenter le prochain host
                    self.__logger.info("Echec creation compte MQ avec %s" % path_complet)
        except ImportError:
            self.__logger.warning("requests non disponible, on ne peut pas tenter d'ajouter le compte MQ")

        return False

