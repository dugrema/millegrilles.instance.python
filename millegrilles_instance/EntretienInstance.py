# Module d'entretien de l'instance protegee
import aiohttp
import asyncio
import base64
import datetime
import json
import logging
import secrets

from os import path, stat, makedirs, listdir
from typing import Optional

from aiohttp import ClientSession
from asyncio import Event, TimeoutError

from millegrilles_messages.docker.Entretien import TacheEntretien
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_messages.messages.MessagesModule import RessourcesConsommation
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance.EntretienNginx import EntretienNginx
from millegrilles_instance.EntretienRabbitMq import EntretienRabbitMq
from millegrilles_instance.RabbitMQDao import RabbitMQDao
from millegrilles_instance.EntretienCatalogues import EntretienCatalogues
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_instance.CommandesDocker import CommandeListeTopologie

logger = logging.getLogger(__name__)

TachesEntretienType = list[TacheEntretien]


def get_module_execution(etat_instance: EtatInstance):
    securite = etat_instance.niveau_securite

    if securite == Constantes.SECURITE_PROTEGE:
        return InstanceProtegee()
    elif etat_instance.docker_present is True:
        # Si docker est actif, on demarre les services de base (certissuer, acme, nginx) pour
        # supporter l'instance protegee
        return InstanceInstallation()

    return None


CONFIG_MODULES_INSTALLATION = [
    'docker.certissuer.json',
    'docker.acme.json',
    # 'docker.nginx.json',
]


CONFIG_MODULES_PROTEGES = [
    'docker.certissuer.json',
    'docker.acme.json',
    'docker.nginx.json',
    'docker.redis.json',
    'docker.mq.json',
    'docker.mongo.json',
    'docker.midcompte.json',
    'docker.core.json',
    'docker.maitrecomptes.json',
    'docker.coupdoeil.json',
]


class InstanceAbstract:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

        self._event_entretien: Optional[Event] = None
        self._taches_entretien = TachesEntretienType()

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceInstallation")
        self._event_stop = Event()
        self._event_entretien = Event()
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        # Ajouter listener de changement de configuration. Demarre l'execution des taches d'entretien/installation.
        self._etat_instance.ajouter_listener(self.declencher_run)

        await etat_docker.initialiser_docker()

    async def fermer(self):
        self.__logger.info("Fermerture InstanceInstallation")
        self._etat_instance.retirer_listener(self.declencher_run)
        self._event_stop.set()

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        for tache in self._taches_entretien:
            tache.reset()

        # Declencher l'entretien
        self._event_entretien.set()

    async def run(self):
        self.__logger.info("run()")
        while self._event_stop.is_set() is False:
            self.__logger.debug("run() debut execution cycle")

            for tache in self._taches_entretien:
                try:
                    await tache.run()
                except:
                    self.__logger.exception("Erreur execution tache entretien")

            try:
                self.__logger.debug("run() fin execution cycle")
                await asyncio.wait_for(self._event_entretien.wait(), 30)
                self._event_entretien.clear()
            except TimeoutError:
                pass
        self.__logger.info("Fin run()")

    def get_config_modules(self) -> list:
        raise NotImplementedError()

    async def get_configuration_services(self) -> dict:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, self.get_config_modules())

        # map configuration certificat
        services = dict()
        for c in configurations:
            try:
                nom = c['name']
                services[nom] = c
            except KeyError:
                pass

        return services

    async def get_configuration_certificats(self) -> dict:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, CONFIG_MODULES_PROTEGES)

        # map configuration certificat
        config_certificats = dict()
        for c in configurations:
            try:
                certificat = c['certificat']
                nom = c['name']
                config_certificats[nom] = certificat
            except KeyError:
                pass

        return config_certificats

    async def get_configuration_passwords(self) -> list:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, CONFIG_MODULES_PROTEGES)

        # map configuration certificat
        liste_noms_passwords = list()
        for c in configurations:
            try:
                p = c['passwords']
                liste_noms_passwords.extend(p)
            except KeyError:
                pass

        return liste_noms_passwords

    async def docker_initialisation(self):
        self.__logger.debug("docker_initialisation debut")
        await self._etat_docker.initialiser_docker()
        self.__logger.debug("docker_initialisation fin")

    async def entretien_services(self):
        self.__logger.debug("entretien_services debut")
        services = await self.get_configuration_services()
        await self._etat_docker.entretien_services(services)
        self.__logger.debug("entretien_services fin")

    async def entretien_catalogues(self):
        if self.__setup_catalogues_complete is False:
            setup_catalogues(self._etat_instance)
            self.__setup_catalogues_complete = True

    async def start_mq(self):
        stop_event = self._event_stop

        # reply_res = RessourcesConsommation(callback_reply_q)
        # q1 = RessourcesConsommation(callback_q_1, 'CoreBackup/tada')
        # q1.ajouter_rk('3.protege', 'commande.CoreBackup.m1')
        # q1.ajouter_rk('2.prive', 'commande.CoreBackup.m2')

        messages_thread = MessagesThread(stop_event)
        # messages_thread.set_reply_ressources(reply_res)
        # messages_thread.ajouter_consumer(q1)

        # Demarrer traitement messages
        await messages_thread.start_async()
        fut_run = messages_thread.run_async()

        return fut_run

    async def emettre_presence(self, producer: MessageProducerFormatteur, info: Optional[dict] = None):
        self.__logger.info("Emettre presence")
        if info is not None:
            info_updatee = info.copy()
        else:
            info_updatee = dict()

        info_updatee['fqdn_detecte'] = self._etat_instance.hostname
        info_updatee['ip_detectee'] = self._etat_instance.ip_address
        info_updatee['instance_id'] = self._etat_instance.instance_id
        info_updatee['securite'] = self._etat_instance.niveau_securite

        await producer.emettre_evenement(info_updatee, Constantes.DOMAINE_INSTANCE,
                                         ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE,
                                         exchanges=Constantes.SECURITE_PROTEGE)


