import asyncio
import logging

from asyncio import Event as EventAsyncio, TimeoutError
from os import environ

from millegrilles_messages.docker_obsolete.DockerHandler import DockerState, DockerHandler
from millegrilles_instance.AcmeHandler import CommandeAcmeIssue, CommandeAcmeExtractCertificates

logger = logging.getLogger("__main__")
logger.setLevel(logging.DEBUG)

docker_state = DockerState()
docker_handler = DockerHandler(docker_state)
docker_handler.start()

DOMAINE = 'mg-dev5.maple.maceroc.com'


async def test_issue_testcert_webroot():
    params = {
        'modeTest': True,
    }
    commande = CommandeAcmeIssue(DOMAINE, params)
    docker_handler.ajouter_commande(commande)
    resultat = await commande.get_resultat()

    exit_code = resultat['code']
    str_resultat = resultat['resultat']
    logger.info("Resultat issue webroot (%d)\n%s", (exit_code, str_resultat))


async def test_issue_testcert_cloudns():
    cloudns_subid = environ['CLOUDNS_SUB_AUTH_ID']
    cloudns_password = environ['CLOUDNS_AUTH_PASSWORD']
    logger.info("Generer certificat avec cloudns sub_id %s" % cloudns_subid)

    params = {
        'modeTest': True,
        'modeCreation': 'dns_cloudns',
        'cloudns_subauthid': cloudns_subid,
        'cloudns_password': cloudns_password,
    }

    commande = CommandeAcmeIssue(DOMAINE, params)
    docker_handler.ajouter_commande(commande)
    resultat = await commande.get_resultat()

    exit_code = resultat['code']
    str_resultat = resultat['resultat']
    logger.info("Resultat issue webroot (%d)\n%s" % (exit_code, str_resultat))


async def test_get_certificats():
    commande = CommandeAcmeExtractCertificates("mg-dev5.maple.maceroc.com")
    docker_handler.ajouter_commande(commande)
    resultat = await commande.get_resultat()

    exit_code = resultat['code']
    str_resultat = resultat['resultat']
    key_pem = resultat['key']
    cert_pem = resultat['cert']
    logger.info("Resultat get certificat (%d)\n%s" % (exit_code, str_resultat))
    logger.info("Key PEM\n%s\n\nCert PEM\n%s" % (key_pem, cert_pem))


async def run_tests():
    logger.debug("run_tests debut")
    try:
        await test_issue_testcert_cloudns()
    except KeyError:
        logger.info("Generer certificat avec webroot")
        await test_issue_testcert_webroot()
    await test_get_certificats()
    logger.debug("run_tests fin")


def main():
    logging.basicConfig()
    logging.getLogger('millegrilles_messages').setLevel(logging.DEBUG)
    logging.getLogger('millegrilles_instance').setLevel(logging.DEBUG)

    logger.debug("Running main")

    asyncio.run(run_tests())


if __name__ == '__main__':
    main()
