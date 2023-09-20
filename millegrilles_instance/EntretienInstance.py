# Module d'entretien de l'instance protegee
import asyncio
import datetime
import json
import logging

from os import path, makedirs, listdir
from typing import Optional, Union

from asyncio import Event, TimeoutError

from millegrilles_messages.docker.Entretien import TacheEntretien
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance.EntretienNginx import EntretienNginx
from millegrilles_instance.EntretienRabbitMq import EntretienRabbitMq
from millegrilles_instance.RabbitMQDao import RabbitMQDao
from millegrilles_instance.EntretienCatalogues import EntretienCatalogues
from millegrilles_instance.EntretienApplications import GestionnaireApplications
from millegrilles_instance.Certificats import generer_certificats_modules, generer_passwords, \
    nettoyer_configuration_expiree, generer_certificats_modules_satellites

logger = logging.getLogger(__name__)

TachesEntretienType = list[TacheEntretien]


def get_module_execution(etat_instance: EtatInstance):
    securite = etat_instance.niveau_securite

    # Determiner si on a un certificat d'instance et s'il est expire
    try:
        clecert = etat_instance.clecertificat
        expiration = clecert.enveloppe.calculer_expiration()
    except AttributeError:
        expiration = None  # Pas de certificat

    if securite == Constantes.SECURITE_SECURE:
        if expiration is None or expiration.get('expire') is True:
            if etat_instance.docker_present is True:
                return InstanceDockerCertificatSecureExpire()
            else:
                return InstanceCertificatSecureExpire()
        elif etat_instance.docker_present is True:
            return InstanceSecureDocker()
        return InstanceSecure()
    if securite == Constantes.SECURITE_PROTEGE:
        if expiration is None or expiration.get('expire') is True:
            return InstanceDockerCertificatProtegeExpire()
        return InstanceProtegee()
    elif securite == Constantes.SECURITE_PRIVE:
        if expiration is None or expiration.get('expire') is True:
            return InstanceCertificatExpire()
        elif etat_instance.docker_present is True:
            return InstancePriveeDocker()
        else:
            return InstancePrivee()
    elif securite == Constantes.SECURITE_PUBLIC:
        if expiration is None or expiration.get('expire') is True:
            return InstanceCertificatExpire()
        elif etat_instance.docker_present is True:
            return InstancePubliqueDocker()
        else:
            raise Exception("Type d'instance non supporte (public/sans docker)")
    elif etat_instance.docker_present is True:
        # Si docker est actif, on demarre les services de base (certissuer, acme, nginx) pour
        # supporter l'instance protegee
        return InstanceInstallationAvecDocker()

    return InstanceInstallation()


CONFIG_MODULES_INSTALLATION = [
    'docker.certissuer.json',
    'docker.acme.json',
]


CONFIG_MODULES_SECURE_EXPIRE = [
    'docker.certissuer.json',
]


CONFIG_CERTIFICAT_EXPIRE = [
]


