import aiohttp
import json
import logging
import urllib.parse

from os import path
from typing import Optional

from aiohttp import web
from aiohttp.web_request import BaseRequest

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_messages.messages import Constantes
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat

logger = logging.getLogger(__name__)


async def installer_instance(context: InstanceContext, request: BaseRequest, headers_response: Optional[dict] = None):
    contenu = await request.json()
    logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))

    try:
        securite = context.securite
        if securite != contenu['securite']:
            logger.error(
                "installer_instance() Mauvais niveau de securite (locked a %s): %s" % (securite, contenu['securite']))
            return web.HTTPForbidden()
    except ValueNotAvailable:
        securite = contenu['securite']

    # Preparer configuration pour sauvegarde - agit comme validation du request recu
    enveloppe_ca = context.ca
    if enveloppe_ca is None:
        certificat_ca = contenu['certificatMillegrille']
        enveloppe_ca = EnveloppeCertificat.from_pem(certificat_ca)
    else:
        certificat_ca = None  # Ne pas changer de certificat CA

    try:
        idmg = context.idmg
        if idmg != enveloppe_ca.idmg:
            raise Exception("Mismatch idmg local et recu")
    except ValueNotAvailable:
        idmg = enveloppe_ca.idmg

    if securite == Constantes.SECURITE_SECURE:
        await installer_secure(context, contenu, certificat_ca, idmg)
        await context.delay_reload(3)
        return web.Response(status=201, headers=headers_response)
    elif securite == Constantes.SECURITE_PROTEGE:
        await installer_protege(context, contenu, certificat_ca, idmg)
        await context.delay_reload(3)
        return web.Response(status=201, headers=headers_response)
    elif securite in [Constantes.SECURITE_PUBLIC, Constantes.SECURITE_PRIVE]:
        await installer_satellite(context, contenu, securite, certificat_ca, idmg)
        await context.delay_reload(3)
        return web.Response(status=200, headers=headers_response)
    else:
        logger.error("installer_instance Mauvais type instance (%s)" % securite)
        return web.HTTPBadRequest()


async def installer_secure(context: InstanceContext, contenu: dict, certificat_ca: str, idmg: str):
    # Injecter un CSR pour generer un certificat d'instance local
    clecsr = CleCsrGenere.build(context.instance_id)
    csr_str = clecsr.get_pem_csr()
    contenu['csr'] = csr_str

    configuration: ConfigurationInstance = context.configuration
    reponse = await installer_certificat_intermediaire(configuration.certissuer_url, contenu)
    certificat_instance = reponse['certificat']

    # Installer le certificat d'instance
    configuration: ConfigurationInstance = context.configuration
    path_idmg = configuration.path_idmg
    path_securite = configuration.path_securite
    path_ca = configuration.ca_path
    path_cert = configuration.cert_path
    path_key = configuration.key_path
    with open(path_idmg, 'w') as fichier:
        fichier.write(idmg)
    if certificat_ca is not None:
        with open(path_ca, 'w') as fichier:
            fichier.write(certificat_ca)
    with open(path_securite, 'w') as fichier:
        fichier.write(Constantes.SECURITE_SECURE)
    with open(path_cert, 'w') as fichier:
        fichier.write(''.join(certificat_instance))
    with open(path_key, 'w') as fichier:
        fichier.write(clecsr.get_pem_cle())

    path_config_json = configuration.path_config_json
    contenu_config = {
        'instance_id': configuration.get_instance_id(),
        'hostname': context.hostname,
        'securite': Constantes.SECURITE_SECURE
    }
    with open(path_config_json, 'w') as fichier:
        json.dump(contenu_config, fichier)


async def installer_protege(context: InstanceContext, contenu: dict, certificat_ca: str, idmg: str):
    # Injecter un CSR pour generer un certificat d'instance local
    clecsr = CleCsrGenere.build(context.instance_id)
    csr_str = clecsr.get_pem_csr()
    contenu['csr'] = csr_str

    configuration = context.configuration
    reponse = await installer_certificat_intermediaire(configuration.certissuer_url, contenu)
    certificat_instance = reponse['certificat']

    # Installer le certificat d'instance
    path_idmg = configuration.path_idmg
    path_ca = configuration.ca_path
    path_securite = configuration.path_securite
    path_cert = configuration.cert_path
    path_key = configuration.key_path
    with open(path_idmg, 'w') as fichier:
        fichier.write(idmg)
    if certificat_ca is not None:
        with open(path_ca, 'w') as fichier:
            fichier.write(certificat_ca)
    with open(path_securite, 'w') as fichier:
        fichier.write(Constantes.SECURITE_PROTEGE)
    with open(path_cert, 'w') as fichier:
        fichier.write(''.join(certificat_instance))
    with open(path_key, 'w') as fichier:
        fichier.write(clecsr.get_pem_cle())

    path_config_json = configuration.path_config_json
    contenu_config = {
        'instance_id': configuration.get_instance_id(),
        'hostname': context.hostname,
        'mq_host': context.hostname,
        'mq_port': context.configuration.mq_port,
        'securite': Constantes.SECURITE_PROTEGE
    }
    with open(path_config_json, 'w') as fichier:
        json.dump(contenu_config, fichier)


