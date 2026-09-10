import asyncio
import datetime
import logging

from asyncio import TaskGroup

import pytz

from millegrilles_messages.messages import Constantes as MilleGrillesConstantes

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.SystemdUtil import restart_compose_applications, restart_middleware, restart_nginx
from millegrilles_instance.apps.Certificates import renew_certificates, signer_module_certissuer, signer_module_core, \
    check_certissuer_available, CertificateConfiguration


class CertificatesManager:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context

        self.__applications_changed = asyncio.Event()
        self.__stopping = asyncio.Event()

        self.__initial_refresh_done = asyncio.Event()

    async def wait_initial_refresh_done(self):
        await self.__initial_refresh_done.wait()

    async def __stop_thread(self):
        await self.__context.wait()
        self.__stopping.set()

    async def run(self):
        self.__logger.debug("CertificatesManager thread started")
        try:
            await asyncio.wait_for(self.__context.certificates_generated.wait(), 30)
        except asyncio.TimeoutError:
            return
        if self.__context.stopping:
            return  # Closing
        try:
            async with TaskGroup() as group:
                group.create_task(self.__stop_thread())
                group.create_task(self.__renew_thread())
        except *Exception as e:  # Fail on first exception
            raise e
        self.__logger.debug("CertificatesManager thread done")

    async def __renew_thread(self):
        """
        Thread that manages certificates that are about to expire. Refreshes the certificates and reloads the
        docker compose services.
        """
        await self.__context.wait(10)
        self.__logger.info("Starting certificate renewal check thread")
        while self.__context.stopping is False:
            try:
                await self.__renew_certificates()
            except Exception:
                self.__logger.exception("Error renewing application certificates in manager")
            try:
                await self.__conditional_renew_manager()
            except Exception:
                self.__logger.exception("Error renewing manager certificate")
            await self.__context.wait(3600)
        self.__logger.info("Stopping certificate renewal check thread")

    async def __renew_certificates(self):
        renewed_config = await renew_certificates(self.__context)
        if len(renewed_config) == 0:
            self.__logger.debug("No certificates to renew")
            return  # Done

        names_renewed: set[str] = set([c['name'] for c in renewed_config])

        # Possible improvements:
        #   - read .yml files and extract service names directly
        #   - use docker compose restart on individual services

        try:
            names_renewed.remove('nginx')  # Hard-coded module name
            nginx_renewed = True
        except KeyError:
            nginx_renewed = False

        middleware_renewed = False
        # Hard-coded module names
        if self.__context.securite == MilleGrillesConstantes.SECURITE_PROTEGE:
            middleware_list = ['mq', 'mongo', 'midcompte', 'redis', 'ceduleur', 'webauth']
        else:
            middleware_list = ['redis', 'webauth']
        for name in middleware_list:
            try:
                names_renewed.remove(name)
                middleware_renewed = True
            except KeyError:
                pass

        # Anything left is in the applications.yml file
        applications_renewed = len(names_renewed) > 0

        instance_name = self.__context.configuration.instance_name
        if nginx_renewed:
            self.__logger.info("Certificates updated, reloading nginx")
            await asyncio.to_thread(restart_nginx, instance_name)

        if not self.__context.configuration.is_docker_disabled:

            if applications_renewed:
                self.__logger.info("Certificates updated, restarting applications")
                await asyncio.to_thread(restart_compose_applications, instance_name)

            if middleware_renewed:
                # Note : restarting the middleware potentially cuts the connection to MQ (closes the manager)
                self.__logger.warning("Certificates updated, restarting middleware (MQ may restart - this crashes the manager)")
                await asyncio.to_thread(restart_middleware, instance_name)

        self.__logger.info("Modules have been restarted after certificate renewal")

    async def __conditional_renew_manager(self):
        signing_key = self.__context.signing_key
        expiration = signing_key.enveloppe.not_valid_after
        now = datetime.datetime.now(tz=pytz.UTC)
        if expiration - now < datetime.timedelta(days=7):
            self.__logger.debug(f"Manager certificate can be renewed, expires on {expiration}")
            await self.__renew_manager_certificate()
            self.__logger.debug(f"Manager certificate renewed, reloading configuration")
            await self.__context.reload_wait()

    async def __renew_manager_certificate(self):
        if self.__context.securite in [MilleGrillesConstantes.SECURITE_PROTEGE, MilleGrillesConstantes.SECURITE_SECURE]:
            exchanges = [MilleGrillesConstantes.SECURITE_PROTEGE, MilleGrillesConstantes.SECURITE_PRIVE, MilleGrillesConstantes.SECURITE_PUBLIC]
        elif self.__context.securite == MilleGrillesConstantes.SECURITE_PRIVE:
            exchanges = [MilleGrillesConstantes.SECURITE_PRIVE, MilleGrillesConstantes.SECURITE_PUBLIC]
        else:
            exchanges = [MilleGrillesConstantes.SECURITE_PUBLIC]
        cert_config = CertificateConfiguration(
            name='manager',
            roles=[MilleGrillesConstantes.DOMAINE_INSTANCE, 'manager'],
            exchanges=exchanges,
            domaines=None,
            dns=None,
            split=False,
            key_path=None,
            cert_path=None,
            passwords=None
        )
        cert_issuer_available = await check_certissuer_available(self.__context)
        if not cert_issuer_available:
            # Ensure that we have access to the MQ producer
            producer = await asyncio.wait_for(self.__context.get_producer(), 1)
        else:
            producer = None
        if cert_issuer_available:
            cle_certificat = signer_module_certissuer(self.__context.configuration, cert_config, self.__context.formatteur)
        elif producer:
            cle_certificat = await signer_module_core(producer, self.__context, cert_config)
        else:
            raise Exception('No means of accessing certissuer found')

        key_pem = cle_certificat.private_key_bytes().decode('utf-8')
        new_certificate = cle_certificat.enveloppe
        cert_pem = "\n".join(new_certificate.chaine_pem()) + "\n"

        secrets_path = self.__context.configuration.path_millegrilles / "secrets"
        pem_path = secrets_path / "manager.pem"
        with open(pem_path, "w") as pem_file:
            pem_file.write(key_pem)
            pem_file.write("\n")
            pem_file.write(cert_pem)
