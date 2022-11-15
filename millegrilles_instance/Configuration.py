import argparse
import os

from typing import Optional

from millegrilles_instance import Constantes
from millegrilles_messages.messages import Constantes as ConstantesMessages

CONST_INSTANCE_PARAMS = [
    Constantes.INSTANCE_CONFIG_PATH,
    Constantes.INSTANCE_NGINX_PATH,
    Constantes.INSTANCE_SECRETS_PATH,
    Constantes.INSTANCE_SECRETS_PARTAGES_PATH,
    Constantes.PARAM_INSTANCE_CA_PATH,
    Constantes.PARAM_INSTANCE_CERT_PATH,
    Constantes.PARAM_INSTANCE_KEY_PATH,
    Constantes.PARAM_INSTANCE_IDMG_PATH,
    Constantes.PARAM_INSTANCE_CERTISSUER_URL,
    Constantes.PARAM_INSTANCE_ID_PATH,
    Constantes.PARAM_INSTANCE_SECURITE_PATH,
    Constantes.PARAM_INSTANCE_PASSWD_MQ_PATH,
    Constantes.PARAM_INSTANCE_MQ_HOST,
    Constantes.PARAM_INSTANCE_MQ_PORT,
]

CONST_WEB_PARAMS = [
    Constantes.ENV_WEB_PORT,
    Constantes.WEB_APP_PATH,
    Constantes.ENV_WEB_CERT_PEM,
    Constantes.ENV_WEB_KEY_PEM,
]


class ConfigurationInstance:

    def __init__(self):
        self.path_configuration = '/var/opt/millegrilles/configuration'
        self.path_secrets = '/var/opt/millegrilles/secrets'
        self.path_secrets_partages = '/var/opt/millegrilles/secrets_partages'
        self.path_nginx = '/var/opt/millegrilles/nginx'
        self.path_certissuer = '/var/opt/millegrilles/certissuer'
        self.certissuer_url = 'http://localhost:2080'
        self.instance_cert_pem_path = '/var/opt/millegrilles/secrets/pki.instance.cert'
        self.instance_key_pem_path = '/var/opt/millegrilles/secrets/pki.instance.key'
        self.instance_id_path = '/var/opt/millegrilles/configuration/instance_id.txt'
        self.instance_idmg_path = '/var/opt/millegrilles/configuration/idmg.txt'
        self.instance_ca_pem_path = '/var/opt/millegrilles/configuration/pki.millegrille.cert'
        self.instance_securite_path = '/var/opt/millegrilles/configuration/securite.txt'
        self.path_catalogues = '/var/opt/millegrilles/configuration/catalogues'
        self.path_docker_apps = '/var/opt/millegrilles/configuration/docker'
        self.instance_password_mq_path = '/var/opt/millegrilles/secrets/passwd.mqadmin.txt'
        self.redis_key_path = '/var/opt/millegrilles/secrets/passwd.redis.txt'
        self.config_json = '/var/opt/millegrilles/configuration/config.json'

        self.docker_actif = False

        self.path_certificat_web: Optional[str] = None
        self.path_cle_web: Optional[str] = None

        self.docker_image_backup = 'docker.maceroc.com/millegrilles_messages_python:2022.8.3'

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

    def parse_config(self, args: argparse.Namespace, configuration: Optional[dict] = None):
        """
        Conserver l'information de configuration
        :param args:
        :param configuration:
        :return:
        """
        dict_params = self.get_env()
        if configuration is not None:
            dict_params.update(configuration)

        self.path_configuration = dict_params.get(Constantes.INSTANCE_CONFIG_PATH) or self.path_configuration
        self.path_secrets = dict_params.get(Constantes.INSTANCE_SECRETS_PATH) or self.path_secrets
        self.path_secrets_partages = dict_params.get(Constantes.INSTANCE_SECRETS_PARTAGES_PATH) or self.path_secrets_partages
        self.path_nginx = dict_params.get(Constantes.INSTANCE_NGINX_PATH) or self.path_nginx
        self.certissuer_url = dict_params.get(Constantes.PARAM_INSTANCE_CERTISSUER_URL) or self.certissuer_url
        self.instance_ca_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_CA_PATH) or self.instance_ca_pem_path
        self.instance_cert_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_CERT_PATH) or self.instance_cert_pem_path
        self.instance_key_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_KEY_PATH) or self.instance_key_pem_path
        self.instance_id_path = dict_params.get(Constantes.PARAM_INSTANCE_ID_PATH) or self.instance_id_path
        self.instance_idmg_path = dict_params.get(Constantes.PARAM_INSTANCE_IDMG_PATH) or self.instance_idmg_path
        self.instance_securite_path = dict_params.get(Constantes.PARAM_INSTANCE_SECURITE_PATH) or self.instance_securite_path
        self.instance_password_mq_path = dict_params.get(Constantes.PARAM_INSTANCE_PASSWD_MQ_PATH) or self.instance_password_mq_path


class ConfigurationWeb:

    def __init__(self):
        self.path_app_installation = '/var/opt/millegrilles/dist/installation'
        self.ca_pem_path = '/var/opt/millegrilles/secrets/pki.millegrille.cert'
        self.web_cert_pem_path = '/var/opt/millegrilles/secrets/pki.web.cert'
        self.web_key_pem_path = '/var/opt/millegrilles/secrets/pki.web.cle'
        self.port = 2443

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
        self.ca_pem_path = dict_params.get(ConstantesMessages.ENV_CA_PEM) or self.ca_pem_path
        self.web_cert_pem_path = dict_params.get(Constantes.ENV_WEB_CERT_PEM) or self.web_cert_pem_path
        self.web_key_pem_path = dict_params.get(Constantes.ENV_WEB_KEY_PEM) or self.web_key_pem_path
        self.port = int(dict_params.get(Constantes.ENV_WEB_PORT) or self.port)
