import aiohttp
import logging
import ssl

from os import path
from typing import Optional

from aiohttp.client_exceptions import ClientConnectorError


class EntretienRabbitMq:

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__passwd_mq: Optional[str] = None
        self.__session: Optional[aiohttp.ClientSession] = None

        ca_path = etat_instance.configuration.instance_ca_pem_path
        self.__sslcontext = ssl.create_default_context(cafile=ca_path)

        self.__entretien_initial_complete = False
        self.__url_mq = 'https://127.0.0.1:8443'

    async def entretien(self):
        self.__logger.debug("entretien debut")

        try:
            pass
            # if self.__session is None:
            #     await self.creer_session()
            #
            # if self.__session is not None:
            #     try:
            #         path_alarm = path.join(self.__url_mq, 'api/health/checks/alarms')
            #         async with self.__session.get(path_alarm, ssl=self.__sslcontext) as reponse:
            #             pass
            #         self.__logger.debug("Reponse MQ : %s" % reponse)
            #
            #         if reponse.status == 200:
            #             pass  # OK
            #         elif reponse.status == 401:
            #             self.__logger.warning("Erreur MQ https, access denied (admin setup incomplet)")
            #         elif reponse.status == 503:
            #             self.__logger.warning("Erreur MQ https, healthcheck echec")
            #     except ClientConnectorError:
            #         self.__logger.exception("MQ n'est pas accessible")

        except Exception as e:
            self.__logger.exception("Erreur verification RabbitMQ https")

        self.__logger.debug("entretien fin")

    async def creer_session(self):
        if self.__etat_instance.configuration.instance_password_mq_path is not None:
            with open(self.__etat_instance.configuration.instance_password_mq_path, 'r') as fichier:
                password_mq = fichier.read().strip()
            basic_auth = aiohttp.BasicAuth('admin', password_mq)
            self.__session = aiohttp.ClientSession(auth=basic_auth)
