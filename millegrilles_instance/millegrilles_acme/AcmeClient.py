import asyncio
import json
import pathlib
import logging

import josepy as jose

from acme import challenges
from acme import client
from acme import crypto_util
from acme import errors
from acme import messages
from acme import standalone

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# This is the staging point for ACME-V2 within Let's Encrypt.
DIRECTORY_URL = 'https://acme-staging-v02.api.letsencrypt.org/directory'
USER_AGENT = 'python-acme'

PATH_WELLKNOWN = '/var/opt/millegrilles/nginx/html'

# Account key size
ACC_KEY_BITS = 2048

# Certificate private key size
CERT_PKEY_BITS = 2048

# Domain name for the certificate.
DOMAIN = 'chalet2.pivoine.maceroc.com'

LOGGER = logging.getLogger(__name__)


async def new_csr_comp(domain_name: str, pkey_pem=None):
    """Create certificate signing request."""
    if pkey_pem is None:
        # Create private key.
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        # public_key = private_key.public_key()
        pkey_pem = private_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                             serialization.NoEncryption())

        # serializing into PEM
        # rsa_pem = public_key.public_bytes(encoding=serialization.Encoding.PEM,
        #                                   format=serialization.PublicFormat.SubjectPublicKeyInfo)
        # pkey = await asyncio.to_thread(rsa.generate_private_key, public_exponent=65537, key_size=CERT_PKEY_BITS)
        # pkey_pem = pkey.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
        #                               serialization.NoEncryption())

    csr_pem = crypto_util.make_csr(pkey_pem, [domain_name])
    return pkey_pem, csr_pem


async def get_account_key() -> jose.JWKRSA:
    try:
        with open('/tmp/key.json', 'rt') as fp:
            key_str = fp.read()
        return jose.JWKRSA.json_loads(key_str)
    except FileNotFoundError:
        rsa_key = await asyncio.to_thread(rsa.generate_private_key, public_exponent=65537, key_size=ACC_KEY_BITS, backend=default_backend())
        acc_key = jose.JWKRSA(key=rsa_key)
        with open('/tmp/key.json', 'wt') as fp:
            fp.write(acc_key.json_dumps())
            # json.dump(acc_key.to_json(), fp)
    return acc_key


async def create_client(acc_key: jose.JWKRSA) -> client.ClientV2:
    net = client.ClientNetwork(acc_key, user_agent=USER_AGENT)
    directory = client.ClientV2.get_directory(DIRECTORY_URL, net)
    client_acme = client.ClientV2(directory, net=net)
    return client_acme


async def get_account(client_acme: client.ClientV2) -> messages.RegistrationResource:
    # Terms of Service URL is in client_acme.directory.meta.terms_of_service
    # Registration Resource: regr
    # Creates account with contact information.
    try:
        with open('/tmp/regr.json', 'rt') as fp:
            regr = messages.RegistrationResource.from_json(json.load(fp))
            regr_state = await asyncio.to_thread(client_acme.query_registration, regr)
            return regr_state.body
    except FileNotFoundError:
        email = ('info.accounts1@mdugre.info')
        regr: messages.RegistrationResource = await asyncio.to_thread(
            client_acme.new_account,
            messages.NewRegistration.from_data(
            email=email, terms_of_service_agreed=True)
        )
        with open('/tmp/regr.json', 'wt') as fp:
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


def perform_http01(client_acme: client.ClientV2, challb: messages.ChallengeBody, orderr: messages.OrderResource):
    """Set up standalone webserver and perform HTTP-01 challenge."""

    response, validation = challb.response_and_validation(client_acme.net.key)
    challenge_received_path = pathlib.Path(challb.chall.path)
    challenge_received_path = challenge_received_path.parts[1:]
    challenge_local_path = pathlib.Path(PATH_WELLKNOWN, *challenge_received_path)
    with open(challenge_local_path, 'wt') as fp:
        fp.write(validation)
    
    # Let the CA server know that we are ready for the challenge.
    client_acme.answer_challenge(challb, response)

    # Wait for challenge status and then issue a certificate.
    # It is possible to set a deadline time.
    finalized_orderr = client_acme.poll_and_finalize(orderr)

    return finalized_orderr.fullchain_pem


async def issue_certificate(client_acme: client.ClientV2) -> (str, bytes):
    # Create domain private key and CSR
    pkey_pem, csr_pem = await new_csr_comp(DOMAIN)
    # Issue certificate
    orderr: messages.OrderResource = await asyncio.to_thread(client_acme.new_order, csr_pem)
    challb = select_http01_chall(orderr)

    cert = await asyncio.to_thread(perform_http01, client_acme, challb, orderr)
    LOGGER.info("Received new certificate\n%s" % cert)

    return cert, pkey_pem

def rotate_certificate(cert: str, key: bytes):
    path_secrets = pathlib.Path('/var/opt/millegrilles/secrets')

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
    acc_key = await get_account_key()
    client = await create_client(acc_key)
    regr = await get_account(client)
    cert, key = await issue_certificate(client)
    await asyncio.to_thread(rotate_certificate, cert, key)
    LOGGER.info("Done")


if __name__ == '__main__':
    asyncio.run(main())
