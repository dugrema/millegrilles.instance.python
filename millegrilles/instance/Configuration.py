import os

from typing import Optional

from millegrilles.instance import Constantes

CONST_INSTANCE_PARAMS = [
    Constantes.INSTANCE_CONFIG_PATH,
    Constantes.INSTANCE_NGINX_PATH,
    Constantes.INSTANCE_SECRETS_PATH,
    Constantes.INSTANCE_SECRETS_PARTAGES_PATH,
]

CONST_WEB_PARAMS = [
    Constantes.WEB_APP_PATH,
]


class ConfigurationInstance:

    def __init__(self):
        self.path_configuration = '/var/opt/millegrilles/configuration'
        self.path_secrets = '/var/opt/millegrilles/secrets'
        self.path_secrets_partages = '/var/opt/millegrilles/secrets_partages'
        self.path_nginx_configuration = '/var/opt/millegrilles/nginx/modules'

        self.docker_actif = False

    def get_env(self) -> dict:
        """
        Extrait l'information pertinente pour pika de os.environ
        :return: Configuration dict
        """
        config = dict()
        for opt_param in CONST_INSTANCE_PARAMS:
            value = os.environ.get(opt_param)
            if value is not None:
                config[opt_param] = value

        return config

    def parse_config(self, configuration: Optional[dict] = None):
        """
        Conserver l'information de configuration
        :param configuration:
        :return:
        """
        dict_params = self.get_env()
        if configuration is not None:
            dict_params.update(configuration)

        self.path_configuration = dict_params.get(Constantes.INSTANCE_CONFIG_PATH) or self.path_configuration
        self.path_secrets = dict_params.get(Constantes.INSTANCE_SECRETS_PATH) or self.path_secrets
        self.path_secrets_partages = dict_params.get(Constantes.INSTANCE_SECRETS_PARTAGES_PATH) or self.path_secrets_partages
        self.path_nginx_configuration = dict_params.get(Constantes.INSTANCE_NGINX_PATH) or self.path_nginx_configuration


class ConfigurationWeb:

    def __init__(self):
        self.path_app_installation = '/var/opt/millegrilles/dist/installation'

    def get_env(self) -> dict:
        """
        Extrait l'information pertinente pour pika de os.environ
        :return: Configuration dict
        """
        config = dict()
        for opt_param in CONST_WEB_PARAMS:
            value = os.environ.get(opt_param)
            if value is not None:
                config[opt_param] = value

        return config

    def parse_config(self, configuration: Optional[dict] = None):
        """
        Conserver l'information de configuration
        :param configuration:
        :return:
        """
        dict_params = self.get_env()
        if configuration is not None:
            dict_params.update(configuration)

        self.path_app_installation = dict_params.get(Constantes.WEB_APP_PATH) or self.path_app_installation
