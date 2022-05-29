import os

import aiohttp
import logging
import ssl

from aiohttp.client_exceptions import ClientConnectorError
from os import path, makedirs, stat
from typing import Optional
from millegrilles_messages.messages import Constantes


class EntretienNginx:

    def __init__(self, etat_instance, etat_docker):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = etat_docker

        self.__passwd_mq: Optional[str] = None
        self.__session: Optional[aiohttp.ClientSession] = None

        ca_path = etat_instance.configuration.instance_ca_pem_path
        self.__sslcontext = ssl.create_default_context(cafile=ca_path)

        self.__entretien_initial_complete = False
        self.__url_nginx = 'https://127.0.0.1:443'
        self.__url_nginx_sslclient = 'https://127.0.0.1:444'

        self.__repertoire_configuration_pret = False

    async def creer_session(self):
        if self.__etat_instance.configuration.instance_password_mq_path is not None:
            with open(self.__etat_instance.configuration.instance_password_mq_path, 'r') as fichier:
                password_mq = fichier.read().strip()
            basic_auth = aiohttp.BasicAuth('admin', password_mq)
            self.__session = aiohttp.ClientSession(auth=basic_auth)

    async def entretien(self):
        self.__logger.debug("entretien debut")

        try:
            if self.__entretien_initial_complete is False:
                await self.preparer_nginx()

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
                except ClientConnectorError:
                    self.__logger.exception("nginx n'est pas accessible")

        except Exception as e:
            self.__logger.exception("Erreur verification nginx https")

        self.__logger.debug("entretien fin")

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
        makedirs(path_nginx_html, 0o750, exist_ok=True)

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

        params = {
            'nodename': 'mg-dev5',
            'hostname': 'mg-dev5',
            'instance_url': 'https://mg-dev5:2443',
            'certissuer_url': 'http://mg-dev5:2080',
            'midcompte_url': 'https://midcompte:2444',
            'MQ_HOST': 'mq',
        }

        configuration_modifiee = False
        niveau_securite = self.__etat_instance.niveau_securite

        # Faire liste des fichiers de configuration
        if niveau_securite == Constantes.SECURITE_PROTEGE:
            repertoire_src_nginx = path.abspath('../etc/nginx/nginx_protege')
        elif niveau_securite == Constantes.SECURITE_PRIVE:
            repertoire_src_nginx = path.abspath('../etc/nginx/nginx_prive')
        elif niveau_securite == Constantes.SECURITE_PUBLIC:
            repertoire_src_nginx = path.abspath('../etc/nginx/nginx_public')
        else:
            raise Exception("Niveau securite non supporte avec nginx : '%s'", niveau_securite)

        for fichier in os.listdir(repertoire_src_nginx):
            # Verifier si le fichier existe dans la destination
            path_destination = path.join(path_nginx_modules, fichier)
            if path.exists(path_destination) is False:
                self.__logger.info("Generer fichier configuration nginx %s" % fichier)
                path_source = path.join(repertoire_src_nginx, fichier)
                with open(path_source, 'r') as fichier:
                    contenu = fichier.read()
                contenu = contenu.format(**params)

                with open(path_destination, 'w') as fichier:
                    fichier.write(contenu)
                configuration_modifiee = True

        return configuration_modifiee
