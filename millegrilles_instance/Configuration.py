import argparse
import json
import logging
import os
import pathlib

from typing import Optional

from millegrilles_instance import Constantes as ContantesInstance
from millegrilles_messages.bus.BusConfiguration import MilleGrillesBusConfiguration

LOGGING_NAMES = [__name__, 'millegrilles_messages', 'millegrilles_instance']


def __adjust_logging(args: argparse.Namespace):
    logging.basicConfig()
    if args.verbose is True:
        for log in LOGGING_NAMES:
            logging.getLogger(log).setLevel(logging.DEBUG)
    else:
        for log in LOGGING_NAMES:
            logging.getLogger(log).setLevel(logging.INFO)


def _parse_command_line():
    parser = argparse.ArgumentParser(description="Instance manager for MilleGrilles")
    parser.add_argument(
        '--verbose', action="store_true", required=False,
        help="More logging"
    )

    args = parser.parse_args()
    __adjust_logging(args)
    return args

CONST_PATH_MILLEGRILLES = '/var/opt/millegrilles'


class ConfigurationInstance(MilleGrillesBusConfiguration):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)

        self.__path_millegrilles = str(CONST_PATH_MILLEGRILLES)
        self.__path_configuration = str(pathlib.Path(self.__path_millegrilles, 'configuration'))
        self.__path_secrets = str(pathlib.Path(self.__path_millegrilles, 'secrets'))
        self.__path_secrets_partages: Optional[str] = None
        self.__path_nginx: Optional[str] = None
        self.__path_certissuer: Optional[str] = None
        self.__certissuer_url = 'http://localhost:2080'
        self.__instance_id_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/instance_id.txt'
        self.__instance_idmg_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/idmg.txt'
        self.__instance_securite_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/securite.txt'
        self.__path_catalogues: Optional[str] = None  # = '/var/opt/millegrilles/configuration/catalogues'
        self.__path_docker_apps: Optional[str] = None  # = '/var/opt/millegrilles/configuration/docker'
        self.__instance_password_mq_path: Optional[str] = None  # = '/var/opt/millegrilles/secrets/passwd.mqadmin.txt'
        self.__config_json: Optional[str] = None  # = '/var/opt/millegrilles/configuration/config.json'

        # self.docker_image_backup = 'docker.maple.maceroc.com:5000/millegrilles_midcompte_python:2023.6.0'

        self.path_app_installation = '/var/opt/millegrilles/dist/installation'
        # self.ca_pem_path = '/var/opt/millegrilles/secrets/pki.millegrille.cert'
        self.web_cert_pem_path = '/var/opt/millegrilles/secrets/pki.web.cert'
        self.web_key_pem_path = '/var/opt/millegrilles/secrets/pki.web.key'
        self.port = 2443

        # Apply instance defaults - usual defaults are meant for usage in docker containers
        self.default_override()

    def default_override(self):
        self.cert_path = str(pathlib.Path(self.__path_secrets, 'pki.instance.cert'))
        self.key_path = str(pathlib.Path(self.__path_secrets, 'pki.instance.key'))
        self.ca_path = str(pathlib.Path(self.__path_configuration, 'pki.millegrille.cert'))
        self.mq_hostname = 'localhost'
        self.redis_hostname = 'localhost'
        self.redis_password_path = str(pathlib.Path(self.__path_secrets, 'passwd.redis.txt'))

    def parse_config(self):
        """
        Conserver l'information de configuration
        :return:
        """
        super().parse_config()

        self.__path_configuration = os.environ.get(ContantesInstance.INSTANCE_CONFIG_PATH) or self.__path_configuration
        self.__path_secrets = os.environ.get(ContantesInstance.INSTANCE_SECRETS_PATH) or self.__path_secrets
        self.__path_secrets_partages = os.environ.get(ContantesInstance.INSTANCE_SECRETS_PARTAGES_PATH) or str(pathlib.Path(self.__path_millegrilles, 'secrets_partages'))
        self.__path_nginx = os.environ.get(ContantesInstance.INSTANCE_NGINX_PATH) or str(pathlib.Path(self.__path_millegrilles, 'nginx'))
        self.__certissuer_url = os.environ.get(ContantesInstance.PARAM_INSTANCE_CERTISSUER_URL) or self.__certissuer_url
        self.__instance_id_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_ID_PATH) or str(pathlib.Path(self.__path_configuration, 'instance_id.txt'))
        self.__instance_idmg_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_IDMG_PATH) or str(pathlib.Path(self.__path_configuration, 'idmg.txt'))
        self.__instance_securite_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_SECURITE_PATH) or str(pathlib.Path(self.__path_configuration, 'securite.txt'))
        self.__instance_password_mq_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_PASSWD_MQ_PATH) or str(pathlib.Path(self.__path_secrets, 'passwd.mqadmin.txt'))

        self.__path_catalogues = str(pathlib.Path(self.__path_configuration, 'catalogues'))
        self.__path_docker_apps = str(pathlib.Path(self.__path_configuration, 'docker'))
        self.__config_json = str(pathlib.Path(self.__path_configuration, 'config.json'))

        # self.path_app_installation = os.environ.get(ContantesInstance.WEB_APP_PATH) or str(pathlib.Path(self.__path_millegrilles, 'dist/installation'))
        # self.ca_pem_path = os.environ.get(ContantesInstance.ENV_CA_PEM) or self.ca_pem_path
        self.web_cert_pem_path = os.environ.get(ContantesInstance.ENV_WEB_CERT_PEM) or str(pathlib.Path(self.__path_secrets, 'pki.web.cert'))
        self.web_key_pem_path = os.environ.get(ContantesInstance.ENV_WEB_KEY_PEM) or str(pathlib.Path(self.__path_secrets, 'pki.web.key'))
        self.port = int(os.environ.get(ContantesInstance.ENV_WEB_PORT) or self.port)

    def parse_args(self, args: argparse.Namespace):
        pass

    @staticmethod
    def load():
        # Override
        config = ConfigurationInstance()
        args = _parse_command_line()
        config.parse_config()
        config.parse_args(args)
        return config

    @property
    def path_millegrilles(self) -> pathlib.Path:
        return pathlib.Path(CONST_PATH_MILLEGRILLES)

    @property
    def path_configuration(self) -> pathlib.Path:
        return pathlib.Path(self.__path_configuration)

    @property
    def path_secrets(self) -> pathlib.Path:
        return pathlib.Path(self.__path_secrets)

    @property
    def path_secrets_partages(self) -> pathlib.Path:
        return pathlib.Path(self.__path_secrets_partages)

    @property
    def path_nginx(self) -> pathlib.Path:
        return pathlib.Path(self.__path_nginx)

    @property
    def path_idmg(self) -> pathlib.Path:
        return pathlib.Path(self.__instance_idmg_path)

    @property
    def path_securite(self) -> pathlib.Path:
        return pathlib.Path(self.__instance_securite_path)

    @property
    def path_config_json(self) -> pathlib.Path:
        return pathlib.Path(self.__config_json)

    @property
    def path_catalogues(self) -> pathlib.Path:
        return pathlib.Path(self.__path_catalogues)

    @property
    def certissuer_url(self) -> str:
        return self.__certissuer_url

    def get_instance_id(self) -> str:
        with open(self.__instance_id_path, 'rt') as fp:
            return fp.read().strip()

    def get_idmg(self) -> str:
        with open(self.__instance_idmg_path, 'rt') as fp:
            return fp.read().strip()

    def get_securite(self) -> str:
        with open(self.__instance_securite_path, 'rt') as fp:
            return fp.read().strip()


