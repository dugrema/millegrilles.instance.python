class RequiredModules:

    def __init__(self, modules: list[str]):
        self.modules = modules

    def __repr__(self):
        return str(self.modules)


CONFIG_MODULES_INSTALLATION = RequiredModules([
    'docker.nginxinstall.json',
    'docker.certissuer.json',
])

CONFIG_MODULES_SECURE_EXPIRE = RequiredModules([
    'docker.nginx.json',
    'docker.certissuer.json',
])

CONFIG_CERTIFICAT_EXPIRE = RequiredModules([
    'docker.nginx.json',
])

CONFIG_MODULES_SECURES = RequiredModules([
    'docker.nginx.json',
    'docker.certissuer.json',
    'docker.redis.json',
])

CONFIG_MODULES_PROTEGES = RequiredModules([
    'docker.nginx.json',
    'docker.certissuer.json',
    'docker.redis.json',
    'docker.mq.json',
    'docker.mongo.json',
    'docker.midcompte.json',
    'docker.ceduleur.json',
    'docker.core.json',
    'docker.webauth.json',
    'docker.protected_webapi.json',
])

CONFIG_MODULES_PRIVES = RequiredModules([
    'docker.nginx.json',
    'docker.redis.json',
    'docker.webauth.json',
])

CONFIG_MODULES_PUBLICS = RequiredModules([
    'docker.nginx.json',
    'docker.redis.json',
    'docker.webauth.json',
])
