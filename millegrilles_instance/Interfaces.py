class DockerHandlerInterface:

    def __init__(self):
        pass

    async def redemarrer_nginx(self):
        raise NotImplementedError('must implement')


class MgbusHandlerInterface:

    def __init__(self):
        pass

    async def register(self):
        raise NotImplementedError('must implement')

    async def unregister(self):
        raise NotImplementedError('must implement')