CONFIG_MODULES_SECURES = [
    'docker.certissuer.json',
    'docker.acme.json',
    'docker.nginx.json',
    'docker.redis.json',
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


CONFIG_MODULES_PRIVES = [
    'docker.nginx.json',
    'docker.redis.json',
    'docker.acme.json',
]


CONFIG_MODULES_PUBLICS = [
    'docker.nginx.json',
    'docker.redis.json',
    'docker.acme.json',
]


class InstanceAbstract:
    """
    Instance sans docker. Utilise pour installation, renouvellement certificat et instance privee sans docker.
    """

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None

        self._event_entretien: Optional[Event] = None
        self._taches_entretien = TachesEntretienType()

        self._gestionnaire_applications: Optional[GestionnaireApplications] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync] = None):
        self.__logger.info("Setup InstanceInstallation")
        self._event_stop = etat_instance.stop_event
        self._event_entretien = Event()
        self._etat_instance = etat_instance

        #setup_dir_apps(etat_instance)

        # Entretien etat_instance (certificats cache du validateur)
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=30), self._etat_instance.entretien, self.get_producer))

        # Ajouter listener de changement de configuration. Demarre l'execution des taches d'entretien/installation.
        self._etat_instance.ajouter_listener(self.declencher_run)

    async def get_producer(self, timeout=5):
        if self._gestionnaire_applications is None:
            return
        return await self._gestionnaire_applications.get_producer(timeout)

    async def fermer(self):
        self.__logger.info("Fermerture InstanceInstallation")
        self._etat_instance.retirer_listener(self.declencher_run)
        self._event_stop.set()
        self._event_entretien.set()

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
        self._event_stop = self._etat_instance.stop_event
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

        await self.fermer()
        self.__logger.info("Fin run()")

    def get_config_modules(self) -> list:
        raise NotImplementedError()

    async def get_configuration_certificats(self) -> dict:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        config_modules = self.get_config_modules()
        configurations = await charger_configuration_docker(path_configuration_docker, config_modules)
        configurations_apps = await charger_configuration_application(path_configuration_docker)
        configurations.extend(configurations_apps)

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

    async def start_mq(self):
        stop_event = self._event_stop
        messages_thread = MessagesThread(stop_event)

        # Demarrer traitement messages
        await messages_thread.start_async()
        fut_run = messages_thread.run_async()

        return fut_run

    def sauvegarder_nginx_data(self, nom_fichier: str, contenu: Union[bytes, str, dict], path_html=False):
        pass  # Aucun effet sans docker


class InstanceInstallation(InstanceAbstract):

    def get_config_modules(self) -> list:
        return list()


class InstanceDockerAbstract:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None
        self._gestionnaire_applications: Optional[GestionnaireApplications] = None

        self._event_entretien: Optional[Event] = None
        self._taches_entretien = TachesEntretienType()

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceInstallation")
        self._event_stop = etat_instance.stop_event
        self._event_entretien = Event()
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        self._gestionnaire_applications = GestionnaireApplications(etat_instance, etat_docker)

        # Entretien etat_instance (certificats cache du validateur)
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=30), self._etat_instance.entretien, self.get_producer))

        self._etat_instance.set_producer(self.get_producer)
        self._etat_instance.generateur_certificats.set_configuration_modules_getter(self.get_configuration_certificats)

        # Ajouter listener de changement de configuration. Demarre l'execution des taches d'entretien/installation.
        self._etat_instance.ajouter_listener(self.declencher_run)

        await etat_docker.initialiser_docker()

    async def get_producer(self, timeout=5):
        if self._gestionnaire_applications is None:
            return
        return await self._gestionnaire_applications.get_producer(timeout)

    async def fermer(self):
        self.__logger.info("Fermerture InstanceInstallation")
        self._etat_instance.retirer_listener(self.declencher_run)
        self._event_stop.set()
        self._event_entretien.set()

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
        self._event_stop = self._etat_instance.stop_event
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

        await self.fermer()
        self.__logger.info("Fin run()")

    def get_config_modules(self) -> list:
        raise NotImplementedError()

    async def get_configuration_services(self) -> dict:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = path.join(path_configuration, 'docker')
        configurations = await charger_configuration_docker(path_configuration_docker, self.get_config_modules())
        configurations_apps = await charger_configuration_application(path_configuration_docker)
        configurations.extend(configurations_apps)

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
        config_modules = self.get_config_modules()
        configurations = await charger_configuration_docker(path_configuration_docker, config_modules)
        configurations_apps = await charger_configuration_application(path_configuration_docker)
        configurations.extend(configurations_apps)

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
            #setup_catalogues(self._etat_instance)
            self.__setup_catalogues_complete = True

    async def entretien_applications(self):
        if self._gestionnaire_applications is not None:
            await self._gestionnaire_applications.entretien()

    async def start_mq(self):
        stop_event = self._event_stop
        messages_thread = MessagesThread(stop_event)

        # Demarrer traitement messages
        await messages_thread.start_async()
        fut_run = messages_thread.run_async()

        return fut_run


class InstanceInstallationAvecDocker(InstanceDockerAbstract):

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
        makedirs(path_nginx_html, 0o755, exist_ok=True)
        # path_certissuer = self._etat_instance.configuration.path_certissuer
        # makedirs(path_certissuer, 0o700, exist_ok=True)



