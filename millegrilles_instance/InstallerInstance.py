import aiohttp
import json
import logging

from os import path
from typing import Optional

from aiohttp import web
from aiohttp.web_request import BaseRequest

from millegrilles_messages.messages import Constantes
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat

logger = logging.getLogger(__name__)


async def installer_instance(etat_instance: EtatInstance, request: BaseRequest, headers_response: Optional[dict] = None):
    contenu = await request.json()
    logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))

    securite = etat_instance.niveau_securite
    if securite is None:
        securite = contenu['securite']
    elif securite != contenu['securite']:
        logger.error("installer_instance() Mauvais niveau de securite (locked a %s): %s" % (securite, contenu['securite']))
        return web.HTTPForbidden()

    # Preparer configuration pour sauvegarde - agit comme validation du request recu
    enveloppe_ca = etat_instance.certificat_millegrille
    idmg = etat_instance.idmg
    if enveloppe_ca is None:
        certificat_ca = contenu['certificatMillegrille']
        enveloppe_ca = EnveloppeCertificat.from_pem(certificat_ca)
    else:
        certificat_ca = None  # Ne pas changer de certificat CA

    if idmg is None:
        idmg = enveloppe_ca.idmg
    elif idmg != enveloppe_ca.idmg:
        raise Exception("Mismatch idmg local et recu")

    if securite == Constantes.SECURITE_SECURE:
        await installer_secure(etat_instance, contenu, certificat_ca, idmg)
        return web.Response(status=201, headers=headers_response)
    elif securite == Constantes.SECURITE_PROTEGE:
        await installer_protege(etat_instance, contenu, certificat_ca, idmg)
        return web.Response(status=201, headers=headers_response)
    elif securite in [Constantes.SECURITE_PUBLIC, Constantes.SECURITE_PRIVE]:
        await installer_satellite(etat_instance, contenu, securite, certificat_ca, idmg)
        return web.Response(status=200, headers=headers_response)
    else:
        logger.error("installer_instance Mauvais type instance (%s)" % securite)
        return web.HTTPBadRequest()


async def installer_secure(etat_instance: EtatInstance, contenu: dict, certificat_ca: str, idmg: str):
    # Injecter un CSR pour generer un certificat d'instance local
    clecsr = CleCsrGenere.build(etat_instance.instance_id)
    csr_str = clecsr.get_pem_csr()
    contenu['csr'] = csr_str

    reponse = await installer_certificat_intermediaire(etat_instance.certissuer_url, contenu)
    certificat_instance = reponse['certificat']

    # Installer le certificat d'instance
    configuration = etat_instance.configuration
    path_idmg = configuration.instance_idmg_path
    path_ca = configuration.instance_ca_pem_path
    path_securite = configuration.instance_securite_path
    path_cert = configuration.instance_cert_pem_path
    path_key = configuration.instance_key_pem_path
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


async def installer_protege(etat_instance: EtatInstance, contenu: dict, certificat_ca: str, idmg: str):
    # Injecter un CSR pour generer un certificat d'instance local
    clecsr = CleCsrGenere.build(etat_instance.instance_id)
    csr_str = clecsr.get_pem_csr()
    contenu['csr'] = csr_str

    reponse = await installer_certificat_intermediaire(etat_instance.certissuer_url, contenu)
    certificat_instance = reponse['certificat']

    # Installer le certificat d'instance
    configuration = etat_instance.configuration
    path_idmg = configuration.instance_idmg_path
    path_ca = configuration.instance_ca_pem_path
    path_securite = configuration.instance_securite_path
    path_cert = configuration.instance_cert_pem_path
    path_key = configuration.instance_key_pem_path
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

    # Declencher le recharger de la configuration de l'instance
    # Va aussi installer les nouveaux elements de configuration/secrets dans docker
    # await etat_instance.reload_configuration()
    #raise ConstantesInstance("installation completee")


async def installer_satellite(etat_instance: EtatInstance, contenu: dict, securite: str, certificat_ca: str, idmg: str):
    certificat_instance = contenu['certificat']
    clecsr = etat_instance.get_csr_genere()

    # Verifier que le certificat et la cle correspondent
    cert_pem = ''.join(certificat_instance)
    cle_pem = clecsr.get_pem_cle()
    clecert = CleCertificat.from_pems(cle_pem, cert_pem)
    if not clecert.cle_correspondent():
        raise ValueError('Cle et Certificat ne correspondent pas')

    # Installer le certificat d'instance
    configuration = etat_instance.configuration
    path_idmg = configuration.instance_idmg_path
    path_ca = configuration.instance_ca_pem_path
    path_securite = configuration.instance_securite_path
    path_cert = configuration.instance_cert_pem_path
    path_key = configuration.instance_key_pem_path
    path_config_json = configuration.config_json
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

    try:
        with open(path_config_json, 'r') as fichier:
            contenu_config = json.load(fichier)
    except FileNotFoundError:
        contenu_config = dict()

    contenu_config.update({
        'hostname': contenu['hostname'],
        'mq_host': contenu['host'],
        'mq_port': contenu['port'],
        'securite': contenu['securite']
    })
    with open(path_config_json, 'w') as fichier:
        json.dump(contenu_config, fichier)

    # Declencher le recharger de la configuration de l'instance
    # Va aussi installer les nouveaux elements de configuration/secrets dans docker
    await etat_instance.reload_configuration()


async def configurer_idmg(etat_instance: EtatInstance, contenu: dict):
    # Preparer configuration pour sauvegarde - agit comme validation du request recu
    try:
        securite = contenu['securite']
        idmg = contenu['idmg']
    except KeyError:
        logger.error("configurer_idmg Parametres securite/idmg manquants")
        return web.HTTPBadRequest()

    if etat_instance.idmg is not None:
        logger.error("Tentative de configurer idmg %s sur instance deja barree" % idmg)
        return web.HTTPForbidden()

    if etat_instance.niveau_securite is not None:
        logger.error("Tentative de configurer securite %s sur instance deja barree" % securite)
        return web.HTTPForbidden()

    # Installer le certificat d'instance
    configuration = etat_instance.configuration
    path_idmg = configuration.instance_idmg_path
    path_securite = configuration.instance_securite_path
    with open(path_idmg, 'w') as fichier:
        fichier.write(idmg)
    with open(path_securite, 'w') as fichier:
        fichier.write(securite)

    # Declencher le recharger de la configuration de l'instance
    # Va aussi installer les nouveaux elements de configuration/secrets dans docker
    await etat_instance.reload_configuration()

    return web.Response(status=200)


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

    path_installer_certissuer = path.join(url_certissuer, 'installer')
    async with aiohttp.ClientSession() as session:
        async with session.post(path_installer_certissuer, json=req) as resp:
            resp.raise_for_status()
            return await resp.json()


