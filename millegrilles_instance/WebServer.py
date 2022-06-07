import aiohttp
import asyncio
import logging
import json

from aiohttp import web
from asyncio import Event
from asyncio.exceptions import TimeoutError, CancelledError
from os import path
from ssl import SSLContext
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_instance.Configuration import ConfigurationWeb
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstallerInstance import installer_instance, configurer_idmg


class WebServer:

    def __init__(self, etat_instance: EtatInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__app = web.Application()
        self.__stop_event: Optional[Event] = None
        self.__configuration = ConfigurationWeb()
        self.__ssl_context: Optional[SSLContext] = None

        self.__webrunner: Optional[WebRunner] = None
        self.__webrunner_443: Optional[WebRunner] = None

    def setup(self, configuration: Optional[dict] = None):
        self._charger_configuration(configuration)
        self._preparer_routes()

        self.__webrunner = WebRunner(self.__etat_instance, self.__configuration, self.__app)

    def _charger_configuration(self, configuration: Optional[dict] = None):
        self.__configuration.parse_config(configuration)

    def _preparer_routes(self):
        self.__app.add_routes([
            web.get('/', self.rediriger_root),

            web.get('/installation/api/info', self.handle_api_info),
            web.get('/installation/api/infoMonitor', self.handle_api_info),  # Deprecated, FIX dans coupdoeil
            web.get('/installation/api/csr', self.handle_api_csr),
            web.get('/installation/api/csrInstance', self.handle_api_csr_instance),
            web.get('/installation/api/etatCertificatWeb', self.handle_etat_certificat_web),

            web.post('/installation/api/installer', self.handle_installer),
            web.post('/installation/api/configurerIdmg', self.handle_configurer_idmg),

            web.options('/installation/api/installer', self.options_cors),

            # Application d'installation static React
            web.get('/installation/', self.installation_index_handler),
            web.get('/installation', self.installation_index_handler),

            web.static('/installation', self.__configuration.path_app_installation),
        ])

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

        # Headers CORS
        headers = headers_cors()

        return web.json_response(headers=headers, data=reponse)

    async def handle_api_csr(self, request):
        url_issuer = self.__etat_instance.certissuer_url
        path_csr = path.join(url_issuer, 'csr')
        headers = headers_cors()
        async with aiohttp.ClientSession() as session:
            async with session.get(path_csr) as resp:
                text_response = await resp.text()
                return web.Response(status=resp.status, text=text_response, headers=headers)

    async def handle_api_csr_instance(self, request):
        csr_genere = self.__etat_instance.get_csr_genere()
        csr_pem = csr_genere.get_pem_csr()
        headers = headers_cors()
        return web.Response(text=csr_pem, headers=headers)

    async def handle_etat_certificat_web(self, request):
        return web.HTTPNotImplemented()

    async def options_cors(self, request):
        headers = {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
            'Access-Control-Allow-Headers': 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range',
            'Access-Control-Max-Age': '1728000',
            'Content-Type': 'text/plain; charset=utf-8',
            'Content-Length': '0',
        }
        return web.HTTPNoContent(headers=headers)

    async def handle_installer(self, request):
        headers = headers_cors()
        try:
            resultat = await installer_instance(self.__etat_instance, request, headers_response=headers)

            if self.__webrunner_443 is not None:
                self.__logger.info("Desactiver server instance sur port 443 pour demarrer nginx")

                self.__logger.warning("Installation, redemarrer (peut pas arreter port 443 pour nginx)")
                self.__etat_instance.set_redemarrer(True)
                self.__stop_event.set()
                await self.__etat_instance.stop()

                # try:
                #     await self.__webrunner_443.stop()
                # except CancelledError:
                #     self.__logger.warning("webrunner port 443 cancelle")
                # self.__webrunner_443 = None

            return resultat
        except:
            self.__logger.exception("Erreur installation")
            return web.Response(headers=headers, status=500)

    async def handle_configurer_idmg(self, request: web.Request):
        contenu = await request.json()
        self.__logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))
        return await configurer_idmg(self.__etat_instance, contenu)

    async def entretien(self):
        self.__logger.debug('Entretien')

    async def run(self, stop_event: Optional[Event] = None):
        if stop_event is not None:
            self.__stop_event = stop_event
        else:
            self.__stop_event = Event()

        # Configuration pour site sur port 443 (utilise si nginx n'est pas configure)
        #niveau_securite_initial = self.__etat_instance.niveau_securite
        #if niveau_securite_initial != Constantes.SECURITE_PROTEGE:
        if self.__etat_instance.certificat_millegrille is None:  # Pas encore initialise
            self.__webrunner_443 = WebRunner(self.__etat_instance, self.__configuration, self.__app, port=443)

        try:
            if self.__webrunner_443 is not None:
                try:
                    await self.__webrunner_443.start()
                except OSError:
                    self.__logger.info("Port 443 non disponible (probablement nginx - OK)")
            await self.__webrunner.start()
            self.__logger.info("Site demarre")

            while not self.__stop_event.is_set():
                await self.entretien()
                try:
                    await asyncio.wait_for(self.__stop_event.wait(), 30)
                except TimeoutError:
                    pass

        finally:
            self.__logger.info("Site arrete")
            # await self.__webrunner.stop()


class WebRunner:

    def __init__(self, etat_instance: EtatInstance, configuration: ConfigurationWeb, app, port: Optional[int] = None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._etat_instance = etat_instance
        self._configuration = configuration
        self._runner = web.AppRunner(app)

        if port is not None:
            self._port = port
        else:
            self._port = self._configuration.port

        self.__site: Optional[web.TCPSite] = None

    async def start(self):
        await self._runner.setup()
        ssl_context = self.charger_ssl()
        self.__site = web.TCPSite(self._runner, '0.0.0.0', self._port, ssl_context=ssl_context)
        await self.__site.start()

    async def stop(self):
        raise NotImplementedError()
        # try:
        #     await self.__site.stop()
        # except CancelledError:
        #     self.__logger.warning('site.stop() %s cancelled' % self._port)

        # try:
        #     await asyncio.wait_for(self._runner.cleanup(), 1)
        # except CancelledError:
        #     self.__logger.warning('runner.cleanup() %s cancelled' % self._port)

    def charger_ssl(self):
        ssl_context = SSLContext()
        configuration = self._configuration
        ssl_context.load_cert_chain(configuration.web_cert_pem_path, configuration.web_key_pem_path)
        return ssl_context


def headers_cors() -> dict:

    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range',
        'Access-Control-Expose-Headers': 'Content-Length,Content-Range',
    }


def main():
    logging.basicConfig()
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    server = WebServer()
    server.setup()
    asyncio.run(server.run())


if __name__  == '__main__':
    main()
