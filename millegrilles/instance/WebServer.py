import asyncio
import logging

from aiohttp import web
from asyncio import Event
from asyncio.exceptions import TimeoutError
from os import path
from typing import Optional

from millegrilles.instance.Configuration import ConfigurationWeb


class WebServer:

    def __init__(self, stop_event: Optional[Event] = None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__app = web.Application()
        self.__stop_event = stop_event
        self.__configuration = ConfigurationWeb()

    async def handle(self, request):
        name = request.match_info.get('name', "Anonymous")
        text = "Hello, " + name
        return web.Response(text=text)

    def setup(self, configuration: Optional[dict] = None):
        self._charger_configuration(configuration)
        self._preparer_routes()

    def _charger_configuration(self, configuration: Optional[dict] = None):
        self.__configuration.parse_config(configuration)

    def _preparer_routes(self):
        self.__app.add_routes([
            # Application d'installation static React
            web.get('/installation', self.index_request),
            web.get('/installation/', self.index_request),
            web.static('/installation', self.__configuration.path_app_installation),
        ])

    async def index_request(self, request):
        path_app_installation = self.__configuration.path_app_installation
        path_index = path.join(path_app_installation, 'index.html')
        return web.FileResponse(path_index)

    async def entretien(self):
        self.__logger.debug('Entretien')

    async def run(self):
        if self.__stop_event is None:
            self.__stop_event = Event()

        runner = web.AppRunner(self.__app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', 8080)
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


def main():
    logging.basicConfig()
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    server = WebServer()
    server.setup()
    asyncio.run(server.run())


if __name__  == '__main__':
    main()
