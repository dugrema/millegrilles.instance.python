import asyncio
import datetime
import json
import os
import pathlib
import logging
import sys
from asyncio import TaskGroup

import pytz

from json import JSONDecodeError

from typing import Optional

import josepy as jose

from acme import challenges
from acme import client
from acme import crypto_util
from acme import errors
from acme import messages

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_messages.bus.BusExceptions import ConfigurationFileError
from millegrilles_messages.messages.CleCertificat import CleCertificat

# Prod
DIRECTORY_URL_PROD = 'https://acme-v02.api.letsencrypt.org/directory'
# This is the staging point for ACME-V2 within Let's Encrypt.
DIRECTORY_URL_STAGING = 'https://acme-staging-v02.api.letsencrypt.org/directory'

USER_AGENT = 'python-acme'

# Account key size
ACC_KEY_BITS = 2048
# Certificate private key size
CERT_PKEY_BITS = 2048

RENEWAL_PERIOD_DAYS = 14
# RENEWAL_PERIOD_DAYS = 90

LOGGER = logging.getLogger(__name__)

class AcmeHandler:

    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)

        self.__context = context
        # self.__path_secrets = pathlib.Path(PATH_SECRETS)
        self.__account_key_path: Optional[pathlib.Path] = None
        self.__account_res_path: Optional[pathlib.Path] = None
        # self.__acc_key: Optional[jose.JWKRSA] = None
        self.__client: Optional[client.ClientV2] = None
        self.__regr: Optional[messages.RegistrationResource] = None

        if os.environ.get('STAGING'):
            self.__logger.warning("using LetsEncrypt staging directory")
            self.__le_directory = DIRECTORY_URL_STAGING
        else:
            self.__le_directory = DIRECTORY_URL_PROD

        self.__email: Optional[str] = None
        self.__additional_domains: Optional[list[str]] = None

        self.__current_certificate: Optional[CleCertificat] = None

    async def setup(self):
        acme_config_path = pathlib.Path(self.__context.configuration.path_configuration, 'acme.json')
        try:
            with open(acme_config_path, 'rt') as fp:
                config_acme = json.load(fp)
        except JSONDecodeError:
            self.__logger.warning("Error loading ACME email value from acme.json")
        except FileNotFoundError:
            self.__logger.debug("No acme.json file found")
        else:
            try:
                self.__email = config_acme['email']
            except KeyError:
                pass  # No email
            try:
                self.__additional_domains = config_acme['additionalDomains']
            except KeyError:
                pass  # No additional domains

        email = os.environ.get('EMAIL')
        if email:
            # Email override
            self.__email = email

        try:
            self.__current_certificate = await load_current_certificate(self.__context.configuration.path_secrets)
        except FileNotFoundError:
            self.__logger.info("Current web certificate not present")
        except ValueError:
            self.__logger.info("Current web certificate invalid or self-signed")

    async def __initialize_client(self):
        if self.__client is not None:
            raise Exception('Let\'s Encrypt Client already initialized')

        path_secrets = self.__context.configuration.path_secrets
        self.__account_key_path = pathlib.Path(path_secrets, 'certbot_key.json')
        self.__account_res_path = pathlib.Path(path_secrets, 'certbot_account.json')

        acc_key = await get_account_key(self.__account_key_path)
        le_client = await create_client(self.__le_directory, acc_key)
        regr = await get_account(self.__account_res_path, self.__email, le_client)

        self.__client = le_client
        self.__regr = regr

    async def issue_certificate(self) -> CleCertificat:
        """
        Issues a new certificate. Use for initial issuance or forced renewal.
        """
        if self.__client is None:
            await self.__initialize_client()

        # Filter known hostnames to remove any local (non-internet) names (e.g. localhost, test1, etc.)
        hostnames = [h for h in self.__context.hostnames if len(h.split('.')) > 0]
        if len(hostnames) == 0:
            raise Exception('No hostnames found')
        self.__logger.debug("Local hostnames: %s", hostnames)

        if self.__additional_domains:
            self.__logger.debug("Additional domains: %s", self.__additional_domains)
            hostnames.extend(self.__additional_domains)

        path_html = pathlib.Path(self.__context.configuration.path_nginx, 'html')
        cle_certificat = await issue_certificate(path_html, hostnames, self.__client)
        path_secrets = self.__context.configuration.path_secrets
        await asyncio.to_thread(rotate_certificate, path_secrets, cle_certificat)

        self.__current_certificate = cle_certificat

        return self.__current_certificate

    async def run(self):
        async with TaskGroup() as group:
            group.create_task(self.__maintain_certificate_thread())

    async def __maintain_certificate_thread(self):
        """
        Thread that auto-renews an ACME provided certificate.
        """
        while self.__context.stopping is False:
            if self.__current_certificate:
                not_after_date = self.__current_certificate.enveloppe.not_valid_after
                expiration = not_after_date - datetime.timedelta(days=RENEWAL_PERIOD_DAYS)
                now = datetime.datetime.now(tz=pytz.UTC)
                if expiration < now:
                    self.__logger.info("Renewing web certificate with LE")
                    try:
                        clecert = await self.issue_certificate()
                        self.__logger.info("Web certificate renewed, new expiration is %s" % clecert.enveloppe.not_valid_after)
                    except:
                        self.__logger.exception("Error renewing certificate")
                else:
                    # Wait until renewal is due
                    wait_time = expiration - now
                    self.__logger.info("Waiting until renewal for web certificate: %s (%s)" % (expiration, wait_time))
                    await self.__context.wait(wait_time.seconds + 120)
                    continue  # Renew

            # Wait 30 minutes until retry
            await self.__context.wait(1800)

    def get_configuration(self) -> dict:
        return {'email': self.__email, 'additionalDomains': self.__additional_domains}

    async def update_configuration(self, configuration: dict):
        acme_config_path = pathlib.Path(self.__context.configuration.path_configuration, 'acme.json')
        try:
            with open(acme_config_path, 'rt') as fp:
                config_acme = json.load(fp)
        except (KeyError, JSONDecodeError):
            self.__logger.warning("Error loading ACME value from acme.json, overriding file")
            config_acme = dict()
        except FileNotFoundError:
            config_acme = dict()  # Ok, new file

        try:
            email = configuration['email']
            if email == '':
                email = None
            config_acme['email'] = email
            self.__email = email
        except KeyError:
            self.__email = None

        try:
            additional_domains = configuration['additionalDomains']
            if len(additional_domains) == 0:
                additional_domains = None
            config_acme['additionalDomains'] = additional_domains
            self.__additional_domains = additional_domains
        except KeyError:
            self.__additional_domains = None

        # Override file
        with open(acme_config_path, 'wt') as fp:
            json.dump(config_acme, fp)


