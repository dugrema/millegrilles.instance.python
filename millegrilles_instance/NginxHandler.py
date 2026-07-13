import asyncio
import json
import os
import urllib.parse

import pathlib

import aiohttp
import logging

from aiohttp.client_exceptions import ClientConnectorError
from os import path, makedirs
from typing import Optional, Union

from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.messages import Constantes


LOGGER = logging.getLogger(__name__)


class NginxHandler:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context: InstanceContext = context

        self.__url_nginx = 'https://127.0.0.1:443'
        self.__url_nginx_sslclient = 'https://127.0.0.1:444'

        self.__repertoire_configuration_pret = False

    async def setup(self):
        await self.preparer_nginx()

    def __ssl_session(self, timeout: Optional[aiohttp.ClientTimeout] = None):
        return self.__context.ssl_session(timeout)

    async def run(self):
        await self.__maintenance()
        if self.__context.stopping is False:
            self.__logger.error("NginxHandler thread stopped improperly - quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

    async def __maintenance(self):
        while self.__context.stopping is False:
            try:
                # await self.__verifier_certificat_web()
                # await self.__verifier_tor()
                await self.__load_fiche()
            except asyncio.CancelledError as e:
                raise e
            except Exception:
                self.__logger.exception("Unhandled error checking nginx status")
            await self.__context.wait(300)
        self.__logger.debug("Nginx maintenance thread DONE")

    async def __load_fiche(self):
        try:
            path_fiche = urllib.parse.urljoin(self.__url_nginx_sslclient, 'fiche.json')
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
                path_fiche_json = urllib.parse.urljoin(path_nginx, 'html', 'fiche.json')
                self.sauvegarder_fichier_data(path_fiche_json, fiche_contenu)
            else:
                self.__logger.warning("Error accessing fiche.json via https, response code %d" % reponse.status)
        except ValueNotAvailable:
            self.__logger.error("Local millegrille TLS not configured yet")
        except ClientConnectorError:
            self.__logger.exception("While loading fichier.json, nginx is unavailable")

    async def preparer_nginx(self):
        raise NotImplementedError("TODO")
        # self.__logger.info("Preparer nginx")

        # S'assurer que l'instance nginxinstall est supprimee
        # await nginx_installation_cleanup(self.__docker_handler)
        # configuration_modifiee = await asyncio.to_thread(self.verifier_repertoire_configuration)
        # self.__entretien_initial_complete = True
        # self.__logger.info("Configuration nginx prete (configuration modifiee? %s)" % configuration_modifiee)

        # if configuration_modifiee is True:
        #     await self.__context.reload_wait()

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

    async def refresh_configuration(self, reason: str):
        self.__logger.warning("NginxHandler refresh_configuration called - NOT IMPLEMENTED")
        # await self.__docker_handler.redemarrer_nginx(reason)


