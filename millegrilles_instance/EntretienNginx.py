import datetime
import json
import os

import aiohttp
import logging
import ssl

from aiohttp.client_exceptions import ClientConnectorError
from os import path, makedirs
from typing import Optional, Union
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_instance.AcmeHandler import CommandeAcmeExtractCertificates, AcmeNonDisponibleException
from millegrilles_instance.TorHandler import CommandeOnionizeGetHostname, OnionizeNonDisponibleException


class EntretienNginx:

    def __init__(self, etat_instance, etat_docker):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

        self.__passwd_mq: Optional[str] = None
        self.__session: Optional[aiohttp.ClientSession] = None

        ca_path = etat_instance.configuration.instance_ca_pem_path
        self.__sslcontext = ssl.create_default_context(cafile=ca_path)

        try:
            self.__sslcontext.load_cert_chain(etat_instance.configuration.instance_cert_pem_path,
                                              etat_instance.configuration.instance_key_pem_path)
        except FileNotFoundError:
            pass

        self.__entretien_initial_complete = False
        self.__url_nginx = 'https://127.0.0.1:443'
        self.__url_nginx_sslclient = 'https://127.0.0.1:444'

        self.__repertoire_configuration_pret = False

        etat_instance.set_entretien_nginx(self)

        # Information de CoreTopologie pour la consignation de fichiers
        self.__configuration_consignation: Optional[dict] = None
        self.__date_changement_consignation: Optional[datetime.datetime] = None
        self.__intervalle_verification_consignation = datetime.timedelta(minutes=15)

    async def creer_session(self):
        if self.__etat_instance.configuration.instance_password_mq_path is not None:
            with open(self.__etat_instance.configuration.instance_password_mq_path, 'r') as fichier:
                password_mq = fichier.read().strip()
            basic_auth = aiohttp.BasicAuth('admin', password_mq)
            self.__session = aiohttp.ClientSession(auth=basic_auth)

    async def entretien(self, producer):
        self.__logger.debug("entretien debut")

        try:
            if self.__entretien_initial_complete is False:
                await self.preparer_nginx()

            await self.verifier_certificat_web()

            await self.verifier_tor()

            if self.__session is None:
                await self.creer_session()

            if self.__session is not None:
                try:
                    path_fiche = path.join(self.__url_nginx_sslclient, 'fiche.json')
                    async with self.__session.get(path_fiche, ssl=self.__sslcontext) as reponse:
                        pass
                    self.__logger.debug("Reponse fiche nginx : %s" % reponse)

                    if reponse.status == 200:
                        pass  # OK
                    elif reponse.status == 404:
                        self.__logger.warning("Erreur nginx https, fiche introuvable")
                        # Tenter de charger la fiche
                        idmg = self.__etat_instance.idmg
                        reponse_fiche = await producer.executer_requete(
                            {'idmg': idmg},
                            'CoreTopologie',
                            'ficheMillegrille',
                            Constantes.SECURITE_PRIVE,
                            timeout=10
                        )
                        fiche_parsed = reponse_fiche.parsed
                        self.__logger.debug("Fiche chargee via requete : %s" % fiche_parsed)
                        path_nginx = self.__etat_instance.configuration.path_nginx
                        path_fiche_json = path.join(path_nginx, 'html', 'fiche.json')
                        self.sauvegarder_fichier_data(path_fiche_json, fiche_parsed)

                except ClientConnectorError:
                    self.__logger.exception("nginx n'est pas accessible")

            if self.__configuration_consignation is None or \
                    self.__date_changement_consignation is None or \
                    self.__date_changement_consignation + self.__intervalle_verification_consignation < datetime.datetime.utcnow():
                try:
                    await self.charger_configuration_consignation(producer)
                    self.__date_changement_consignation = datetime.datetime.utcnow()
                except:
                    self.__logger.exception("Erreur configuration URL consignation")

        except Exception as e:
            self.__logger.exception("Erreur verification nginx https")

        self.__logger.debug("entretien fin")

    async def charger_configuration_consignation(self, producer):
        requete = dict()
        reponse = await producer.executer_requete(requete, 'CoreTopologie', 'getConsignationFichiers', Constantes.SECURITE_PRIVE)
        reponse_parsed = reponse.parsed
        if reponse_parsed['ok'] is True:
            self.__configuration_consignation = reponse_parsed
            # S'assurer que le module de configuration nginx pour TOR est configure
            instance_id = reponse_parsed['instance_id']
            if self.__etat_instance.instance_id == instance_id:
                # Local
                url_consignation = 'https://fichiers:443'
            else:
                url_consignation = reponse_parsed['consignation_url']

            nom_fichier = 'fichiers.proxypass.name'
            contenu = """# Fichier genere par EntretienNginx
set $upstream_fichiers %s;
proxy_pass $upstream_fichiers;
    """ % url_consignation
            fichier_nouveau = self.ajouter_fichier_configuration(nom_fichier, contenu)

            if fichier_nouveau is True:
                await self.__etat_docker.redemarrer_nginx()

    async def preparer_nginx(self):
        self.__logger.info("Preparer nginx")
        configuration_modifiee = self.verifier_repertoire_configuration()
        self.__entretien_initial_complete = True
        self.__logger.info("Configuration nginx prete (configuration modifiee? %s)" % configuration_modifiee)

        if configuration_modifiee is True:
            await self.__etat_instance.reload_configuration()

    def verifier_repertoire_configuration(self):
        path_nginx = self.__etat_instance.configuration.path_nginx
        path_nginx_html = path.join(path_nginx, 'html')
        makedirs(path_nginx_html, 0o755, exist_ok=True)
        path_nginx_data = path.join(path_nginx, 'data')
        makedirs(path_nginx_data, 0o755, exist_ok=True)
        path_nginx_module = path.join(path_nginx, 'modules')
        makedirs(path_nginx_module, 0o750, exist_ok=True)

        # Verifier existance de la configuration de modules nginx
        configuration_modifiee = self.generer_configuration_nginx()

        return configuration_modifiee

    def generer_configuration_nginx(self) -> bool:
        path_nginx = self.__etat_instance.configuration.path_nginx
        path_nginx_modules = path.join(path_nginx, 'modules')
        makedirs(path_nginx_modules, 0o750, exist_ok=True)

        # params = {
        #     'nodename': nodename,
        #     'hostname': hostname,
        #     'monitor_url': monitor_url,
        #     'certissuer_url': certissuer_url,
        #     'MQ_HOST': mq_host,
        # }

        # params = {
        #     'nodename': 'mg-dev5',
        #     'hostname': 'mg-dev5',
        #     'instance_url': 'https://mg-dev5:2443',
        #     'certissuer_url': 'http://mg-dev5:2080',
        #     'midcompte_url': 'https://midcompte:2444',
        #     'MQ_HOST': 'mq',
        # }

        configuration_modifiee = False
        niveau_securite = self.__etat_instance.niveau_securite

        # Faire liste des fichiers de configuration
        path_src_nginx = path.join(self.__etat_instance.configuration.path_configuration, 'nginx')

        if niveau_securite == Constantes.SECURITE_PROTEGE:
            repertoire_src_nginx = path.join(path_src_nginx, 'nginx_protege')
        elif niveau_securite == Constantes.SECURITE_SECURE:
            repertoire_src_nginx = path.join(path_src_nginx, 'nginx_secure')
        elif niveau_securite == Constantes.SECURITE_PRIVE:
            repertoire_src_nginx = path.join(path_src_nginx, 'nginx_prive')
        elif niveau_securite == Constantes.SECURITE_PUBLIC:
            repertoire_src_nginx = path.join(path_src_nginx, 'nginx_public')
        else:
            raise Exception("Niveau securite non supporte avec nginx : '%s'", niveau_securite)

        for fichier in os.listdir(repertoire_src_nginx):
            # Verifier si le fichier existe dans la destination
            path_destination = path.join(path_nginx_modules, fichier)
            if path.exists(path_destination) is False:
                self.__logger.info("Generer fichier configuration nginx %s" % fichier)
                path_source = path.join(repertoire_src_nginx, fichier)
                with open(path_source, 'r') as fichier_input:
                    contenu = fichier_input.read()
                # contenu = contenu.format(**params)
                self.ajouter_fichier_configuration(fichier, contenu)
                # with open(path_destination, 'w') as fichier:
                #     fichier.write(contenu)
                configuration_modifiee = True

        return configuration_modifiee

    def ajouter_fichier_configuration(self, nom_fichier: str, contenu: str, params: Optional[dict] = None) -> bool:
        path_nginx = self.__etat_instance.configuration.path_nginx
        path_nginx_modules = path.join(path_nginx, 'modules')
        if params is None:
            params = dict()
        else:
            params = params.copy()

        params.update({
            'nodename': self.__etat_instance.hostname,
            'hostname': self.__etat_instance.hostname,
            'instance_url': 'https://%s:2443' % self.__etat_instance.hostname,
            'certissuer_url': 'http://%s:2080' % self.__etat_instance.hostname,
            'midcompte_url': 'https://midcompte:2444',
            'MQ_HOST': self.__etat_instance.mq_hostname,
        })

        path_destination = path.join(path_nginx_modules, nom_fichier)
        contenu = contenu.format(**params)

        changement_detecte = False
        try:
            with open(path_destination, 'r') as fichier_existant:
                contenu_existant = fichier_existant.read()
                if contenu_existant != contenu:
                    changement_detecte = True
        except FileNotFoundError:
            changement_detecte = True

        with open(path_destination, 'w') as fichier_output:
            fichier_output.write(contenu)

        return changement_detecte

    def sauvegarder_fichier_data(self, path_fichier: str, contenu: Union[str, bytes, dict], path_html=False):
        path_nginx = self.__etat_instance.configuration.path_nginx
        if path_html is True:
            path_nginx_fichier = path.join(path_nginx, 'html', path_fichier)
        else:
            path_nginx_fichier = path.join(path_nginx, 'data', path_fichier)

        if isinstance(contenu, str):
            contenu = contenu.encode('utf-8')
        elif isinstance(contenu, dict):
            contenu = json.dumps(contenu).encode('utf-8')

        with open(path_nginx_fichier, 'wb') as output:
            output.write(contenu)

    async def verifier_certificat_web(self):
        """
        Verifier si le certificat web doit etre change (e.g. maj ACME)
        :return:
        """
        hostname = self.__etat_instance.hostname
        commande = CommandeAcmeExtractCertificates(hostname)
        self.__etat_docker.ajouter_commande(commande)
        try:
            resultat = await commande.get_resultat()
        except AcmeNonDisponibleException:
            self.__logger.debug("Service ACME non demarre")
            return

        exit_code = resultat['code']
        str_resultat = resultat['resultat']
        key_pem = resultat['key']
        cert_pem = resultat['cert']

        if exit_code != 0:
            self.__logger.debug("Aucun certificat web avec ACME pour %s\n%s" % (hostname, str_resultat))
            return

        enveloppe_acme = CleCertificat.from_pems(key_pem, cert_pem)
        if enveloppe_acme.cle_correspondent() is False:
            self.__logger.warning("Cle/certificat ACME ne correspondent pas (etat inconsistent)")
            return

        # S'assurer que le certificat installe est le meme que celui recu
        configuration = self.__etat_instance.configuration
        path_cle_web = configuration.path_cle_web
        path_cert_web = configuration.path_certificat_web

        remplacer = False
        try:
            cert_courant = EnveloppeCertificat.from_file(path_cert_web)
        except FileNotFoundError:
            self.__logger.info("Fichier certificat web absent, on utilise la version ACME")
            remplacer = True
        else:
            if cert_courant.not_valid_before < enveloppe_acme.enveloppe.not_valid_before:
                self.__logger.info("Fichier certificat ACME plus recent que le certificat courant, on l'applique")
                remplacer = True
            elif cert_courant.is_root_ca:
                self.__logger.info("Fichier certificat local est self-signed, on applique le cert ACME")
                remplacer = True

        if remplacer is True:
            self.__logger.info("Remplacer le certificat web nginx")
            with open(path_cle_web, 'w') as fichier:
                fichier.write(key_pem)
            with open(path_cert_web, 'w') as fichier:
                fichier.write(cert_pem)

            self.__logger.info("Redemarrer nginx avec le nouveau certificat web")
            await self.__etat_docker.redemarrer_nginx()

    async def verifier_tor(self):
        commande = CommandeOnionizeGetHostname()
        self.__etat_docker.ajouter_commande(commande)
        try:
            hostname = await commande.get_resultat()
        except OnionizeNonDisponibleException:
            self.__logger.debug("Service onionize non demarre")
            return

        self.__logger.debug("Adresse onionize : %s" % hostname)

        # S'assurer que le module de configuration nginx pour TOR est configure
        nom_fichier = 'onion.location'
        contenu = """
add_header "Onion-Location" "https://%s";
""" % hostname
        fichier_nouveau = self.ajouter_fichier_configuration(nom_fichier, contenu)

        if fichier_nouveau is True:
            await self.__etat_docker.redemarrer_nginx()

