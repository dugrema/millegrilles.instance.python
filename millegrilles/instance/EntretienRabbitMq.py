import aiohttp
import asyncio
import logging
import ssl

from typing import Optional

from aiohttp.client_exceptions import ClientConnectorError
from asyncio import Event, TimeoutError


class EntretienRabbitMq:

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__passwd_mq: Optional[str] = None
        self.__session: Optional[aiohttp.ClientSession] = None

        ca_path = etat_instance.configuration.instance_ca_pem_path
        self.__sslcontext = ssl.create_default_context(cafile=ca_path)

        self.__entretien_initial_complete = False

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
                try:
                    async with self.__session.get('https://127.0.0.1:8443/api/health/checks/alarms', ssl=self.__sslcontext) as reponse:
                        pass
                    self.__logger.debug("Reponse MQ : %s" % reponse)

                    if reponse.status == 200:
                        if self.__entretien_initial_complete is False:
                            await self.entretien_initial()
                        pass  # OK
                    elif reponse.status == 401:
                        self.__logger.warning("Erreur MQ https, tentative de configuration du compte admin")
                        await self.configurer_admin()
                        await self.entretien_initial()
                    elif reponse.status == 503:
                        self.__logger.warning("Erreur MQ https, healthcheck echec")
                except ClientConnectorError:
                    self.__logger.exception("MQ n'est pas accessible")

        except Exception as e:
            self.__logger.exception("Erreur verification RabbitMQ https")

        self.__logger.debug("entretien fin")

    async def configurer_admin(self):
        with open(self.__etat_instance.configuration.instance_password_mq_path, 'r') as fichier:
            password_mq = fichier.read().strip()

        basic_auth = aiohttp.BasicAuth('guest', 'guest')
        async with aiohttp.ClientSession(auth=basic_auth) as session:
            data = {
                'tags': 'administrator',
                'password': password_mq,
            }

            async with session.put('https://127.0.0.1:8443/api/users/admin', json=data, ssl=self.__sslcontext) as response:
                self.__logger.debug("Reponse creation admin : %s" % response)

    async def entretien_initial(self):
        async with self.__session.delete('https://127.0.0.1:8443/api/users/guest', ssl=self.__sslcontext) as response:
            self.__logger.debug("Reponse suppression guest : %s" % response)

        self.__entretien_initial_complete = True

    async def ajouter_compte(self):
        raise NotImplementedError('todo')

