import asyncio
import datetime
import json
import os
from asyncio import to_thread

import urllib3
import pathlib

import aiohttp
import logging
import ssl

from aiohttp.client_exceptions import ClientConnectorError
from os import path, makedirs
from typing import Optional, Union

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.InstanceDocker import InstanceDockerHandler
from millegrilles_instance.NginxUtils import ajouter_fichier_configuration
from millegrilles_messages.docker.DockerHandler import DockerHandler
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_instance.AcmeHandler import CommandeAcmeExtractCertificates, AcmeNonDisponibleException
from millegrilles_instance.TorHandler import CommandeOnionizeGetHostname, OnionizeNonDisponibleException


LOGGER = logging.getLogger(__name__)


class NginxHandler:

    def __init__(self, context: InstanceContext, docker_handler: Optional[DockerHandler]):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context: InstanceContext = context
        self.__docker_handler = docker_handler

        self.__url_nginx = 'https://127.0.0.1:443'
        self.__url_nginx_sslclient = 'https://127.0.0.1:444'

        self.__repertoire_configuration_pret = False

    async def setup(self):
        await self.preparer_nginx()

    def __ssl_session(self, timeout: Optional[aiohttp.ClientTimeout] = None):
        return self.__context.ssl_session(timeout)

    async def __entretien(self, producer):
        self.__logger.debug("entretien debut")
        try:
            await self.__verifier_certificat_web()
            await self.__verifier_tor()
            await self.__load_fiche()
        except Exception as e:
            self.__logger.exception("Erreur verification nginx https")
        self.__logger.debug("entretien fin")

    async def __load_fiche(self):
        try:
            path_fiche = path.join(self.__url_nginx_sslclient, 'fiche.json')
            async with self.__ssl_session(aiohttp.ClientTimeout(total=10, connect=3)) as session:
                async with session.head(path_fiche) as reponse:
                    pass

            if reponse.status == 200:
                pass  # Ok, already present
            elif reponse.status == 404:
                self.__logger.info("Error accessing fiche.json via https (404)")
                # Tenter de charger la fiche
                idmg = self.__context.idmg
                try:
                    producer = await asyncio.wait_for(self.__context.get_producer(), 3)
                except asyncio.TimeoutError:
                    self.__logger.info("Producer not available yet, fiche not updated")
                    return

                reponse_fiche = await producer.request(
                    {'idmg': idmg},
                    'CoreTopologie',
                    'ficheMillegrille',
                    Constantes.SECURITE_PRIVE,
                    timeout=10
                )

                fiche_contenu = reponse_fiche.contenu
                self.__logger.debug("Fiche chargee via requete : %s" % fiche_contenu)
                path_nginx = self.__context.configuration.path_nginx
                path_fiche_json = path.join(path_nginx, 'html', 'fiche.json')
                self.sauvegarder_fichier_data(path_fiche_json, fiche_contenu)
            else:
                self.__logger.warning("Error accessing fiche.json via https, response code %d" % reponse.status)
        except ValueNotAvailable:
            self.__logger.error("Local millegrille TLS not configured yet")
        except ClientConnectorError:
            self.__logger.exception("While loading fichier.json, nginx is unavailable")

    async def preparer_nginx(self):
        self.__logger.info("Preparer nginx")

        # S'assurer que l'instance nginxinstall est supprimee
        # await nginx_installation_cleanup(self.__docker_handler)
        configuration_modifiee = await asyncio.to_thread(self.verifier_repertoire_configuration)
        # self.__entretien_initial_complete = True
        self.__logger.info("Configuration nginx prete (configuration modifiee? %s)" % configuration_modifiee)

        # if configuration_modifiee is True:
        #     await self.__context.reload_wait()

    def verifier_repertoire_configuration(self):
        path_nginx = self.__context.configuration.path_nginx
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
        path_src_nginx = pathlib.Path(self.__context.configuration.path_configuration, 'nginx')
        return generer_configuration_nginx(self.__context, path_src_nginx)

    def sauvegarder_fichier_data(self, path_fichier: str, contenu: Union[str, bytes, dict], path_html=False):
        path_nginx = self.__context.configuration.path_nginx
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

    async def __verifier_certificat_web(self):
        """
        Verifier si le certificat web doit etre change (e.g. maj ACME)
        :return:
        """
        hostname = self.__context.hostname
        commande = CommandeAcmeExtractCertificates(hostname)
        await self.__docker_handler.run_command(commande)
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
        configuration = self.__context.configuration
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
            await self.__docker_handler.redemarrer_nginx("EntetienNginx.verifier_certificat_web Nouveau certificat web")

    async def __verifier_tor(self):
        commande = CommandeOnionizeGetHostname()
        await self.__docker_handler.run_command(commande)
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

        path_nginx = self.__context.configuration.path_nginx
        path_nginx_module = pathlib.Path(path_nginx, 'modules')
        fichier_nouveau = ajouter_fichier_configuration(self.__context, path_nginx_module, nom_fichier, contenu)

        if fichier_nouveau is True:
            await self.__docker_handler.redemarrer_nginx("EntretienNginx.verifier_tor Maj configuration TOR")


def generer_configuration_nginx(context: InstanceContext, path_src_nginx: pathlib.Path) -> bool:
    """
    :path_src_nginx: Configuration file source folder for nginx
    :path_nginx: nginx destination folder
    :niveau_securite: Security level of the instance, None for installation mode.
    """

    try:
        securite = context.securite
    except ValueNotAvailable:
        securite = None  # Installation mode

    configuration: ConfigurationInstance = context.configuration
    path_nginx_modules = pathlib.Path(configuration.path_nginx, 'modules')

    makedirs(path_nginx_modules, 0o750, exist_ok=True)

    configuration_modifiee = False

    # Faire liste des fichiers de configuration
    if securite == Constantes.SECURITE_PROTEGE:
        repertoire_src_nginx = path.join(path_src_nginx, 'nginx_protege')
    elif securite == Constantes.SECURITE_SECURE:
        repertoire_src_nginx = path.join(path_src_nginx, 'nginx_secure')
    elif securite == Constantes.SECURITE_PRIVE:
        repertoire_src_nginx = path.join(path_src_nginx, 'nginx_prive')
    elif securite == Constantes.SECURITE_PUBLIC:
        repertoire_src_nginx = path.join(path_src_nginx, 'nginx_public')
    else:
        LOGGER.info("Configurer nginx en mode installation")
        repertoire_src_nginx = path.join(path_src_nginx, 'nginx_installation')

    initial_override = False
    guard_initial_override = None
    if securite is not None:
        guard_initial_override = pathlib.Path(path_nginx_modules, '.init_done')
        if guard_initial_override.exists() is False:
            initial_override = True

    for fichier in os.listdir(repertoire_src_nginx):
        # Verifier si le fichier existe dans la destination
        path_destination = path.join(path_nginx_modules, fichier)
        if initial_override or path.exists(path_destination) is False:
            LOGGER.info("Generer fichier configuration nginx %s" % fichier)
            path_source = path.join(repertoire_src_nginx, fichier)
            with open(path_source, 'r') as fichier_input:
                contenu = fichier_input.read()
            ajouter_fichier_configuration(context, path_nginx_modules, fichier, contenu)
            configuration_modifiee = True

    if guard_initial_override:
        with open(guard_initial_override, 'wt') as fichier:
            json.dump({'done': True}, fichier)

    return configuration_modifiee


