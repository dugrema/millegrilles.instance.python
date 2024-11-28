import datetime

import aiohttp
import asyncio
import logging
import json
import math

from aiohttp import web
from os import path
from ssl import SSLContext
from typing import Optional

import millegrilles_instance.Exceptions
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.Manager import InstanceManager
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.messages import Constantes
from millegrilles_instance.InstallerInstance import installer_instance, configurer_idmg
from millegrilles_messages.messages.CleCertificat import CleCertificat


class WebServer:
    """
    Web access module
    """

    def __init__(self, manager: InstanceManager):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__manager = manager

        self.__app = web.Application()
        self.__ssl_context: Optional[SSLContext] = None

        self.__webrunner: Optional[WebRunner] = None
        self.__ipv6 = True

    async def setup(self):
        self._charger_configuration()
        self._preparer_routes()

        self.__webrunner = WebRunner(self.context, self.__app, ipv6=self.__ipv6)

    @property
    def context(self) -> InstanceContext:
        return self.__manager.context

    def _charger_configuration(self):
        self.context.configuration.parse_config()

    def _preparer_routes(self):
        self.__app.add_routes([
            web.get('/installation/api/info', self.handle_api_info),
            web.get('/installation/api/infoMonitor', self.handle_api_info),  # Deprecated, FIX dans coupdoeil
            web.get('/installation/api/csr', self.handle_api_csr),
            web.get('/installation/api/csrInstance', self.handle_api_csr_instance),
            web.get('/installation/api/etatCertificatWeb', self.handle_etat_certificat_web),
            web.get('/installation/api/appInstallationStatus', self.handle_application_installation_status),

            web.post('/installation/api/installer', self.handle_installer),
            web.post('/installation/api/configurerIdmg', self.handle_configurer_idmg),
            # web.post('/installation/api/changerDomaine', self.handle_changer_domaine),
            web.post('/installation/api/configurerMQ', self.handle_configurer_mq),
            web.post('/installation/api/installerCertificat', self.handle_installer_certificat),

            web.options('/installation/api/installer', self.options_cors),
            web.options('/installation/api/configurerMQ', self.options_cors),
            web.options('/installation/api/installerCertificat', self.options_cors),
        ])

    async def handle_api_info(self, request):
        try:
            reponse = {
                'instance_id': self.context.instance_id,
                'securite': self.context.securite,
                'idmg': self.context.idmg,
            }
        except ValueNotAvailable:
            reponse = {
                'instance_id': None,
                'securite': None,
                'idmg': None,
            }

        try:
            reponse['ca'] = self.context.ca.certificat_pem
        except AttributeError:
            pass

        try:
            reponse['certificat'] = self.context.signing_key.enveloppe.chaine_pem()
        except AttributeError:
            pass

        # Headers CORS
        headers = headers_cors()

        return web.json_response(headers=headers, data=reponse)

    async def handle_application_installation_status(self, request):
        status = {'ok': True}
        apps_status = self.context.application_status
        status['apps'] = apps_status.apps
        status['lastUpdate'] = math.floor(apps_status.last_update.timestamp())

        # Headers CORS
        headers = headers_cors()
        return web.json_response(headers=headers, data=status)

    async def handle_api_csr(self, _request):
        configuration = self.context.configuration
        url_issuer = configuration.certissuer_url
        path_csr = path.join(url_issuer, 'csr')
        headers = headers_cors()
        async with aiohttp.ClientSession() as session:
            async with session.get(path_csr) as resp:
                text_response = await resp.text()
                return web.Response(status=resp.status, text=text_response, headers=headers)

    async def handle_api_csr_instance(self, request):
        csr_genere = self.context.csr_genere
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
            resultat = await installer_instance(self.context, request, headers_response=headers)
            # Reload context with delay to allow sending response
            await self.context.delay_reload(0.5)
            return web.json_response({'ok': True}, headers=headers, status=200)
        except millegrilles_instance.Exceptions.RedemarrageException:
            # Reload context with delay to allow sending response
            await self.context.delay_reload(0.5)
            return web.json_response({'ok': True}, headers=headers, status=200)
        except:
            self.__logger.exception("Installation error")
            return web.Response(headers=headers, status=500)

    async def handle_configurer_idmg(self, request: web.Request):
        contenu = await request.json()
        self.__logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))
        return await configurer_idmg(self.__etat_instance, contenu)

    # async def handle_changer_domaine(self, request: web.Request):
    #     enveloppe_message = await request.json()
    #     self.__logger.debug("handle_changer_domaine contenu\n%s" % json.dumps(enveloppe_message, indent=2))
    #
    #     # Valider message - delegation globale
    #     enveloppe = await self.__etat_instance.validateur_message.verifier(enveloppe_message)
    #     if enveloppe.get_delegation_globale != Constantes.DELEGATION_GLOBALE_PROPRIETAIRE:
    #         self.__logger.error("Requete handle_configurer_mq() avec certificat sans delegation globale")
    #         return web.HTTPForbidden()
    #
    #     contenu = json.loads(enveloppe_message['contenu'])
    #
    #     # Conserver hostname
    #     hostname = contenu['hostname']
    #     self.__etat_instance.maj_configuration_json({'hostname': hostname})
    #     # await self.__etat_instance.reload_configuration()
    #     await self.__etat_instance.delay_reload_configuration(duration=datetime.timedelta(seconds=1))
    #
    #     return web.json_response({'ok': True}, headers=headers_cors())

    async def handle_configurer_mq(self, request: web.Request):
        enveloppe_message = await request.json()

        # Valider message - delegation globale
        enveloppe = await self.__etat_instance.validateur_message.verifier(enveloppe_message)
        if enveloppe.get_delegation_globale != Constantes.DELEGATION_GLOBALE_PROPRIETAIRE:
            self.__logger.error("Requete handle_configurer_mq() avec certificat sans delegation globale")
            return web.HTTPForbidden()

        contenu = json.loads(enveloppe_message['contenu'])
        self.__logger.debug("handle_configurer_mq contenu\n%s" % json.dumps(contenu, indent=2))

        config_dict = {
            'mq_host': contenu['host'],
            'mq_port': int(contenu['port']),
        }
        self.__etat_instance.maj_configuration_json(config_dict)
        # await self.__etat_instance.reload_configuration()
        await self.__etat_instance.delay_reload_configuration(duration=datetime.timedelta(seconds=1))

        return web.json_response({'ok': True}, headers=headers_cors())

    async def handle_installer_certificat(self, request: web.Request):
        """
        Sert a renouveller un certificat pousse via HTTPS
        :param request:
        :return:
        """
        contenu = await request.json()
        certificat = '\n'.join(contenu['certificat'])

        # Valider le nouveau certificat, s'assurer que c'est un certificat d'instance du bon niveau
        enveloppe = await self.context.verificateur_certificats.valider(certificat)
        exchanges = enveloppe.get_exchanges
        roles = enveloppe.get_roles

        # Roles doit inclure intance
        if 'instance' not in roles:
            self.__logger.error("Certificat recu ne contient pas role 'instance'")
            return web.HTTPBadRequest()

        # Roles doit inclure securite locale
        niveau_securite = self.context.securite
        if niveau_securite not in exchanges:
            self.__logger.error("Certificat recu ne contient pas niveau de securite  '%s'" % niveau_securite)
            return web.HTTPBadRequest()

        clecsr = self.__etat_instance.get_csr_genere()

        # Verifier que le certificat et la cle correspondent
        cle_pem = clecsr.get_pem_cle()
        clecert = CleCertificat.from_pems(cle_pem, certificat)
        if not clecert.cle_correspondent():
            raise ValueError('Cle et Certificat ne correspondent pas')

        # Installer le nouveau certificat d'instance
        self.__etat_instance.maj_clecert(clecert)

        # await self.__etat_instance.reload_configuration()
        await self.__etat_instance.delay_reload_configuration(duration=datetime.timedelta(seconds=1))

        return web.json_response({'ok': True}, headers=headers_cors())

    async def run(self):
        try:
            await self.__webrunner.start()
            self.__logger.info("Web server started on port %s" % self.context.configuration.port)
            await self.context.wait()
        except asyncio.CancelledError as e:
            if self.context.stopping is False:
                self.__logger.exception("Web server - thread cancelled, quitting")
                self.context.stop()
                raise ForceTerminateExecution()
            raise e
        except ForceTerminateExecution as e:
            raise e
        except:
            self.__logger.exception("Web server - Unhandled error")
        finally:
            # await self.__webrunner.stop()
            self.__logger.info("Web server stopped")


