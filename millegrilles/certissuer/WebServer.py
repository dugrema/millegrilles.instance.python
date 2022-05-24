import asyncio
import logging

from aiohttp import web
from asyncio import Event
from asyncio.exceptions import TimeoutError
from os import path
from typing import Optional

from millegrilles.certissuer.Configuration import ConfigurationWeb
from millegrilles.certissuer.EtatCertissuer import EtatCertissuer


class WebServer:

    def __init__(self, etat_certissuer: EtatCertissuer):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_certissuer = etat_certissuer

        self.__configuration = ConfigurationWeb()
        self.__app = web.Application()
        self.__stop_event: Optional[Event] = None

    def setup(self, configuration: Optional[dict] = None):
        self._charger_configuration(configuration)
        self._preparer_routes()

    def _charger_configuration(self, configuration: Optional[dict] = None):
        self.__configuration.parse_config(configuration)

    def _preparer_routes(self):
        self.__app.add_routes([
            web.get('/csr', self.handle_csr),
            web.post('/installer', self.handle_installer),
        ])

    async def handle_csr(self, request):
        csr_str = self.__etat_certissuer.get_csr()
        return web.Response(text=csr_str)

    async def handle_installer(self, request):
        info_cert = await request.json()
        self.__etat_certissuer.sauvegarder_certificat(info_cert)

    async def entretien(self):
        self.__logger.debug('Entretien')

    async def run(self, stop_event: Optional[Event] = None):
        if stop_event is not None:
            self.__stop_event = stop_event
        else:
            self.__stop_event = Event()

        runner = web.AppRunner(self.__app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.__configuration.port)
        try:
            await site.start()
            self.__logger.info("Site demarre")

            while not self.__stop_event.is_set():
                await self.entretien()
                try:
                    await asyncio.wait_for(self.__stop_event.wait(), 30)
                except TimeoutError:
                    pass
        finally:
            self.__logger.info("Site arrete")
            await runner.cleanup()


# def main():
#     logging.basicConfig()
#     logging.getLogger(__name__).setLevel(logging.DEBUG)
#     logging.getLogger('millegrilles').setLevel(logging.DEBUG)
#
#     server = WebServer()
#     server.setup()
#     asyncio.run(server.run())
#
#
# if __name__  == '__main__':
#     main()