async def installer_satellite(context: InstanceContext, contenu: dict, securite: str, certificat_ca: str, idmg: str):
    certificat_instance = contenu['certificat']
    clecsr = context.csr_genere

    # Verifier que le certificat et la cle correspondent
    cert_pem = ''.join(certificat_instance)
    cle_pem = clecsr.get_pem_cle()
    clecert = CleCertificat.from_pems(cle_pem, cert_pem)
    if not clecert.cle_correspondent():
        raise ValueError('Cle et Certificat ne correspondent pas')

    # Installer le certificat d'instance
    configuration = context.configuration
    path_idmg = configuration.path_idmg
    path_ca = configuration.ca_path
    path_securite = configuration.path_securite
    path_cert = configuration.cert_path
    path_key = configuration.key_path
    with open(path_idmg, 'w') as fichier:
        fichier.write(idmg)
    if certificat_ca is not None:
        with open(path_ca, 'w') as fichier:
            fichier.write(certificat_ca)
    with open(path_securite, 'w') as fichier:
        fichier.write(securite)
    with open(path_cert, 'w') as fichier:
        fichier.write(cert_pem)
    with open(path_key, 'w') as fichier:
        fichier.write(cle_pem)

    path_config_json = configuration.path_config_json
    contenu_config = {
        'instance_id': configuration.get_instance_id(),
        'hostname': contenu['hostname'],
        'mq_host': contenu['host'],
        'mq_port': contenu['port'],
        'securite': contenu['securite']
    }
    with open(path_config_json, 'w') as fichier:
        json.dump(contenu_config, fichier)

    # Recharger de la configuration de l'instance
    # Donner un delai pour terminer le traitement (e.g. reponse web)
    await context.delay_reload(1)


async def configurer_idmg(context: InstanceContext, contenu: dict):
    # Preparer configuration pour sauvegarde - agit comme validation du request recu
    try:
        securite = contenu['securite']
        idmg = contenu['idmg']
    except KeyError:
        logger.error("configurer_idmg Parametres securite/idmg manquants")
        return web.HTTPBadRequest()

    try:
        idmg = context.idmg
        logger.error("Tentative de configurer idmg %s sur instance deja barree" % idmg)
        return web.HTTPForbidden()
    except ValueNotAvailable:
        pass  # Ok

    try:
        securite = context.securite
        logger.error("Tentative de configurer securite %s sur instance deja barree" % securite)
        return web.HTTPForbidden()
    except ValueNotAvailable:
        pass  # Ok

    # Installer le certificat d'instance
    configuration = context.configuration
    path_idmg = configuration.path_idmg
    path_securite = configuration.path_securite
    with open(path_idmg, 'w') as fichier:
        fichier.write(idmg)
    with open(path_securite, 'w') as fichier:
        fichier.write(securite)

    # Declencher le recharger de la configuration de l'instance
    # Va aussi installer les nouveaux elements de configuration/secrets dans docker
    # await etat_instance.reload_configuration()
    await context.delay_reload(1)

    return web.json_response({'ok': True}, status=200)


async def installer_certificat_intermediaire(url_certissuer: str, contenu: dict) -> dict:
    securite = contenu['securite']
    certificat_ca = contenu['certificatMillegrille']
    certificat_intermediaire = contenu['certificatIntermediaire']

    req = {
        'ca': certificat_ca,
        'intermediaire': certificat_intermediaire,
        'csr': contenu['csr'],
        'securite': securite,
    }

    path_installer_certissuer = urllib.parse.urljoin(url_certissuer, 'installer')
    async with aiohttp.ClientSession() as session:
        async with session.post(path_installer_certissuer, json=req) as resp:
            resp.raise_for_status()
            return await resp.json()


