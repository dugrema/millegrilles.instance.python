import aiohttp
import asyncio
import logging
import ssl

from typing import Optional

from asyncio import Event, TimeoutError


class EntretienRabbitMq:

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__passwd_mq: Optional[str] = None
        self.__session: Optional[aiohttp.ClientSession] = None

        ca_path = etat_instance.configuration.instance_ca_pem_path
        self.__sslcontext = ssl.create_default_context(cafile=ca_path)

    async def entretien(self):
        self.__logger.debug("entretien debut")

        try:
            if self.__session is None:
                if self.__etat_instance.configuration.instance_password_mq_path is not None:
                    with open(self.__etat_instance.configuration.instance_password_mq_path, 'r') as fichier:
                        password_mq = fichier.read().strip()
                    basic_auth = aiohttp.BasicAuth('admin', password_mq)
                    self.__session = aiohttp.ClientSession(auth=basic_auth)

            if self.__session is not None:
                async with self.__session.get('https://127.0.0.1:8443/api/health/checks/alarms', ssl=self.__sslcontext) as reponse:
                    pass
                self.__logger.debug("Reponse MQ : %s" % reponse)

                if reponse.status == 401:
                    self.__logger.warning("Erreur MQ https, tentative de configuration du compte admin")
                    await self.configurer_admin()

        except Exception as e:
            self.__logger.exception("Erreur verification RabbitMQ https")

        self.__logger.debug("entretien fin")

    async def configurer_admin(self):
        basic_auth = aiohttp.BasicAuth('guest', 'guest')
        async with aiohttp.ClientSession(auth=basic_auth) as session:
            async with session.get('https://127.0.0.1:8443/api/health/checks/alarms', ssl=self.__sslcontext) as reponse:
                pass
        self.__logger.debug("Reponse MQ config admin : %s" % reponse)

    async def ajouter_compte(self):
        raise NotImplementedError('todo')