class InstanceDockerCertificatProtegeExpire(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceCertificatProtegeExpire")
        await super().setup(etat_instance, etat_docker)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_INSTALLATION


class InstanceDockerCertificatSecureExpire(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceDockerCertificatSecureExpire")
        await super().setup(etat_instance, etat_docker)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_SECURE_EXPIRE


class InstanceCertificatExpire(InstanceInstallation):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker=None):
        self.__logger.info("Setup InstanceCertificatExpire")
        await super().setup(etat_instance)

    def get_config_modules(self) -> list:
        return CONFIG_CERTIFICAT_EXPIRE


class InstanceCertificatSecureExpire(InstanceCertificatExpire):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker=None):
        self.__logger.info("Setup InstanceCertificatSecureExpire")
        await super().setup(etat_instance)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_SECURE_EXPIRE


class InstanceProtegee(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            TacheEntretien(datetime.timedelta(minutes=60), self.entretien_catalogues),
            TacheEntretien(datetime.timedelta(days=1), self.docker_initialisation),
            # TacheEntretien(datetime.timedelta(minutes=2), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_nginx),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_mq),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_applications),
        ]
        self._taches_entretien.extend(taches_entretien)

        # self.__client_session = aiohttp.ClientSession()

        # self.__event_setup_initial_certificats: Optional[Event] = None
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

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)
        self.__entretien_rabbitmq = EntretienRabbitMq(etat_instance)
        self.__entretien_catalogues = EntretienCatalogues(etat_instance)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, self._etat_docker,
                                          self._gestionnaire_applications)

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        # self.__event_setup_initial_certificats.clear()
        self.__event_setup_initial_passwords.clear()

        await self._etat_docker.redemarrer_nginx()

        await super().declencher_run(etat_instance)

    async def fermer(self):
        await super().fermer()
        # self.__event_setup_initial_certificats.set()
        self.__event_setup_initial_passwords.set()

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

    # async def entretien_certificats(self):
    #     self.__logger.debug("entretien_certificats debut")
    #
    #     # Verifier certificat d'instance
    #     # enveloppe_instance = self._etat_instance.clecertificat.enveloppe
    #     # expiration_instance = enveloppe_instance.calculer_expiration()
    #     # if expiration_instance['expire'] is True:
    #     #     self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
    #     #     # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
    #     #     await self._etat_instance.stop()
    #     # elif expiration_instance['renouveler'] is True:
    #     # #else:
    #     #     self.__logger.info("Certificat d'instance peut etre renouvele")
    #     #     producer = self.__rabbitmq_dao.get_producer()
    #     #     clecertificat = await renouveler_certificat_instance_protege(producer,
    #     #                                                                  self._etat_instance.client_session,
    #     #                                                                  self._etat_instance)
    #     #     # Sauvegarder nouveau certificat
    #     #     path_secrets = self._etat_instance.configuration.path_secrets
    #     #     nom_certificat = 'pki.instance.cert'
    #     #     nom_cle = 'pki.instance.key'
    #     #     path_certificat = path.join(path_secrets, nom_certificat)
    #     #     path_cle = path.join(path_secrets, nom_cle)
    #     #     cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
    #     #     with open(path_cle, 'wb') as fichier:
    #     #         fichier.write(clecertificat.private_key_bytes())
    #     #     with open(path_certificat, 'w') as fichier:
    #     #         fichier.write(cert_str)
    #     #
    #     #     # Reload configuration avec le nouveau certificat
    #     #     await self._etat_instance.reload_configuration()
    #
    #     configuration = await self.get_configuration_certificats()
    #     producer = self.__rabbitmq_dao.get_producer()
    #     await generer_certificats_modules(producer, self._etat_instance.client_session, self._etat_instance,
    #                                       configuration, self._etat_docker)
    #     await nettoyer_configuration_expiree(self._etat_docker)
    #     self.__logger.debug("entretien_certificats fin")
    #     # self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, self._etat_docker, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_services(self):
        self.__logger.debug("entretien_services attente certificats et passwords")
        await asyncio.wait_for(self._etat_instance.generateur_certificats.event_entretien_initial.wait(), 50)
        await asyncio.wait_for(self.__event_setup_initial_passwords.wait(), 10)

        await super().entretien_services()

    async def entretien_nginx(self):
        if self.__entretien_nginx:
            producer = self.__rabbitmq_dao.get_producer()
            await self.__entretien_nginx.entretien(producer)

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

        await self._etat_docker.emettre_presence(producer)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_PROTEGES

    def ajouter_fichier_configuration(self, nom_fichier: str, contenu: str, params: Optional[dict] = None):
        self.__entretien_nginx.ajouter_fichier_configuration(nom_fichier, contenu, params)

    def sauvegarder_nginx_data(self, nom_fichier: str, contenu: Union[bytes, str, dict], path_html=False):
        self.__entretien_nginx.sauvegarder_fichier_data(nom_fichier, contenu, path_html)