async def new_csr_comp(domain_names: list[str]):
    """Create certificate signing request."""
    # EC private key.
    private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())

    # RSA
    # rsa_pem = public_key.public_bytes(encoding=serialization.Encoding.PEM,
    #                                   format=serialization.PublicFormat.SubjectPublicKeyInfo)
    # private_key = await asyncio.to_thread(rsa.generate_private_key, public_exponent=65537, key_size=CERT_PKEY_BITS)

    pkey_pem = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                         serialization.NoEncryption())

    csr_pem = crypto_util.make_csr(pkey_pem, domain_names)
    return pkey_pem, csr_pem


async def get_account_key(keypath: pathlib.Path) -> jose.JWKRSA:
    try:
        with open(keypath, 'rt') as fp:
            key_str = fp.read()
        return jose.JWKRSA.json_loads(key_str)
    except FileNotFoundError:
        LOGGER.info("Creating new ACME account with certbot")
        rsa_key = await asyncio.to_thread(rsa.generate_private_key, public_exponent=65537, key_size=ACC_KEY_BITS, backend=default_backend())
        acc_key = jose.JWKRSA(key=rsa_key)
        with open(keypath, 'wt') as fp:
            fp.write(acc_key.json_dumps())
        LOGGER.info("ACME account created")
    return acc_key


async def create_client(directory_path: str, acc_key: jose.JWKRSA) -> client.ClientV2:
    net = client.ClientNetwork(acc_key, user_agent=USER_AGENT)
    # directory = client.ClientV2.get_directory(DIRECTORY_URL_PROD, net)
    directory = client.ClientV2.get_directory(directory_path, net)
    client_acme = client.ClientV2(directory, net=net)
    return client_acme


async def get_account(account_res_path: pathlib.Path, email_str: Optional[str],
                      client_acme: client.ClientV2) -> messages.RegistrationResource:
    # Terms of Service URL is in client_acme.directory.meta.terms_of_service
    # Registration Resource: regr
    # Creates account with contact information.
    try:
        with open(account_res_path, 'rt') as fp:
            regr = messages.RegistrationResource.from_json(json.load(fp))
            regr_state = await asyncio.to_thread(client_acme.query_registration, regr)
            return regr_state.body
    except FileNotFoundError:
        if email_str is None:
            raise ValueError('missing email - set as environment varilable EMAIL')
        email = (email_str)
        regr: messages.RegistrationResource = await asyncio.to_thread(
            client_acme.new_account,
            messages.NewRegistration.from_data(
            email=email, terms_of_service_agreed=True)
        )
        with open(account_res_path, 'wt') as fp:
            json.dump(regr.to_json(), fp)
        return regr
    pass


