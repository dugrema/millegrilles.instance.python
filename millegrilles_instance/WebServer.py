import aiohttp
import asyncio
import logging

from aiohttp import web
from asyncio import Event
from asyncio.exceptions import TimeoutError
from os import path
from ssl import SSLContext
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_instance.Configuration import ConfigurationWeb
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstallerInstance import installer_instance


class WebServer:

    def __init__(self, etat_instance: EtatInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__app = web.Application()
        self.__stop_event: Optional[Event] = None
        self.__configuration = ConfigurationWeb()
        self.__ssl_context: Optional[SSLContext] = None

        self.__site_web_443 = None

    def setup(self, configuration: Optional[dict] = None):
        self._charger_configuration(configuration)
        self._preparer_routes()
        self._charger_ssl()

    def _charger_configuration(self, configuration: Optional[dict] = None):
        self.__configuration.parse_config(configuration)

    def _preparer_routes(self):
        self.__app.add_routes([
            web.get('/', self.rediriger_root),

            web.get('/installation/api/info', self.handle_api_info),
            web.get('/installation/api/csr', self.handle_api_csr),
            web.get('/installation/api/etatCertificatWeb', self.handle_etat_certificat_web),

            web.post('/installation/api/installer', self.handle_installer),

            # Application d'installation static React
            web.get('/installation/', self.installation_index_handler),
            web.get('/installation', self.installation_index_handler),
            web.static('/installation', self.__configuration.path_app_installation),
        ])

    def _charger_ssl(self):
        self.__ssl_context = SSLContext()
        self.__ssl_context.load_cert_chain(self.__configuration.web_cert_pem_path,
                                           self.__configuration.web_key_pem_path)

    async def rediriger_root(self, request):
        return web.HTTPTemporaryRedirect(location='/installation')

    async def installation_index_handler(self, request):
        path_app_installation = self.__configuration.path_app_installation
        path_index = path.join(path_app_installation, 'index.html')
        return web.FileResponse(path_index)

    async def handle_api_info(self, request):
        # action = request.match_info['action']
        # print("ACTION! %s" % action)
        reponse = {
            'instance_id': self.__etat_instance.instance_id,
            'securite': self.__etat_instance.niveau_securite,
            'idmg': self.__etat_instance.idmg,
        }
        try:
            reponse['ca'] = self.__etat_instance.certificat_millegrille.certificat_pem
        except AttributeError:
            pass
        try:
            reponse['certificat'] = self.__etat_instance.clecertificat.enveloppe.chaine_pem()
        except AttributeError:
            pass

        return web.json_response(data=reponse)

    async def handle_api_csr(self, request):
        url_issuer = self.__etat_instance.certissuer_url
        path_csr = path.join(url_issuer, 'csr')
        async with aiohttp.ClientSession() as session:
            async with session.get(path_csr) as resp:
                text_response = await resp.text()
                return web.Response(status=resp.status, text=text_response)

    async def handle_etat_certificat_web(self, request):
        return web.HTTPNotImplemented()

    async def handle_installer(self, request):
        try:
            resultat = await installer_instance(self.__etat_instance, request)
            if self.__site_web_443 is not None:
                self.__logger.info("Desactiver server instance sur port 443 pour demarrer nginx")
                await self.__site_web_443.shutdown()
                self.__site_web_443 = None
            return resultat
        except:
            self.__logger.exception("Erreur installation")
            return web.Response(status=500)

    async def entretien(self):
        self.__logger.debug('Entretien')

    async def run(self, stop_event: Optional[Event] = None):
        if stop_event is not None:
            self.__stop_event = stop_event
        else:
            self.__stop_event = Event()

        runner = web.AppRunner(self.__app)
        await runner.setup()
        port = self.__configuration.port
        # Configuration pour site sur port 443 (utilise si nginx n'est pas configure)
        niveau_securite_initial = self.__etat_instance.niveau_securite
        if niveau_securite_initial != Constantes.SECURITE_PROTEGE:
            self.__site_web_443 = web.AppRunner(self.__app)
            await self.__site_web_443.setup()
        site = web.TCPSite(runner, '0.0.0.0', port, ssl_context=self.__ssl_context)
        try:
            if self.__site_web_443 is not None:
                try:
                    site_443 = web.TCPSite(self.__site_web_443, '0.0.0.0', 443, ssl_context=self.__ssl_context)
                    await site_443.start()
                except OSError:
                    self.__logger.info("Port 443 non disponible (probablement nginx - OK)")
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
