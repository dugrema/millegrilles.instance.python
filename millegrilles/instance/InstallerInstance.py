from aiohttp import web
from aiohttp.web_request import BaseRequest


async def installer_instance(request: BaseRequest):
    contenu = await request.json()
    return web.Response(status=200)


async def installer_certificat_intermediaire():
    pass

