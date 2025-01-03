# Module d'entretien de l'instance protegee
import asyncio
import datetime
import logging
import pathlib
import shutil

from os import path, makedirs
from typing import Optional, Union

from asyncio import Event, TimeoutError

from millegrilles_instance.MaintenanceApplicationWeb import entretien_webapps_installation
from millegrilles_instance.ModulesRequisInstance import CONFIG_MODULES_INSTALLATION, CONFIG_MODULES_SECURE_EXPIRE, \
    CONFIG_CERTIFICAT_EXPIRE, CONFIG_MODULES_SECURES, CONFIG_MODULES_PROTEGES, CONFIG_MODULES_PRIVES
from millegrilles_instance.millegrilles_docker.Entretien import TacheEntretien
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesThread import MessagesThread
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance.NginxHandler import NginxHandler, generer_configuration_nginx
from millegrilles_instance.EntretienRabbitMq import EntretienRabbitMq
from millegrilles_instance.RabbitMQDao import RabbitMQDao
from millegrilles_instance.EntretienCatalogues import EntretienCatalogues
from millegrilles_instance.MaintenanceApplications import ApplicationsHandler
from millegrilles_instance.Certificats import generer_passwords, \
    nettoyer_configuration_expiree, generer_certificats_modules_satellites
from millegrilles_instance.MaintenanceApplicationService import charger_configuration_docker, charger_configuration_application

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

        self._gestionnaire_applications: Optional[ApplicationsHandler] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync] = None):
        self.__logger.info("Setup InstanceInstallation")
        self._event_stop = etat_instance.stop_event
        self._event_entretien = Event()
        self._etat_instance = etat_instance

        #setup_dir_apps(etat_instance)
        self._etat_instance.set_producer(self.get_producer)

        # Entretien etat_instance (certificats cache du validateur)
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=30), self._etat_instance.entretien, self.get_producer))
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=5), self._etat_instance.check_delay_reload))

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
        path_configuration_docker = pathlib.Path(path_configuration, 'docker')
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
        path_configuration_docker = pathlib.Path(path_configuration, 'docker')
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
        self._gestionnaire_applications: Optional[ApplicationsHandler] = None

        self._event_entretien: Optional[Event] = None
        self._taches_entretien = TachesEntretienType()

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceInstallation")
        self._event_stop = etat_instance.stop_event
        self._event_entretien = Event()
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        self._gestionnaire_applications = ApplicationsHandler(etat_instance, etat_docker)

        # Entretien etat_instance (certificats cache du validateur)
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=30), self._etat_instance.entretien, self.get_producer))
        self._taches_entretien.append(TacheEntretien(
            datetime.timedelta(seconds=5), self._etat_instance.check_delay_reload))

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
                await asyncio.wait_for(self._event_entretien.wait(), 5)
                self._event_entretien.clear()
            except TimeoutError:
                pass

        await self.fermer()
        self.__logger.info("Fin run()")

    def get_config_modules(self) -> list:
        raise NotImplementedError()

    async def get_configuration_services(self) -> dict:
        path_configuration = self._etat_instance.configuration.path_configuration
        path_configuration_docker = pathlib.Path(path_configuration, 'docker')
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
        path_configuration_docker = pathlib.Path(path_configuration, 'docker')
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
        path_configuration_docker = pathlib.Path(path_configuration, 'docker')
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
        # services = await self.get_configuration_services()
        config_modules = self.get_config_modules()
        await self._etat_docker.entretien_services(config_modules)
        self.__logger.debug("entretien_services fin")

    async def entretien_webapps_installation(self):
        self.__logger.debug("entretien_webapps_installation debut")
        await entretien_webapps_installation(self._etat_instance)
        self.__logger.debug("entretien_webapps_installation fin")

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
        self._taches_entretien.append(TacheEntretien(datetime.timedelta(seconds=30), self.entretien_webapps_installation))

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceInstallation")
        await super().setup(etat_instance, etat_docker)

    def get_config_modules(self) -> list:
        return CONFIG_MODULES_INSTALLATION

    async def entretien_repertoires_installation(self):
        path_nginx = self._etat_instance.configuration.path_nginx
        path_nginx_html = path.join(path_nginx, 'html')
        makedirs(path_nginx_html, 0o755, exist_ok=True)

        path_nginx_modules = pathlib.Path(path_nginx, 'modules')
        if path_nginx_modules.exists() is False:  # modules/ not configured yet
            self.__logger.info("Setup nginx installation module configuration")
            path_nginx_modules_work = pathlib.Path(path_nginx, 'modules.work')
            try:
                # Cleanup old attempt
                shutil.rmtree(path_nginx_modules_work)
            except FileNotFoundError:
                pass  #

            path_src_nginx = pathlib.Path(self._etat_instance.configuration.path_configuration, 'nginx')
            generer_configuration_nginx(self._etat_instance, path_src_nginx, path_nginx_modules_work, None)
            path_nginx_modules_work.rename(path_nginx_modules)