class WebRunner:

    def __init__(self, contexte: InstanceContext, app,
                 ipv6: Optional[bool] = False, port: Optional[int] = None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__contexte = contexte

        configuration = contexte.configuration
        self._runner = web.AppRunner(app)

        self.__ipv6 = ipv6

        if port is not None:
            self._port = port
        else:
            self._port = configuration.port

        self.__site: Optional[web.TCPSite] = None
        self.__site_ipv6: Optional[web.TCPSite] = None

    async def start(self):
        await self._runner.setup()
        ssl_context = self.charger_ssl()

        self.__site = web.TCPSite(self._runner, '0.0.0.0', self._port, ssl_context=ssl_context)

        if self.__ipv6 is True:
            self.__site_ipv6 = web.TCPSite(self._runner, '::', self._port, ssl_context=ssl_context)
            await self.__site_ipv6.start()

        await self.__site.start()

        self.__logger.debug("Web server started")

    async def stop(self):
        try:
            await self._runner.app.shutdown()
            self._runner.app.clear()  # Clear all sessions
            await self._runner.shutdown()
        except asyncio.CancelledError:
            self.__logger.warning('site.stop() %s cancelled' % self._port)

    def charger_ssl(self):
        ssl_context = SSLContext()
        configuration = self.__contexte.configuration
        ssl_context.load_cert_chain(configuration.web_cert_pem_path, configuration.web_key_pem_path)
        return ssl_context


def headers_cors() -> dict:

    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'DNT,User-Agent,X-Requested-With,If-Modified-Since,Cache-Control,Content-Type,Range',
        'Access-Control-Expose-Headers': 'Content-Length,Content-Range',
    }