class InstanceInstallation(InstanceAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

        self._taches_entretien.append(TacheEntretien(datetime.timedelta(seconds=30), self.entretien_repertoires_installation))
        self._taches_entretien.append(TacheEntretien(datetime.timedelta(seconds=30), self.entretien_catalogues))
        self._taches_entretien.append(TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services))

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceInstallation")
        await super().setup(etat_instance, etat_docker)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_INSTALLATION

    async def entretien_repertoires_installation(self):
        path_nginx = self._etat_instance.configuration.path_nginx
        path_nginx_html = path.join(path_nginx, 'html')
        makedirs(path_nginx_html, 0o750, exist_ok=True)
        path_certissuer = self._etat_instance.configuration.path_certissuer
        makedirs(path_certissuer, 0o700, exist_ok=True)


class InstanceProtegee(InstanceAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            TacheEntretien(datetime.timedelta(minutes=60), self.entretien_catalogues),
            TacheEntretien(datetime.timedelta(days=1), self.docker_initialisation),
            TacheEntretien(datetime.timedelta(minutes=30), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_nginx),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_mq),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
        ]
        self._taches_entretien.extend(taches_entretien)

        self.__client_session = aiohttp.ClientSession()

        self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_nginx: Optional[EntretienNginx] = None
        self.__entretien_rabbitmq: Optional[EntretienRabbitMq] = None
        self.__entretien_catalogues: Optional[EntretienCatalogues] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)
        self.__entretien_rabbitmq = EntretienRabbitMq(etat_instance)
        self.__entretien_catalogues = EntretienCatalogues(etat_instance)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, self._etat_docker)

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        self.__event_setup_initial_certificats.clear()
        self.__event_setup_initial_passwords.clear()

        await self._etat_docker.redemarrer_nginx()

        await super().declencher_run(etat_instance)

    async def run(self):
        self.__logger.info("run()")

        tasks = [
            asyncio.create_task(super().run()),
            asyncio.create_task(self.__rabbitmq_dao.run())
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

    async def entretien_catalogues(self):
        # Tache de copier des fichiers .xz inclus localement pour coupdoeil
        await self.__entretien_catalogues.entretien()
        await super().entretien_catalogues()

    async def entretien_certificats(self):
        self.__logger.debug("entretien_certificats debut")
        configuration = await self.get_configuration_certificats()
        await generer_certificats_modules(self.__client_session, self._etat_instance, self._etat_docker,
                                          configuration)
        self.__logger.debug("entretien_certificats fin")
        self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, self._etat_docker, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_services(self):
        self.__logger.debug("entretien_services attente certificats et passwords")
        await asyncio.wait_for(self.__event_setup_initial_certificats.wait(), 50)
        await asyncio.wait_for(self.__event_setup_initial_passwords.wait(), 10)

        await super().entretien_services()

    async def entretien_nginx(self):
        if self.__entretien_nginx:
            await self.__entretien_nginx.entretien()

    async def entretien_mq(self):
        if self.__entretien_rabbitmq:
            await self.__entretien_rabbitmq.entretien()

    async def entretien_topologie(self):
        """
        Emet information sur instance, applications installees vers MQ.
        :return:
        """
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            self.__logger.debug("entretien_topologie Producer MQ non disponible")
            return

        commande = CommandeListeTopologie()
        self._etat_docker.ajouter_commande(commande)
        info_instance = parse_topologie_docker(await commande.get_info())

        await self.emettre_presence(producer, info_instance)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_PROTEGES

    async def get_liste_applications(self):
        pass


async def charger_configuration_docker(path_configuration: str, fichiers: list) -> list:
    configuration = []
    for filename in fichiers:
        path_fichier = path.join(path_configuration, filename)
        try:
            with open(path_fichier, 'rb') as fichier:
                contenu = json.load(fichier)
            configuration.append(contenu)
        except FileNotFoundError:
            logger.error("Fichier de module manquant : %s" % path_fichier)

    return configuration


async def generer_certificats_modules(client_session: ClientSession, etat_instance: EtatInstance,
                                      etat_docker: EtatDockerInstanceSync, configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_certificat = 'pki.%s.cert' % nom_module
        nom_cle = 'pki.%s.cle' % nom_module
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)
        combiner_keycert = value.get('combiner_keycert') or False

        sauvegarder = False
        try:
            clecertificat = CleCertificat.from_files(path_cle, path_certificat)
            enveloppe = clecertificat.enveloppe

            # Ok, verifier si le certificat doit etre renouvele
            detail_expiration = enveloppe.calculer_expiration()
            if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
                sauvegarder = True

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_module)
            clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
            sauvegarder = True

        # Verifier si le certificat et la cle sont stocke dans docker
        if sauvegarder is True:

            cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
            with open(path_cle, 'wb') as fichier:
                fichier.write(clecertificat.private_key_bytes())
                if combiner_keycert is True:
                    fichier.write(cert_str.encode('utf-8'))
            with open(path_certificat, 'w') as fichier:
                cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
                fichier.write(cert_str)

        await etat_docker.assurer_clecertificat(nom_module, clecertificat, combiner_keycert)


