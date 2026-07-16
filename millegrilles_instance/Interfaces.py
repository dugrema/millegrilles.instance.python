from typing import Optional

# from millegrilles_instance.millegrilles_docker.DockerHandler import CommandeDocker
from millegrilles_messages.messages.CleCertificat import CleCertificat


# class DockerHandlerInterface:
#
#     def __init__(self):
#         pass
#
#     async def redemarrer_nginx(self):
#         raise NotImplementedError('must implement')
#
#     async def assurer_clecertificat(self, nom_module: str, clecertificat: CleCertificat, combiner=False):
#         raise NotImplementedError('must implement')
#
#     async def run_command(self, command: CommandeDocker):
#         raise NotImplementedError('must implement')
#
#     async def ajouter_password(self, nom_module: str, date: str, value: str):
#         raise NotImplementedError('must implement')


class MgbusHandlerInterface:

    def __init__(self):
        pass

    async def register(self):
        raise NotImplementedError('must implement')

    async def unregister(self):
        raise NotImplementedError('must implement')