# import argparse
# import logging
# import os
# import json
# import pathlib
#
# from typing import Optional
#
# from millegrilles_instance import Constantes
# from millegrilles_messages.messages import Constantes as ConstantesMessages
#
# LOGGER = logging.getLogger(__name__)
#
# CONST_INSTANCE_PARAMS = [
#     Constantes.INSTANCE_CONFIG_PATH,
#     Constantes.INSTANCE_NGINX_PATH,
#     Constantes.INSTANCE_SECRETS_PATH,
#     Constantes.INSTANCE_SECRETS_PARTAGES_PATH,
#     Constantes.PARAM_INSTANCE_CA_PATH,
#     Constantes.PARAM_INSTANCE_CERT_PATH,
#     Constantes.PARAM_INSTANCE_KEY_PATH,
#     Constantes.PARAM_INSTANCE_IDMG_PATH,
#     Constantes.PARAM_INSTANCE_CERTISSUER_URL,
#     Constantes.PARAM_INSTANCE_ID_PATH,
#     Constantes.PARAM_INSTANCE_SECURITE_PATH,
#     Constantes.PARAM_INSTANCE_PASSWD_MQ_PATH,
#     Constantes.PARAM_INSTANCE_MQ_HOST,
#     Constantes.PARAM_INSTANCE_MQ_PORT,
# ]
#
# CONST_WEB_PARAMS = [
#     Constantes.ENV_WEB_PORT,
#     Constantes.WEB_APP_PATH,
#     Constantes.ENV_WEB_CERT_PEM,
#     Constantes.ENV_WEB_KEY_PEM,
# ]
#
#
# class ConfigurationInstance:
#
#     def __init__(self):
#         self.path_configuration = '/var/opt/millegrilles/configuration'
#         self.path_secrets = '/var/opt/millegrilles/secrets'
#         self.path_secrets_partages = '/var/opt/millegrilles/secrets_partages'
#         self.path_nginx = '/var/opt/millegrilles/nginx'
#         self.path_certissuer = '/var/opt/millegrilles/certissuer'
#         self.certissuer_url = 'http://localhost:2080'
#         self.instance_cert_pem_path = '/var/opt/millegrilles/secrets/pki.instance.cert'
#         self.instance_key_pem_path = '/var/opt/millegrilles/secrets/pki.instance.key'
#         self.instance_id_path = '/var/opt/millegrilles/configuration/instance_id.txt'
#         self.instance_idmg_path = '/var/opt/millegrilles/configuration/idmg.txt'
#         self.instance_ca_pem_path = '/var/opt/millegrilles/configuration/pki.millegrille.cert'
#         self.instance_securite_path = '/var/opt/millegrilles/configuration/securite.txt'
#         self.path_catalogues = '/var/opt/millegrilles/configuration/catalogues'
#         self.path_docker_apps = '/var/opt/millegrilles/configuration/docker'
#         self.instance_password_mq_path = '/var/opt/millegrilles/secrets/passwd.mqadmin.txt'
#         self.redis_key_path = '/var/opt/millegrilles/secrets/passwd.redis.txt'
#         self.config_json = '/var/opt/millegrilles/configuration/config.json'
#
#         self.docker_actif = False
#
#         self.path_certificat_web: Optional[str] = None
#         self.path_cle_web: Optional[str] = None
#
#         # self.docker_image_backup = 'docker.maple.maceroc.com:5000/millegrilles_midcompte_python:2023.6.0'
#
#     def get_env(self) -> dict:
#         """
#         Extrait l'information pertinente pour pika de os.environ
#         :return: Configuration dict
#         """
#         config = dict()
#         for opt_param in CONST_INSTANCE_PARAMS:
#             value = os.environ.get(opt_param)
#             if value is not None:
#                 config[opt_param] = value
#
#         return config
#
#     def parse_config(self, args: argparse.Namespace, configuration: Optional[dict] = None):
#         """
#         Conserver l'information de configuration
#         :param args:
#         :param configuration:
#         :return:
#         """
#         dict_params = self.get_env()
#         if configuration is not None:
#             dict_params.update(configuration)
#
#         self.path_configuration = dict_params.get(Constantes.INSTANCE_CONFIG_PATH) or self.path_configuration
#         self.path_secrets = dict_params.get(Constantes.INSTANCE_SECRETS_PATH) or self.path_secrets
#         self.path_secrets_partages = dict_params.get(Constantes.INSTANCE_SECRETS_PARTAGES_PATH) or self.path_secrets_partages
#         self.path_nginx = dict_params.get(Constantes.INSTANCE_NGINX_PATH) or self.path_nginx
#         self.certissuer_url = dict_params.get(Constantes.PARAM_INSTANCE_CERTISSUER_URL) or self.certissuer_url
#         self.instance_ca_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_CA_PATH) or self.instance_ca_pem_path
#         self.instance_cert_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_CERT_PATH) or self.instance_cert_pem_path
#         self.instance_key_pem_path = dict_params.get(Constantes.PARAM_INSTANCE_KEY_PATH) or self.instance_key_pem_path
#         self.instance_id_path = dict_params.get(Constantes.PARAM_INSTANCE_ID_PATH) or self.instance_id_path
#         self.instance_idmg_path = dict_params.get(Constantes.PARAM_INSTANCE_IDMG_PATH) or self.instance_idmg_path
#         self.instance_securite_path = dict_params.get(Constantes.PARAM_INSTANCE_SECURITE_PATH) or self.instance_securite_path
#         self.instance_password_mq_path = dict_params.get(Constantes.PARAM_INSTANCE_PASSWD_MQ_PATH) or self.instance_password_mq_path
#
#
# class ConfigurationWeb:
#
#     def __init__(self):
#         self.path_app_installation = '/var/opt/millegrilles/dist/installation'
#         self.ca_pem_path = '/var/opt/millegrilles/secrets/pki.millegrille.cert'
#         self.web_cert_pem_path = '/var/opt/millegrilles/secrets/pki.web.cert'
#         self.web_key_pem_path = '/var/opt/millegrilles/secrets/pki.web.cle'
#         self.port = 2443
#
#     def get_env(self) -> dict:
#         """
#         Extrait l'information pertinente pour pika de os.environ
#         :return: Configuration dict
#         """
#         config = dict()
#         for opt_param in CONST_WEB_PARAMS:
#             value = os.environ.get(opt_param)
#             if value is not None:
#                 config[opt_param] = value
#
#         return config
#
#     def parse_config(self, configuration: Optional[dict] = None):
#         """
#         Conserver l'information de configuration
#         :param configuration:
#         :return:
#         """
#         dict_params = self.get_env()
#         if configuration is not None:
#             dict_params.update(configuration)
#
#         self.path_app_installation = dict_params.get(Constantes.WEB_APP_PATH) or self.path_app_installation
#         self.ca_pem_path = dict_params.get(ConstantesMessages.ENV_CA_PEM) or self.ca_pem_path
#         self.web_cert_pem_path = dict_params.get(Constantes.ENV_WEB_CERT_PEM) or self.web_cert_pem_path
#         self.web_key_pem_path = dict_params.get(Constantes.ENV_WEB_KEY_PEM) or self.web_key_pem_path
#         self.port = int(dict_params.get(Constantes.ENV_WEB_PORT) or self.port)
#
#
# def sauvegarder_configuration_webapps(nom_application: str, web_links: dict, etat_instance):
#     LOGGER.debug("Sauvegarder configuration pour web app %s" % nom_application)
#
#     path_conf_applications = pathlib.Path(
#         etat_instance.configuration.path_configuration,
#         Constantes.CONFIG_NOMFICHIER_CONFIGURATION_WEB_APPLICATIONS)
#
#     hostname = etat_instance.hostname
#     try:
#         links = web_links['links']
#     except (TypeError, KeyError):
#         LOGGER.debug("sauvegarder_configuration_webapps Aucun web links pour %s" % nom_application)
#     else:
#         for link in links:
#             try:
#                 link['url'] = link['url'].replace('${HOSTNAME}', hostname)
#             except KeyError:
#                 pass  # No url
#         try:
#             with open(path_conf_applications, 'rt+') as fichier:
#                 config_apps_json = json.load(fichier)
#                 config_apps_json[nom_application] = web_links
#                 fichier.seek(0)
#                 json.dump(config_apps_json, fichier)
#                 fichier.truncate()
#         except (FileNotFoundError, json.JSONDecodeError):
#             config_apps_json = dict()
#             config_apps_json[nom_application] = web_links
#             with open(path_conf_applications, 'wt') as fichier:
#                 json.dump(config_apps_json, fichier)