class InstanceSecureDocker(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            TacheEntretien(datetime.timedelta(days=1), self.docker_initialisation),
            # TacheEntretien(datetime.timedelta(minutes=2), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_applications),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_nginx),
        ]
        self._taches_entretien.extend(taches_entretien)

        # self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_nginx: Optional[EntretienNginx] = None
        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceSecureDocker")
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()
        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, self._etat_docker,
                                          self._gestionnaire_applications)

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        # self.__event_setup_initial_certificats.clear()
        self.__event_setup_initial_passwords.clear()

        await self._etat_docker.redemarrer_nginx()

        await super().declencher_run(etat_instance)

    async def fermer(self):
        await super().fermer()
        # self.__event_setup_initial_certificats.set()
        self.__event_setup_initial_passwords.set()

    async def run(self):
        self.__logger.info("run()")

        tasks = [
            asyncio.create_task(super().run()),
            asyncio.create_task(self.__rabbitmq_dao.run())
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

    # async def entretien_certificats(self):
    #     self.__logger.debug("entretien_certificats debut")
    #
    #     # Verifier certificat d'instance
    #     # enveloppe_instance = self._etat_instance.clecertificat.enveloppe
    #     # expiration_instance = enveloppe_instance.calculer_expiration()
    #     # if expiration_instance['expire'] is True:
    #     #     self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
    #     #     # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
    #     #     await self._etat_instance.stop()
    #     # elif expiration_instance['renouveler'] is True:
    #     #     self.__logger.info("Certificat d'instance peut etre renouvele")
    #     #     producer = self.__rabbitmq_dao.get_producer()
    #     #     clecertificat = await renouveler_certificat_instance_protege(producer,
    #     #                                                                  self._etat_instance.client_session,
    #     #                                                                  self._etat_instance)
    #     #     # Sauvegarder nouveau certificat
    #     #     path_secrets = self._etat_instance.configuration.path_secrets
    #     #     nom_certificat = 'pki.instance.cert'
    #     #     nom_cle = 'pki.instance.key'
    #     #     path_certificat = path.join(path_secrets, nom_certificat)
    #     #     path_cle = path.join(path_secrets, nom_cle)
    #     #     cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
    #     #     with open(path_cle, 'wb') as fichier:
    #     #         fichier.write(clecertificat.private_key_bytes())
    #     #     with open(path_certificat, 'w') as fichier:
    #     #         fichier.write(cert_str)
    #     #
    #     #     # Reload configuration avec le nouveau certificat
    #     #     await self._etat_instance.reload_configuration()
    #
    #     configuration = await self.get_configuration_certificats()
    #     producer = self.__rabbitmq_dao.get_producer()
    #     await generer_certificats_modules(producer, self._etat_instance.client_session, self._etat_instance, configuration, self._etat_docker)
    #     self.__logger.debug("entretien_certificats fin")
    #     # self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, self._etat_docker, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_services(self):
        self.__logger.debug("entretien_services attente certificats et passwords")
        # await asyncio.wait_for(self.__event_setup_initial_certificats.wait(), 50)
        await asyncio.wait_for(self.__event_setup_initial_passwords.wait(), 10)

        await super().entretien_services()

    async def entretien_topologie(self):
        """
        Emet information sur instance, applications installees vers MQ.
        :return:
        """
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            self.__logger.debug("entretien_topologie Producer MQ non disponible")
            return

        await self._etat_docker.emettre_presence(producer)

    async def entretien_nginx(self):
        if self.__entretien_nginx:
            producer = self.__rabbitmq_dao.get_producer()
            await self.__entretien_nginx.entretien(producer)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_SECURES

    def sauvegarder_nginx_data(self, nom_fichier: str, contenu: Union[bytes, str, dict], path_html=False):
        self.__entretien_nginx.sauvegarder_fichier_data(nom_fichier, contenu, path_html)


class InstancePriveeDocker(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            TacheEntretien(datetime.timedelta(days=1), self.docker_initialisation),
            # TacheEntretien(datetime.timedelta(minutes=2), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_services),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_nginx),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_applications),
        ]
        self._taches_entretien.extend(taches_entretien)

        # self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_nginx: Optional[EntretienNginx] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, self._etat_docker,
                                          self._gestionnaire_applications)

    async def declencher_run(self, etat_instance: Optional[EtatInstance]):
        """
        Declence immediatement l'execution de l'entretien. Utile lors de changement de configuration.
        :return:
        """
        # self.__event_setup_initial_certificats.clear()
        self.__event_setup_initial_passwords.clear()

        await self._etat_docker.redemarrer_nginx()

        await super().declencher_run(etat_instance)

    async def fermer(self):
        await super().fermer()
        # self.__event_setup_initial_certificats.set()
        self.__event_setup_initial_passwords.set()

    async def run(self):
        self.__logger.info("run()")

        tasks = [
            asyncio.create_task(super().run()),
            asyncio.create_task(self.__rabbitmq_dao.run())
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

    async def entretien_certificats(self):
        self.__logger.debug("entretien_certificats debut")

        # if self.__event_setup_initial_certificats.is_set() is False:
        #     # Ajouter attente d'initialisation thread RabbitMQ
        #     await asyncio.sleep(3)

        await self.__rabbitmq_dao.attendre_pret(10)
        producer = self.__rabbitmq_dao.get_producer()

        # Verifier certificat d'instance
        # enveloppe_instance = self._etat_instance.clecertificat.enveloppe
        # expiration_instance = enveloppe_instance.calculer_expiration()
        # if expiration_instance['expire'] is True:
        #     self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
        #     # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
        #     await self._etat_instance.stop()
        # elif expiration_instance['renouveler'] is True:
        #     # else:
        #     self.__logger.info("Certificat d'instance peut etre renouvele")
        #     await renouveler_certificat_satellite(producer, self._etat_instance)
        #     # Redemarrer instance
        #     self._etat_instance.set_redemarrer(True)
        #     await self._etat_instance.reload_configuration()

        if producer is not None:
            configuration = await self.get_configuration_certificats()
            await generer_certificats_modules_satellites(producer, self._etat_instance, None, configuration)
            self.__logger.debug("entretien_certificats fin")
            # self.__event_setup_initial_certificats.set()
        else:
            self.__logger.info("entretien_certificats() Producer MQ n'est pas pret, skip entretien")

        configuration = await self.get_configuration_certificats()
        producer = self.__rabbitmq_dao.get_producer()
        await generer_certificats_modules_satellites(producer, self._etat_instance, self._etat_docker, configuration)
        await nettoyer_configuration_expiree(self._etat_docker)
        self.__logger.debug("entretien_certificats fin")
        # self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, self._etat_docker, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_services(self):
        self.__logger.debug("entretien_services attente certificats et passwords")
        # await asyncio.wait_for(self.__event_setup_initial_certificats.wait(), 50)
        await asyncio.wait_for(self.__event_setup_initial_passwords.wait(), 10)

        await super().entretien_services()

    async def entretien_nginx(self):
        if self.__entretien_nginx:
            producer = self.__rabbitmq_dao.get_producer()
            await self.__entretien_nginx.entretien(producer)

    async def entretien_topologie(self):
        """
        Emet information sur instance, applications installees vers MQ.
        :return:
        """
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            self.__logger.debug("entretien_topologie Producer MQ non disponible")
            return

        await self._etat_docker.emettre_presence(producer)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_PRIVES

    def ajouter_fichier_configuration(self, nom_fichier: str, contenu: str, params: Optional[dict] = None):
        self.__entretien_nginx.ajouter_fichier_configuration(nom_fichier, contenu, params)

    def sauvegarder_nginx_data(self, nom_fichier: str, contenu: Union[bytes, str, dict], path_html=False):
        self.__entretien_nginx.sauvegarder_fichier_data(nom_fichier, contenu, path_html)


class InstancePubliqueDocker(InstancePriveeDocker):

    def __init__(self):
        super().__init__()


class InstancePrivee(InstanceAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            # TacheEntretien(datetime.timedelta(minutes=2), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_applications),
        ]
        self._taches_entretien.extend(taches_entretien)

        # self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_nginx: Optional[EntretienNginx] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync]=None):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)

        self._gestionnaire_applications = GestionnaireApplications(etat_instance, etat_docker)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, None,
                                          self._gestionnaire_applications)

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

        tasks = [
            asyncio.create_task(super().run()),
            asyncio.create_task(self.__rabbitmq_dao.run())
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

    def get_config_modules(self) -> list:
        return list()

    async def entretien_applications(self):
        if self._gestionnaire_applications is not None:
            await self._gestionnaire_applications.entretien()

    async def entretien_certificats(self):
        self.__logger.debug("entretien_certificats debut")

        # if self.__event_setup_initial_certificats.is_set() is False:
        #     # Ajouter attente d'initialisation thread RabbitMQ
        #     await asyncio.sleep(3)

        await self.__rabbitmq_dao.attendre_pret(10)
        producer = self.__rabbitmq_dao.get_producer()

        # Verifier certificat d'instance
        # enveloppe_instance = self._etat_instance.clecertificat.enveloppe
        # expiration_instance = enveloppe_instance.calculer_expiration()
        # if expiration_instance['expire'] is True:
        #     self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
        #     # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
        #     await self._etat_instance.stop()
        # elif expiration_instance['renouveler'] is True:
        # # else:
        #     self.__logger.info("Certificat d'instance peut etre renouvele")
        #     await renouveler_certificat_satellite(producer, self._etat_instance)
        #     # Redemarrer instance
        #     self._etat_instance.set_redemarrer(True)
        #     await self._etat_instance.reload_configuration()
        #
        # if producer is not None:
        #     configuration = await self.get_configuration_certificats()
        #     await generer_certificats_modules_satellites(producer, self._etat_instance, None, configuration)
        #     self.__logger.debug("entretien_certificats fin")
        #     self.__event_setup_initial_certificats.set()
        # else:
        #     self.__logger.info("entretien_certificats() Producer MQ n'est pas pret, skip entretien")

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, None, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_topologie(self):
        """
        Emet information sur instance, applications installees vers MQ.
        :return:
        """
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            self.__logger.debug("entretien_topologie Producer MQ non disponible")
            return

        await self._etat_instance.emettre_presence(producer)


class InstanceSecure(InstanceAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        taches_entretien = [
            # TacheEntretien(datetime.timedelta(minutes=2), self.entretien_certificats),
            TacheEntretien(datetime.timedelta(minutes=360), self.entretien_passwords),
            TacheEntretien(datetime.timedelta(seconds=120), self.entretien_topologie),
            TacheEntretien(datetime.timedelta(seconds=30), self.entretien_applications),
        ]
        self._taches_entretien.extend(taches_entretien)

        # self.__event_setup_initial_certificats: Optional[Event] = None
        self.__event_setup_initial_passwords: Optional[Event] = None
        self.__entretien_nginx: Optional[EntretienNginx] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync] = None):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = EntretienNginx(etat_instance, etat_docker)

        self._gestionnaire_applications = GestionnaireApplications(etat_instance, etat_docker)

        await super().setup(etat_instance, etat_docker)

        self.__rabbitmq_dao = RabbitMQDao(self._event_stop, self, self._etat_instance, None,
                                          self._gestionnaire_applications)

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

        tasks = [
            asyncio.create_task(super().run()),
            asyncio.create_task(self.__rabbitmq_dao.run())
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)

    def get_config_modules(self) -> list:
        return list()

    async def entretien_applications(self):
        if self._gestionnaire_applications is not None:
            await self._gestionnaire_applications.entretien()

    # async def entretien_certificats(self):
    #     self.__logger.debug("entretien_certificats debut")
    #
    #     # Verifier certificat d'instance
    #     # enveloppe_instance = self._etat_instance.clecertificat.enveloppe
    #     # expiration_instance = enveloppe_instance.calculer_expiration()
    #     # if expiration_instance['expire'] is True:
    #     #     self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
    #     #     # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
    #     #     await self._etat_instance.stop()
    #     # #elif expiration_instance['renouveler'] is True:
    #     # else:
    #     #     self.__logger.fatal(' **** DEBUG **** ')
    #     #     self.__logger.info("Certificat d'instance peut etre renouvele")
    #     #     producer = self.__rabbitmq_dao.get_producer()
    #     #     clecertificat = await renouveler_certificat_instance_protege(producer,
    #     #                                                                  self._etat_instance.client_session,
    #     #                                                                  self._etat_instance)
    #     #     # Sauvegarder nouveau certificat
    #     #     path_secrets = self._etat_instance.configuration.path_secrets
    #     #     nom_certificat = 'pki.instance.cert'
    #     #     nom_cle = 'pki.instance.key'
    #     #     path_certificat = path.join(path_secrets, nom_certificat)
    #     #     path_cle = path.join(path_secrets, nom_cle)
    #     #     cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
    #     #     with open(path_cle, 'wb') as fichier:
    #     #         fichier.write(clecertificat.private_key_bytes())
    #     #     with open(path_certificat, 'w') as fichier:
    #     #         fichier.write(cert_str)
    #     #
    #     #     # Reload configuration avec le nouveau certificat
    #     #     await self._etat_instance.reload_configuration()
    #
    #     configuration = await self.get_configuration_certificats()
    #     producer = self.__rabbitmq_dao.get_producer()
    #     await generer_certificats_modules(producer, self._etat_instance.client_session, self._etat_instance, configuration, None)
    #     self.__logger.debug("entretien_certificats fin")
    #     self.__event_setup_initial_certificats.set()

    async def entretien_passwords(self):
        self.__logger.debug("entretien_passwords debut")
        liste_noms_passwords = await self.get_configuration_passwords()
        await generer_passwords(self._etat_instance, None, liste_noms_passwords)
        self.__logger.debug("entretien_passwords fin")
        self.__event_setup_initial_passwords.set()

    async def entretien_topologie(self):
        """
        Emet information sur instance, applications installees vers MQ.
        :return:
        """
        producer = self.__rabbitmq_dao.get_producer()
        if producer is None:
            self.__logger.debug("entretien_topologie Producer MQ non disponible")
            return

        await self._etat_instance.emettre_presence(producer)


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


