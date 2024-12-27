import asyncio
import json
import os
import pathlib
import logging
import sys

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
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_messages.bus.BusExceptions import ConfigurationFileError
from millegrilles_messages.messages.CleCertificat import CleCertificat

# Prod
DIRECTORY_URL_PROD = 'https://acme-v02.api.letsencrypt.org/directory'

# This is the staging point for ACME-V2 within Let's Encrypt.
DIRECTORY_URL_STAGING = 'https://acme-staging-v02.api.letsencrypt.org/directory'
USER_AGENT = 'python-acme'

# PATH_WELLKNOWN = '/var/opt/millegrilles/nginx/html'
# PATH_SECRETS = '/var/opt/millegrilles/secrets'

# Account key size
ACC_KEY_BITS = 2048

# Certificate private key size
CERT_PKEY_BITS = 2048

# Domain name for the certificate.
# DOMAIN = 'chalet2.pivoine.maceroc.com'

LOGGER = logging.getLogger(__name__)

class CertbotHandler:

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

        self.__email = 'md.accounts1@mdugre.info'

    async def setup(self):
        path_secrets = self.__context.configuration.path_secrets
        self.__account_key_path = pathlib.Path(path_secrets, 'certbot_key.json')
        self.__account_res_path = pathlib.Path(path_secrets, 'certbot_account.json')

        acc_key = await get_account_key(self.__account_key_path)
        self.__client = await create_client(acc_key)
        self.__regr = await get_account(self.__account_res_path, self.__email, self.__client)

    async def issue_certificate(self) -> CleCertificat:
        # Filter known hostnames to remove any local (non-internet) names (e.g. localhost, test1, etc.)
        hostnames = [h for h in self.__context.hostnames if len(h.split('.')) > 0]
        if len(hostnames) == 0:
            raise Exception('No hostnames found')
        path_html = pathlib.Path(self.__context.configuration.path_nginx, 'html')
        cert, key = await issue_certificate(path_html, hostnames, self.__client)
        path_secrets = self.__context.configuration.path_secrets
        await asyncio.to_thread(rotate_certificate, path_secrets, cert, key)
        return CleCertificat.from_pems(key, cert)


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


async def create_client(acc_key: jose.JWKRSA) -> client.ClientV2:
    net = client.ClientNetwork(acc_key, user_agent=USER_AGENT)
    # directory = client.ClientV2.get_directory(DIRECTORY_URL_PROD, net)
    directory = client.ClientV2.get_directory(DIRECTORY_URL_STAGING, net)
    client_acme = client.ClientV2(directory, net=net)
    return client_acme


async def get_account(account_res_path: pathlib.Path, email_str: str, client_acme: client.ClientV2) -> messages.RegistrationResource:
    # Terms of Service URL is in client_acme.directory.meta.terms_of_service
    # Registration Resource: regr
    # Creates account with contact information.
    try:
        with open(account_res_path, 'rt') as fp:
            regr = messages.RegistrationResource.from_json(json.load(fp))
            regr_state = await asyncio.to_thread(client_acme.query_registration, regr)
            return regr_state.body
    except FileNotFoundError:
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


async def issue_certificate(path_html: pathlib.Path, domains: list[str], client_acme: client.ClientV2) -> (str, bytes):
    # Create domain private key and CSR
    pkey_pem, csr_pem = await new_csr_comp(domains)
    # Issue certificate
    orderr: messages.OrderResource = await asyncio.to_thread(client_acme.new_order, csr_pem)
    challb = select_http01_chall(orderr)

    cert = await asyncio.to_thread(perform_http01, path_html, client_acme, challb, orderr)
    LOGGER.info("Received new certificate\n%s" % cert)

    return cert, pkey_pem

def rotate_certificate(path_secrets: pathlib.Path, cert: str, key: bytes):
    path_key_new = pathlib.Path(path_secrets, 'pki.web.key.new')
    path_key = pathlib.Path(path_secrets, 'pki.web.key')
    path_key_old = pathlib.Path(path_secrets, 'pki.web.key.old')
    path_cert_new = pathlib.Path(path_secrets, 'pki.web.cert.new')
    path_cert = pathlib.Path(path_secrets, 'pki.web.cert')
    path_cert_old = pathlib.Path(path_secrets, 'pki.web.cert.old')

    with open(path_key_new, 'wb') as fp:
        fp.write(key)
    with open(path_cert_new, 'wt') as fp:
        fp.write(cert)

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


async def main():
    LOGGER.info("Starting")
    config = ConfigurationInstance.load()
    try:
        context = InstanceContext(config)
        context.reload()
    except ConfigurationFileError as e:
        LOGGER.error("Error loading configuration files %s, quitting" % str(e))
        sys.exit(1)  # Quit

    handler = CertbotHandler(context)
    await handler.setup()
    clecert = await handler.issue_certificate()
    LOGGER.info("New certificate expiry: %s" % clecert.enveloppe.not_valid_after)
    LOGGER.info("Done")


if __name__ == '__main__':
    logging.basicConfig()
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    asyncio.run(main())
