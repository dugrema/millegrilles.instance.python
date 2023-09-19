import os

import asyncio
import aiohttp
import datetime
import logging
import json
import psutil

from apcaccess import status as apc
from asyncio import Event
from json.decoder import JSONDecodeError
from typing import Optional
from os import path, listdir

from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages import Constantes
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.Certificats import preparer_certificats_web, generer_certificats_modules, generer_passwords, \
    generer_certificats_modules_satellites
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_messages.IpUtils import get_ip, get_hostname
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.FormatteurMessages import SignateurTransactionSimple, FormatteurMessageMilleGrilles
from millegrilles_instance.EntretienNginx import EntretienNginx
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_messages.messages.ValidateurCertificats import ValidateurCertificatCache
from millegrilles_messages.messages.ValidateurMessage import ValidateurMessage
from millegrilles_messages.messages.Notifications import EmetteurNotifications


class EtatInstance:

    def __init__(self, configuration: ConfigurationInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__client_session = aiohttp.ClientSession()
        self.__etat_systeme = EtatSysteme(self)

        self.__ip_address: Optional[str] = None
        self.__hostname: Optional[str] = None
        self.__instance_id: Optional[str] = None
        self.__niveau_securite: Optional[str] = None
        self.__idmg: Optional[str] = None
        self.__certificat_millegrille: Optional[EnveloppeCertificat] = None
        self.__clecertificat: Optional[CleCertificat] = None
        self.__password_mq: Optional[str] = None

        self.__host_mq = "localhost"
        self.__port_mq = 5673

        self.__docker_present = False
        self.__docker_actif = False
        self.__csr_genere: Optional[CleCsrGenere] = None

        self.__entretien_nginx: Optional[EntretienNginx] = None

        # Liste de listeners qui sont appeles sur changement de configuration
        self.__config_listeners = list()
        self.__formatteur_message: Optional[FormatteurMessageMilleGrilles] = None
        self.__validateur_certificats: Optional[ValidateurCertificatCache] = None
        self.__validateur_message: Optional[ValidateurMessage] = None
        self.__generateur_certificats = None

        self.__stop_event: Optional[Event] = None
        self.__redemarrer = False

        self.__attente_rotation_maitredescles: Optional[datetime.datetime] = None

        self.__certificats_maitredescles: dict[str, CacheCertificat] = dict()

        self.__emetteur_notifications: Optional[EmetteurNotifications] = None

        self.__producer_set_event = None
        self.__producer_cb = None

    async def reload_configuration(self):
        self.__logger.info("Reload configuration sur disque ou dans docker")

        if self.__producer_set_event is None:
            self.__producer_set_event = asyncio.Event()

        self.__ip_address = get_ip()
        self.__hostname = get_hostname(fqdn=True)
        self.__logger.debug("Nom domaine instance: %s" % self.__hostname)

        # Generer les certificats web self-signed au besoin
        path_cert_web, path_cle_web = preparer_certificats_web(self.__configuration.path_secrets)
        self.__configuration.path_certificat_web = path_cert_web
        self.__configuration.path_cle_web = path_cle_web

        self.__instance_id = load_fichier_config(self.__configuration.instance_id_path)
        self.__logger.info("Instance id : %s", self.__instance_id)

        self.__niveau_securite = load_fichier_config(self.__configuration.instance_securite_path)
        self.__logger.info("Securite : %s", self.__niveau_securite)

        self.__idmg = load_fichier_config(self.__configuration.instance_idmg_path)
        self.__logger.info("IDMG : %s", self.__idmg)

        self.__certificat_millegrille = load_enveloppe_cert(self.__configuration.instance_ca_pem_path)
        self.__logger.debug("Certificat Millegrille\n%s" % self.__certificat_millegrille)

        self.__clecertificat = load_clecert(self.__configuration.instance_key_pem_path,
                                            self.__configuration.instance_cert_pem_path)
        self.__logger.debug("Certificat instance: %s" % self.__clecertificat)

        # Exporter configuration pour modules dependants
        self.maj_configuration_json()

        try:
            self.__emetteur_notifications = EmetteurNotifications(self.__certificat_millegrille, 'Instance %s' % self.__hostname)
        except AttributeError as e:
            self.__logger.warning("Emetteur de notification non disponible (certificats pas pret) : %s" % e)
            self.__emetteur_notifications = None

        if self.__clecertificat is not None:
            signateur = SignateurTransactionSimple(self.__clecertificat)
            self.__formatteur_message = FormatteurMessageMilleGrilles(self.__idmg, signateur)
            self.__validateur_certificats = ValidateurCertificatCache(self.__certificat_millegrille)
            self.__validateur_message = ValidateurMessage(self.__validateur_certificats)

        for listener in self.__config_listeners:
            await listener(self)

    def maj_configuration_json(self, configuration: Optional[dict] = None):
        config_json_path = self.configuration.config_json
        try:
            with open(config_json_path, 'rb') as fichier:
                params_courants = json.load(fichier)
            os.rename(config_json_path, config_json_path + '.old')
        except FileNotFoundError:
            params_courants = dict()
        except JSONDecodeError:
            raise Exception("Fichier %s corrompu" % config_json_path)

        params_courants['instance_id'] = self.instance_id
        params_courants['idmg'] = self.idmg or params_courants.get('idmg')
        params_courants['securite'] = self.niveau_securite or params_courants.get('securite')

        if configuration is not None:
            params_courants.update(configuration)

        try:
            # Verifier si on a un override
            self.__host_mq = os.environ['MQ_HOST']
        except KeyError:
            try:
                self.__host_mq = params_courants['mq_host']
            except KeyError:
                pass

        try:
            # Verifier si on a un override
            self.__port_mq = os.environ['MQ_PORT']
        except KeyError:
            try:
                self.__port_mq = params_courants['mq_port']
            except KeyError:
                pass

        with open(config_json_path, 'w') as fichier:
            json.dump(params_courants, fichier, indent=2)

    def ajouter_listener(self, callback_async):
        self.__config_listeners.append(callback_async)

    def retirer_listener(self, callback_async):
        try:
            self.__config_listeners.remove(callback_async)
        except ValueError:
            pass

    def etat(self):
        pass

    async def entretien(self, get_producer=None):
        if self.__validateur_certificats is not None:
            await self.__validateur_certificats.entretien()

        maitredescles_expire = [v.fingerprint for v in self.__certificats_maitredescles.values() if v.cache_expire()]
        for fingerprint in maitredescles_expire:
            del self.__certificats_maitredescles[fingerprint]

        if get_producer is not None:
            producer = await get_producer()
        else:
            self.__logger.info("EtatInstance.entretien Producer mq est None")
            producer = None

        try:
            await self.__etat_systeme.entretien(producer)
        except Exception:
            self.__logger.exception('Erreur entretien systeme')

    def set_docker_present(self, etat: bool):
        self.__docker_present = etat

    def get_csr_genere(self):
        if self.__csr_genere is None:
            self.__csr_genere = CleCsrGenere.build(self.instance_id)
        return self.__csr_genere

    def clear_csr_genere(self):
        self.__csr_genere = None

    def ajouter_certificat_maitredescles(self, certificat: EnveloppeCertificat):
        fingerprint = certificat.fingerprint
        try:
            env_cache = self.__certificats_maitredescles[fingerprint]
            # Touch certificat existant
            env_cache.touch()
        except KeyError:
            # Conserver certificat
            env_cache = CacheCertificat(certificat)
            self.__certificats_maitredescles[fingerprint] = env_cache

    async def get_producer(self, timeout=5):
        if self.__producer_cb is None:
            await asyncio.wait_for(self.__producer_set_event.wait(), timeout=timeout)
        if self.__producer_cb is not None:
            return await self.__producer_cb(timeout)
        return None

    @property
    def stop_event(self):
        return self.__stop_event

    @property
    def docker_present(self):
        return self.__docker_present

    def set_docker_actif(self, etat: bool):
        self.__docker_actif = etat

    @property
    def docker_actif(self):
        return self.__docker_actif

    @property
    def instance_id(self):
        return self.__instance_id

    @property
    def niveau_securite(self):
        return self.__niveau_securite

    @property
    def idmg(self):
        return self.__idmg

    @property
    def certissuer_url(self):
        return self.__configuration.certissuer_url

    @property
    def nom_domaine(self):
        return self.__hostname

    @property
    def configuration(self):
        return self.__configuration

    @property
    def clecertificat(self):
        return self.__clecertificat

    @property
    def certificat_millegrille(self):
        return self.__certificat_millegrille

    @property
    def ip_address(self):
        return self.__ip_address

    @property
    def hostname(self):
        return self.__hostname

    @property
    def mq_hostname(self):
        return self.__host_mq or self.__hostname

    @property
    def mq_port(self):
        return self.__port_mq

    @property
    def formatteur_message(self):
        return self.__formatteur_message

    def set_redemarrer(self, redemarrer):
        self.__redemarrer = redemarrer

    def set_entretien_nginx(self, entretien_nginx):
        self.__entretien_nginx = entretien_nginx

    def set_producer(self, producer_cb):
        self.__producer_cb = producer_cb
        self.__producer_set_event.set()

    @property
    def client_session(self):
        return self.__client_session

    @property
    def entretien_nginx(self):
        return self.__entretien_nginx

    @property
    def redemarrer(self):
        return self.__redemarrer

    @property
    def validateur_certificats(self):
        return self.__validateur_certificats

    @property
    def validateur_message(self):
        return self.__validateur_message

    @property
    def generateur_certificats(self):
        return self.__generateur_certificats

    @generateur_certificats.setter
    def generateur_certificats(self, generateur_certificats):
        self.__generateur_certificats = generateur_certificats

    def doit_activer_443(self):
        """
        :return: True si le WebServer doit ouvrir le port 443 (en plus du port 2443)
        """
        if self.__certificat_millegrille is None:
            return True
        if self.__docker_present is False:
            return True

        return False

    def set_stop_event(self, stop_event: Event):
        self.__stop_event = stop_event

    async def stop(self):
        if self.__stop_event is not None:
            self.__stop_event.set()
        else:
            raise Exception("Stop event non disponible")

    async def generer_certificats_module(self, producer: MessageProducerFormatteur, etat_docker, nom_module: str, configuration: dict):
        config = {nom_module: configuration}
        await generer_certificats_modules(producer, self.__client_session, self, config, etat_docker)

    async def generer_certificats_module_satellite(self, producer: MessageProducerFormatteur,
                                                   etat_docker, nom_module: str, configuration: dict):
        config = {nom_module: configuration}
        await generer_certificats_modules_satellites(producer, self, etat_docker, config)

    async def generer_passwords(self, etat_docker, passwords: list):
        await generer_passwords(self, etat_docker, passwords)

    # def partition_usage(self):
    #     partitions = psutil.disk_partitions()
    #     reponse = list()
    #     for p in partitions:
    #         if 'rw' in p.opts and '/boot' not in p.mountpoint:
    #             usage = psutil.disk_usage(p.mountpoint)
    #             reponse.append(
    #                 {'mountpoint': p.mountpoint, 'free': usage.free, 'used': usage.used, 'total': usage.total})
    #     return reponse

    async def emettre_presence(self, producer: MessageProducerFormatteur, info: Optional[dict] = None):
        self.__logger.info("Emettre presence")
        if info is not None:
            info_updatee = info.copy()
        else:
            info_updatee = dict()

        info_updatee['hostname'] = self.hostname
        info_updatee['domaine'] = self.hostname
        info_updatee['fqdn_detecte'] = get_hostname(fqdn=True)
        info_updatee['ip_detectee'] = self.ip_address
        info_updatee['instance_id'] = self.instance_id
        info_updatee['securite'] = self.niveau_securite

        # Ajouter etat systeme
        info_updatee.update(self.__etat_systeme.etat)

        # Faire la liste des applications installees
        liste_applications = await self.get_liste_configurations()
        info_updatee['applications_configurees'] = liste_applications

        niveau_securite = self.niveau_securite
        if niveau_securite == Constantes.SECURITE_SECURE:
            # Downgrade 4.secure a niveau 3.protege
            niveau_securite = Constantes.SECURITE_PROTEGE

        await producer.emettre_evenement(info_updatee, Constantes.DOMAINE_INSTANCE,
                                         ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE,
                                         exchanges=niveau_securite)

    async def get_liste_configurations(self) -> list:
        """
        Charge l'information de configuration de toutes les applications connues.
        :return:
        """
        info_configuration = list()
        path_docker_apps = self.configuration.path_docker_apps
        try:
            for fichier_config in listdir(path_docker_apps):
                if not fichier_config.startswith('app.'):
                    continue  # Skip, ce n'est pas une application
                with open(path.join(path_docker_apps, fichier_config), 'rb') as fichier:
                    contenu = json.load(fichier)
                nom = contenu['nom']
                version = contenu['version']
                info_configuration.append({'nom': nom, 'version': version})
        except FileNotFoundError:
            self.__logger.debug("get_liste_configurations Path catalogues docker non trouve")

        return info_configuration

    def maj_clecert(self, clecert: CleCertificat):
        # Installer le certificat d'instance
        cert_pem = '\n'.join(clecert.enveloppe.chaine_pem())
        cle_pem = clecert.private_key_bytes().decode('utf-8')
        configuration = self.configuration
        path_cert = configuration.instance_cert_pem_path
        path_key = configuration.instance_key_pem_path
        with open(path_cert, 'w') as fichier:
            fichier.write(cert_pem)
        with open(path_key, 'w') as fichier:
            fichier.write(cle_pem)

    def set_rotation_maitredescles(self):
        # Conserver delai de 3 heures avant prochaine rotation de certificat de maitre des cles
        self.__attente_rotation_maitredescles = datetime.datetime.utcnow() + datetime.timedelta(hours=3)

    def is_rotation_maitredescles(self):
        if self.__attente_rotation_maitredescles is None:
            return False

        datenow = datetime.datetime.utcnow()
        if datenow > self.__attente_rotation_maitredescles:
            self.__attente_rotation_maitredescles = None
            return False

        return True

    async def emettre_notification(self, producer, contenu, subject: Optional[str] = None, niveau='info'):
        if self.__emetteur_notifications is not None:
            if subject is None:
                subject = self.__hostname

            await self.__emetteur_notifications.emettre_notification(producer, contenu, subject, niveau)
        else:
            self.__logger.debug("Emetteur notification offline, notification ignoree : %s" % contenu)


def load_fichier_config(path_fichier: str) -> Optional[str]:
    try:
        with open(path_fichier, 'r') as fichier:
            value = fichier.read().strip()
        return value
    except FileNotFoundError:
        return None


def load_clecert(path_cle: str, path_cert: str) -> Optional[CleCertificat]:
    try:
        return CleCertificat.from_files(path_cle, path_cert)
    except FileNotFoundError:
        return None


def load_enveloppe_cert(path_cert: str) -> Optional[EnveloppeCertificat]:
    try:
        return EnveloppeCertificat.from_file(path_cert)
    except FileNotFoundError:
        return None


class CacheCertificat:

    def __init__(self, enveloppe: EnveloppeCertificat):
        self.derniere_reception = datetime.datetime.utcnow()
        self.enveloppe = enveloppe

    @property
    def fingerprint(self) -> str:
        return self.enveloppe.fingerprint

    @property
    def pems(self) -> list:
        return self.enveloppe.chaine_pem()

    def touch(self):
        self.derniere_reception = datetime.datetime.utcnow()

    def cache_expire(self) -> bool:
        date_expiration = datetime.datetime.utcnow() - datetime.timedelta(minutes=10)
        return self.derniere_reception < date_expiration


class EtatSysteme:

    CONST_INTERVALLE_NOTIFICATIONS_INFO = datetime.timedelta(hours=24)
    CONST_INTERVALLE_NOTIFICATIONS_WARN = datetime.timedelta(hours=12)
    CONST_INTERVALLE_NOTIFICATIONS_ERROR = datetime.timedelta(minutes=15)

    def __init__(self, etat_instance: EtatInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__apc_info = None

        self.__etat = dict()

        self.__notif_demarrage_envoyee = False
        self.__derniere_notification_disk: Optional[datetime.datetime] = None
        self.__derniere_notification_cpu: Optional[datetime.datetime] = None

        self.__notification_apc_offline: Optional[datetime.datetime] = None

    @property
    def etat(self):
        return self.__etat

    async def entretien(self, producer=None):
        # Charger information UPS APC (si disponible)

        await asyncio.gather(
            self.apc_info(producer),
            asyncio.to_thread(self.maj_info_systeme)
        )

        if producer is not None:
            await self.emettre_notifications(producer)

    def maj_info_systeme(self):
        info_systeme = dict()
        info_systeme['disk'] = self.partition_usage()
        info_systeme['load_average'] = [round(l * 100) / 100 for l in list(psutil.getloadavg())]
        info_systeme['system_temperature'] = psutil.sensors_temperatures()
        info_systeme['system_fans'] = psutil.sensors_fans()
        info_systeme['system_battery'] = psutil.sensors_battery()

        if self.__apc_info:
            info_systeme['apc'] = self.__apc_info

        self.__etat = info_systeme

    async def apc_info(self, producer=None):
        """
        Charge l'information du UPS de type APC.
        L'option se desactive automatiquement au premier echec
        """
        if self.__apc_info is False:
            return
        try:
            resultat = await asyncio.to_thread(apc.get, timeout=3)
            parsed = apc.parse(resultat, strip_units=True)
            self.__apc_info = parsed

            # Detecter besoin notification
            if producer is not None:
                try:
                    etat_ups = parsed['STATUS']
                except KeyError:
                    pass
                else:
                    try:
                        if self.__notification_apc_offline is None:
                            if etat_ups.startswith('ONLINE') is False:
                                # Etat UPS offline ou deconnecte
                                await self.emettre_notification_apc(producer, offline=True)
                        else:
                            if etat_ups.startswith('ONLINE') is True:
                                # Etat UPS ONLINE a nouveau
                                await self.emettre_notification_apc(producer, offline=False)
                    except Exception:
                        self.__logger.exception("Erreur notification APC UPS")

        except Exception as e:
            self.__logger.warning("UPS de type APC non accessible, desactiver (erreur %s)" % e)
            self.__apc_info = False

    def partition_usage(self):
        partitions = psutil.disk_partitions()
        reponse = list()
        for p in partitions:
            if 'rw' in p.opts and '/boot' not in p.mountpoint:
                usage = psutil.disk_usage(p.mountpoint)
                reponse.append(
                    {'mountpoint': p.mountpoint, 'free': usage.free, 'used': usage.used, 'total': usage.total})
        return reponse

    async def emettre_notifications(self, producer):
        """
        Emet des notifications systeme au besoin
        :return:
        """
        now = datetime.datetime.utcnow()
        if self.__notif_demarrage_envoyee is False:
            await self.__notification_demarrage(producer)
        if self.__derniere_notification_disk is None or now > self.__derniere_notification_disk + EtatSysteme.CONST_INTERVALLE_NOTIFICATIONS_INFO:
            await self.__notifications_disk(producer)
        if self.__derniere_notification_cpu is None or now > self.__derniere_notification_cpu + EtatSysteme.CONST_INTERVALLE_NOTIFICATIONS_WARN:
            await self.__notification_cpu(producer)

    async def __notifications_disk(self, producer):
        """
        Verifier espace disque
        """
        try:
            disk_info = self.__etat['disk']
        except KeyError:
            # Pas d'information disk
            return

        notifications = list()
        niveau = 'info'

        for disk in disk_info:
            # Calculer pourcentage
            mountpoint = disk['mountpoint']
            free = disk['free']
            total = disk['total']
            pct = free / total
            if pct < 0.05:
                # Warning
                self.__logger.warning("Disk %s < 5%%" % mountpoint)
                notifications.append('<p>Disk/partition "%s" : il reste moins de 5%% d''espace libre.</p>' % mountpoint)
                if niveau != 'warn':
                    niveau = 'warn'
            elif pct < 0.1:
                # Info
                self.__logger.info("Disk %s < 10%%" % mountpoint)
                notifications.append('<p>Disk/partition "%s" : il reste moins de 10%% d''espace libre.</p>' % mountpoint)

        subject = '%s Disk usage' % self.__etat_instance.hostname

        if len(notifications) > 0:
            info = {
                'instance_id': self.__etat_instance.instance_id,
                'nom_domaine': self.__etat_instance.nom_domaine,
            }
            contenu = """
<p>Faible espace disque disponible<p>
<p>Serveur {nom_domaine}</p>
<p>Instance id {instance_id}</p>
<br/>
""".format(**info)
            contenu += '\n'.join(notifications)

            self.__derniere_notification_disk = datetime.datetime.utcnow()
            await self.__etat_instance.emettre_notification(producer, contenu, subject=subject, niveau=niveau)

    async def __notification_demarrage(self, producer):
        info = {
            'instance_id': self.__etat_instance.instance_id,
            'nom_domaine': self.__etat_instance.nom_domaine,
            'ip_detectee': self.__etat_instance.ip_address,
            'securite': self.__etat_instance.niveau_securite,
        }

        subject = '%s Demarrage' % info['nom_domaine']
        contenu = """
<p>Demarrage de {nom_domaine}</p>
<br/>
<p>Instance {instance_id}</p>
<p>IP detectee {ip_detectee}</p>
<p>Securite {securite}</p>
""".format(**info)

        self.__notif_demarrage_envoyee = True
        await self.__etat_instance.emettre_notification(producer, contenu, subject=subject, niveau='info')

    async def __notification_cpu(self, producer):

        try:
            load_average = self.__etat['load_average']
        except KeyError:
            return  # Aucune info CPU

        niveau = None
        if load_average[2] > 5.0:
            niveau = 'warn'
        elif load_average[2] > 15.0:
            niveau = 'error'

        if niveau is None:
            return

        info = {
            'instance_id': self.__etat_instance.instance_id,
            'nom_domaine': self.__etat_instance.nom_domaine,
            'load_average': load_average,
        }

        subject = '%s CPU usage eleve' % info['nom_domaine']
        contenu = """
<p>Utilisation CPU elevee sur {nom_domaine}</p>
<br/>
CPU usage : {load_average}
<br/>
<p>Instance {instance_id}</p>
""".format(**info)

        self.__derniere_notification_cpu = datetime.datetime.utcnow()
        await self.__etat_instance.emettre_notification(producer, contenu, subject=subject, niveau=niveau)

    async def emettre_notification_apc(self, producer, offline: bool):

        etat_apc = self.__apc_info
        info = {
            'instance_id': self.__etat_instance.instance_id,
            'nom_domaine': self.__etat_instance.nom_domaine,
        }
        info.update(etat_apc)

        if offline is True:
            self.__notification_apc_offline = datetime.datetime.utcnow()

            subject = '%s UPS offline' % info['nom_domaine']
            # Emettre notification offline
            contenu = """
<p>APC UPS offline sur {nom_domaine}</p>
<br/>
<p>STATUS {STATUS}</p>
<p>Temps restant (minutes) {TIMELEFT}</p>
<p>Raison {LASTXFER}</p>
<p>Duree {TONBATT}</p>
<p>Nombre de transferts {NUMXFERS}</p>
"""
            await self.__etat_instance.emettre_notification(producer, contenu, subject=subject, niveau='warn')
        else:
            # Reset notification
            self.__notification_apc_offline = None

            subject = '%s UPS restored (online)' % info['nom_domaine']
            # Emettre notification offline
            contenu = """
<p>APC UPS restored (online) sur {nom_domaine}</p>
<br/>
<p>STATUS {STATUS}</p>
<p>Raison {LASTXFER}</p>
<p>Duree {TONBATT}</p>
<p>Nombre de transferts {NUMXFERS}</p>
"""
            await self.__etat_instance.emettre_notification(producer, contenu, subject=subject, niveau='warn')