async def charger_configuration_application(path_configuration: str) -> list:
    configuration = []
    try:
        filenames = listdir(path_configuration)
    except FileNotFoundError:
        # Aucune configuration
        return list()

    for filename in filenames:
        if filename.startswith('app.'):
            path_fichier = path.join(path_configuration, filename)
            try:
                with open(path_fichier, 'rb') as fichier:
                    contenu = json.load(fichier)

                deps = contenu['dependances']

                configuration.extend(deps)
            except FileNotFoundError:
                logger.error("Fichier de module manquant : %s" % path_fichier)

    return configuration


# def setup_catalogues(etat_instance: EtatInstance):
#     setup_dir_apps(etat_instance)
#
#     path_configuration = etat_instance.configuration.path_configuration
#     path_docker_catalogues = path.join(path_configuration, 'docker')
#
#     repertoire_src_catalogues = path.abspath('../etc/docker')
#     for fichier in listdir(repertoire_src_catalogues):
#         path_fichier_src = path.join(repertoire_src_catalogues, fichier)
#         path_fichier_dest = path.join(path_docker_catalogues, fichier)
#         if path.exists(path_fichier_dest) is False:
#             with open(path_fichier_src, 'r') as fichier_src:
#                 with open(path_fichier_dest, 'w') as fichier_dest:
#                     fichier_dest.write(fichier_src.read())
#
#
# def setup_dir_apps(etat_instance: EtatInstance):
#     path_configuration = etat_instance.configuration.path_configuration
#     path_docker_catalogues = path.join(path_configuration, 'docker')
#     makedirs(path_docker_catalogues, 0o750, exist_ok=True)