class InstanceDockerCertificatProtegeExpire(InstanceDockerAbstract):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._event_stop: Optional[Event] = None
        self._etat_instance: Optional[EtatInstance] = None
        self._etat_docker: Optional[EtatDockerInstanceSync] = None

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceCertificatProtegeExpire")
        etat_instance.attente_renouvellement_certificat = True
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
        etat_instance.attente_renouvellement_certificat = True
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
        etat_instance.attente_renouvellement_certificat = True
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
        self.__entretien_nginx: Optional[NginxHandler] = None
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

        self.__entretien_nginx = NginxHandler(etat_instance, etat_docker)
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

        # await self._etat_docker.redemarrer_nginx("InstanceProtegee Demarrage instance")

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

        # # Ensure coupdoeil is listed in web applications list
        # hostname = self._etat_instance.hostname
        # coupdoeil_info = APPLICATION_COUPDOEIL_CONFIG.copy()
        # coupdoeil_info['url'] = coupdoeil_info['url'].replace('${HOSTNAME}', hostname)
        # path_conf_applications = pathlib.Path(
        #     self._etat_instance.configuration.path_configuration,
        #     ConstantesInstance.CONFIG_NOMFICHIER_CONFIGURATION_WEB_APPLICATIONS)
        # try:
        #     with open(path_conf_applications, 'rt+') as fichier:
        #         config_file = json.load(fichier)
        #         if config_file.get('coupdoeil') is None:
        #             config_file['coupdoeil'] = {'links': [coupdoeil_info]}
        #             fichier.seek(0)
        #             json.dump(config_file, fichier)
        #             fichier.truncate()
        # except (FileNotFoundError, json.JSONDecodeError):
        #     with open(path_conf_applications, 'wt') as fichier:
        #         json.dump({'coupdoeil': {'links': [coupdoeil_info]}}, fichier)

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
        self.__entretien_nginx: Optional[NginxHandler] = None
        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceSecureDocker")
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()
        self.__entretien_nginx = NginxHandler(etat_instance, etat_docker)

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

        # await self._etat_docker.redemarrer_nginx("InstanceSecureDocker Demarrage instance")

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
        self.__entretien_nginx: Optional[NginxHandler] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: EtatDockerInstanceSync):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = NginxHandler(etat_instance, etat_docker)

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

        # await self._etat_docker.redemarrer_nginx("InstancePriveeDocker Demarrage instance")

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
        self.__entretien_nginx: Optional[NginxHandler] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync]=None):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = NginxHandler(etat_instance, etat_docker)

        self._gestionnaire_applications = ApplicationsHandler(etat_instance, etat_docker)

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
        self.__entretien_nginx: Optional[NginxHandler] = None

        self.__rabbitmq_dao: Optional[RabbitMQDao] = None

        self.__setup_catalogues_complete = False

    async def setup(self, etat_instance: EtatInstance, etat_docker: Optional[EtatDockerInstanceSync] = None):
        self.__logger.info("Setup InstanceProtegee")
        self._etat_instance = etat_instance

        # self.__event_setup_initial_certificats = Event()
        self.__event_setup_initial_passwords = Event()

        self.__entretien_nginx = NginxHandler(etat_instance, etat_docker)

        self._gestionnaire_applications = ApplicationsHandler(etat_instance, etat_docker)

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
