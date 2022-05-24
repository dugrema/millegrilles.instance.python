import aiohttp
import json
import logging

from os import path

from aiohttp import web
from aiohttp.web_request import BaseRequest

from millegrilles.instance.EtatInstance import EtatInstance

logger = logging.getLogger(__name__)


async def installer_instance(etat_instance: EtatInstance, request: BaseRequest):
    contenu = await request.json()
    logger.debug("installer_instance contenu\n%s" % json.dumps(contenu, indent=2))

    await installer_certificat_intermediaire(etat_instance.certissuer_url, contenu)

    return web.Response(status=200)


async def installer_certificat_intermediaire(url_certissuer: str, contenu: dict):
    certificat_ca = contenu['certificatMillegrille']
    certificat_intermediaire = contenu['certificatIntermediaire']

    req = {
        'ca': certificat_ca,
        'intermediaire': certificat_intermediaire,
    }

    path_installer_certissuer = path.join(url_certissuer, 'installer')
    async with aiohttp.ClientSession() as session:
        async with session.post(path_installer_certissuer, json=req) as resp:
            resp.raise_for_status()


