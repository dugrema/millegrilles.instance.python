import aiohttp
import json
import logging

from os import path

from aiohttp import web
from aiohttp.web_request import BaseRequest

from millegrilles.certificats.Generes import CleCsrGenere
from millegrilles.instance.EtatInstance import EtatInstance

logger = logging.getLogger(__name__)


async def installer_instance(etat_instance: EtatInstance, request: BaseRequest):
    contenu = await request.json()
    logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))

    # Injecter un CSR pour generer un certificat d'instance local
    clecsr = CleCsrGenere.build(etat_instance.instance_id)
    csr_str = clecsr.get_pem_csr()
    contenu['csr_instance'] = csr_str

    reponse = await installer_certificat_intermediaire(etat_instance.certissuer_url, contenu)
    certificat_instance = reponse['certificat']

    # Installer le certificat d'instance
    raise NotImplemented('todo')

    return web.Response(status=200)


async def installer_certificat_intermediaire(url_certissuer: str, contenu: dict) -> dict:
    securite = contenu['securite']
    certificat_ca = contenu['certificatMillegrille']
    certificat_intermediaire = contenu['certificatIntermediaire']

    req = {
        'ca': certificat_ca,
        'intermediaire': certificat_intermediaire,
        'csr_instance': contenu['csr_instance'],
        'securite': securite,
    }

    path_installer_certissuer = path.join(url_certissuer, 'installer')
    async with aiohttp.ClientSession() as session:
        async with session.post(path_installer_certissuer, json=req) as resp:
            resp.raise_for_status()
            return await resp.json()