def select_http01_chall(orderr: messages.OrderResource) -> messages.ChallengeBody:
    """Extract authorization resource from within order resource."""
    # Authorization Resource: authz.
    # This object holds the offered challenges by the server and their status.
    authz_list = orderr.authorizations

    for authz in authz_list:
        # Choosing challenge.
        # authz.body.challenges is a set of ChallengeBody objects.
        for i in authz.body.challenges:
            # Find the supported challenge.
            if isinstance(i.chall, challenges.HTTP01):
                return i

    raise Exception('HTTP-01 challenge was not offered by the CA server.')


def perform_http01(path_html: pathlib.Path, client_acme: client.ClientV2, challb: messages.ChallengeBody,
                   orderr: messages.OrderResource):
    """Perform HTTP-01 challenge."""

    response, validation = challb.response_and_validation(client_acme.net.key)
    challenge_received_path = pathlib.Path(challb.chall.path)
    challenge_received_path = challenge_received_path.parts[1:]
    challenge_local_path = pathlib.Path(path_html, *challenge_received_path)

    # Ensure acme-challenge path exists
    challenge_local_path.parent.mkdir(parents=True, exist_ok=True)

    with open(challenge_local_path, 'wt') as fp:
        fp.write(validation)

    try:
        # Let the CA server know that we are ready for the challenge.
        client_acme.answer_challenge(challb, response)

        # Wait for challenge status and then issue a certificate.
        # It is possible to set a deadline time.
        finalized_orderr = client_acme.poll_and_finalize(orderr)

        return finalized_orderr.fullchain_pem
    finally:
        # Remove challenge file
        challenge_local_path.unlink(missing_ok=True)


async def issue_certificate(path_html: pathlib.Path, domains: list[str], client_acme: client.ClientV2) -> CleCertificat:
    # Create domain private key and CSR
    pkey_pem, csr_pem = await new_csr_comp(domains)
    # Issue certificate
    orderr: messages.OrderResource = await asyncio.to_thread(client_acme.new_order, csr_pem)
    challb = select_http01_chall(orderr)

    cert = await asyncio.to_thread(perform_http01, path_html, client_acme, challb, orderr)
    LOGGER.debug("Received new certificate\n%s" % cert)

    cle_certificat = CleCertificat.from_pems(pkey_pem, cert)
    if cle_certificat.cle_correspondent() is False:
        raise ValueError("Error - web cert/key do not match")

    LOGGER.info("New web certificate expiry: %s" % cle_certificat.enveloppe.not_valid_after)

    return cle_certificat

def rotate_certificate(path_secrets: pathlib.Path, cle_certificat: CleCertificat):
    path_key_new = pathlib.Path(path_secrets, 'pki.web.key.new')
    path_key = pathlib.Path(path_secrets, 'pki.web.key')
    path_key_old = pathlib.Path(path_secrets, 'pki.web.key.old')
    path_cert_new = pathlib.Path(path_secrets, 'pki.web.cert.new')
    path_cert = pathlib.Path(path_secrets, 'pki.web.cert')
    path_cert_old = pathlib.Path(path_secrets, 'pki.web.cert.old')

    with open(path_key_new, 'wb') as fp:
        fp.write(cle_certificat.private_key_bytes())
    with open(path_cert_new, 'wt') as fp:
        pem_chain = '\n'.join(cle_certificat.enveloppe.chaine_pem())
        fp.write(pem_chain)

    path_key_old.unlink(missing_ok=True)
    path_cert_old.unlink(missing_ok=True)
    try:
        path_key.rename(path_key_old)
    except FileNotFoundError:
        pass
    try:
        path_cert.rename(path_cert_old)
    except FileNotFoundError:
        pass

    path_key_new.rename(path_key)
    path_cert_new.rename(path_cert)
    LOGGER.info("Saved new certificate to %s" % path_key)

    pass


async def load_current_certificate(secret_path: pathlib.Path) -> CleCertificat:
    path_cert = pathlib.Path(secret_path, 'pki.web.cert')
    path_key = pathlib.Path(secret_path, 'pki.web.key')
    clecert: CleCertificat = await asyncio.to_thread(CleCertificat.from_files, path_key, path_cert)

    if clecert.enveloppe.is_ca:
        raise ValueError("Self-signed certificate")

    if clecert.cle_correspondent() is False:
        raise ValueError('Web key/cert do not correspond')

    return clecert


async def main():
    LOGGER.info("Starting")
    config = ConfigurationInstance.load()
    try:
        context = InstanceContext(config)
        context.reload()
    except ConfigurationFileError as e:
        LOGGER.error("Error loading configuration files %s, quitting" % str(e))
        sys.exit(1)  # Quit

    handler = AcmeHandler(context)
    await handler.setup()
    # clecert = await handler.issue_certificate()
    # LOGGER.info("New web certificate expiry: %s" % clecert.enveloppe.not_valid_after)

    LOGGER.info("Waiting until renewal")
    await handler.run()

    LOGGER.info("Done")


if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    asyncio.run(main())