async def generer_nouveau_certificat(client_session: ClientSession, etat_instance: EtatInstance, nom_module: str,
                                     configuration: dict) -> CleCertificat:
    instance_id = etat_instance.instance_id
    idmg = etat_instance.certificat_millegrille.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = etat_instance.nom_domaine
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = etat_instance.formatteur_message
    message_signe, _uuid = formatteur_message.signer_message(configuration)

    logger.debug("Demande de signature de certificat pour %s => %s\n%s" % (nom_module, message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    async with client_session.post(path_csr, json=message_signe) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    logger.debug("Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
    return clecertificat


async def generer_passwords(etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync,
                            liste_noms_passwords: list):
    """
    Generer les passwords manquants.
    :param etat_instance:
    :param etat_docker:
    :param liste_noms_passwords:
    :return:
    """
    path_secrets = etat_instance.configuration.path_secrets
    configurations = await etat_docker.get_configurations_datees()
    secrets_dict = configurations['secrets']

    for nom_password in liste_noms_passwords:
        prefixe = 'passwd.%s' % nom_password
        path_password = path.join(path_secrets, prefixe + '.txt')

        try:
            with open(path_password, 'r') as fichier:
                password = fichier.read().strip()
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime
        except FileNotFoundError:
            # Fichier non trouve, on doit le creer
            password = base64.b64encode(secrets.token_bytes(24)).decode('utf-8').replace('=', '')
            with open(path_password, 'w') as fichier:
                fichier.write(password)
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime

        logger.debug("Date password : %s" % date_password)
        date_password = datetime.datetime.utcfromtimestamp(date_password)
        date_password_str = date_password.strftime('%Y%m%d%H%M%S')

        label_passord = '%s.%s' % (prefixe, date_password_str)
        try:
            secrets_dict[label_passord]
            continue  # Mot de passe existe
        except KeyError:
            pass  # Le mot de passe n'existe pas

        # Ajouter mot de passe
        await etat_docker.ajouter_password(nom_password, date_password_str, password)


def setup_catalogues(etat_instance: EtatInstance):
    path_configuration = etat_instance.configuration.path_configuration
    path_docker_catalogues = path.join(path_configuration, 'docker')
    makedirs(path_docker_catalogues, 0o750, exist_ok=True)

    repertoire_src_catalogues = path.abspath('../etc/docker')
    for fichier in listdir(repertoire_src_catalogues):
        path_fichier_src = path.join(repertoire_src_catalogues, fichier)
        path_fichier_dest = path.join(path_docker_catalogues, fichier)
        if path.exists(path_fichier_dest) is False:
            with open(path_fichier_src, 'r') as fichier_src:
                with open(path_fichier_dest, 'w') as fichier_dest:
                    fichier_dest.write(fichier_src.read())


def parse_topologie_docker(info: dict) -> dict:

    info_docker = info.copy()

    # try:
    #     configuration_acme = json.loads(gestionnaire_docker.charger_config('acme.configuration'))
    #     dict_infomillegrille['domaine'] = configuration_acme['domain']
    # except IndexError:
    #     pass
    #
    # try:
    #     securite = gestionnaire_docker.charger_config(ConstantesServiceMonitor.DOCKER_LIBVAL_CONFIG_SECURITE).decode(
    #         'utf-8').strip()
    #     dict_infomillegrille['securite'] = securite
    # except IndexError:
    #     pass
    #
    # try:
    #     hostname_onion = gestionnaire_docker.get_nginx_onionize_hostname()
    #     dict_infomillegrille['onion'] = hostname_onion
    # except:
    #     pass
    #
    # # Verifier si on a le certificat de monitor - indique que le noeud est installe
    # try:
    #     monitor_cert = gestionnaire_docker.charger_config_recente('pki.monitor.cert')
    #     monitor_cert = b64decode(monitor_cert['config'].attrs['Spec']['Data']).decode('utf-8')
    #     dict_infomillegrille['certificat'] = monitor_cert
    #     ca_cert = gestionnaire_docker.charger_config_recente('pki.millegrille.cert')
    #     ca_cert = b64decode(ca_cert['config'].attrs['Spec']['Data']).decode('utf-8')
    #     dict_infomillegrille['ca'] = ca_cert
    # except (IndexError, AttributeError):
    #     self.__logger.info("Certificat de monitor n'existe pas")
    #
    # if inclure_services:
    #     dict_infomillegrille['services'] = gestionnaire_docker.get_liste_services()
    #     dict_infomillegrille['containers'] = gestionnaire_docker.get_liste_containers()
    #
    # # Charger la liste des applications configurees (config app.cfg.*)
    # apps = gestionnaire_docker.charger_configs('app.cfg.')
    # config_apps = list()
    # for app in apps:
    #     app_config = json.loads(app['configuration'].decode('utf-8'))
    #     config_apps.append({'nom': app_config['nom'], 'version': app_config['version']})
    #
    # dict_infomillegrille['applications_configurees'] = config_apps

    return info_docker
