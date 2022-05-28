import asyncio
import json
import logging

from aiohttp import web
from asyncio import Event
from asyncio.exceptions import TimeoutError
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles.certissuer.Configuration import ConfigurationWeb
from millegrilles.certissuer.EtatCertissuer import EtatCertissuer
from millegrilles.certissuer.CertificatHandler import CertificatHandler


class WebServer:

    def __init__(self, etat_certissuer: EtatCertissuer):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_certissuer = etat_certissuer

        self.__configuration = ConfigurationWeb()
        self.__app = web.Application()
        self.__certificat_handler = CertificatHandler(self.__configuration, self.__etat_certissuer)
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
            web.post('/signerModule', self.handle_signer_module),
        ])

    async def handle_csr(self, request):
        csr_str = self.__etat_certissuer.get_csr()
        return web.Response(text=csr_str)

    async def handle_installer(self, request):
        info_cert = await request.json()
        self.__logger.debug("handle_installer params\n%s" % json.dumps(info_cert, indent=2))

        try:
            await self.__etat_certissuer.sauvegarder_certificat(info_cert)
            self.__logger.debug("Sauvegarde du certificat intermediaire OK")
        except:
            self.__logger.exception("Erreur sauvegarde certificat")
            return web.HTTPForbidden()

        # Generer le certificat pour l'application d'instance
        csr_instance = info_cert['csr_instance']
        securite = info_cert['securite']
        cert_instance = self.__certificat_handler.generer_certificat_instance(csr_instance, securite)
        self.__logger.debug("Nouveau certificat d'instance\n%s" % cert_instance)
        return web.json_response({'certificat': cert_instance}, status=201)

    async def handle_signer_module(self, request):
        info_cert = await request.json()
        self.__logger.debug("handle_installer params\n%s" % json.dumps(info_cert, indent=2))

        # Valider signature de request (doit etre role instance, niveau de securite suffisant pour exchanges)
        enveloppe = await self.__etat_certissuer.validateur_messages.verifier(info_cert)

        # Le certificat doit avoir le role instance ou core
        roles_enveloppe = enveloppe.get_roles
        if 'instance' not in roles_enveloppe and 'core' not in roles_enveloppe:
            return web.HTTPForbidden()

        # Les niveaux de securite demandes doivent etre supporte par le certificat demandeur
        securite_enveloppe = enveloppe.get_exchanges
        try:
            for ex in info_cert['exchanges']:
                if ex == Constantes.SECURITE_SECURE:
                    ex = Constantes.SECURITE_PROTEGE  # Niveau protege permet de creer certificat secure
                if ex not in securite_enveloppe:
                    self.__logger.info('Niveau de securite %s demande par un certificat qui ne le supporte pas' % ex)
                    return web.HTTPForbidden()
        except KeyError:
            pass

        chaine = self.__certificat_handler.generer_certificat_module(info_cert)
        return web.json_response({'certificat': chaine})

    async def entretien(self):
        self.__logger.debug('Entretien')
        try:
            await self.__etat_certissuer.entretien()
        except:
            self.__logger.exception("Erreur entretien etat_certissuer")

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
