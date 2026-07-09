import asyncio
import argparse
import logging
import os
import pathlib
import json

from typing import Optional

from millegrilles_instance import Constantes as ContantesInstance
from millegrilles_messages.bus.BusConfiguration import MilleGrillesBusConfiguration, ENV_MQ_HOSTNAME, ENV_MQ_PORT

LOGGING_NAMES = [__name__, 'millegrilles_messages', 'millegrilles_instance']


def __adjust_logging(args: argparse.Namespace):
    logging_format = '%(levelname)s:%(name)s:%(message)s'

    if args.logtime:
        logging_format = f'%(asctime)s - {logging_format}'

    logging.basicConfig(format=logging_format)

    if args.verbose is True:
        asyncio.get_event_loop().set_debug(True)  # Asyncio warnings
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
    parser.add_argument(
        '--logtime', action="store_true", required=False,
        help="Add time to logging"
    )

    args = parser.parse_args()
    __adjust_logging(args)
    return args

CONST_PATH_ROOT = os.environ["MILLEGRILLES_ROOT"]  # '/var/opt/millegrilles'
if CONST_PATH_ROOT is None:
    raise ValueError("Missing MILLEGRILLES_ROOT environment parameter")


class ConfigurationInstance(MilleGrillesBusConfiguration):

    def __init__(self):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)

        self.__path_millegrilles = str(CONST_PATH_ROOT)
        self.__path_etc = str(pathlib.Path(self.__path_millegrilles, 'etc'))
        self.__path_secrets = str(pathlib.Path(self.__path_etc, 'secrets'))
        # self.__path_secrets_partages: Optional[str] = None
        self.__path_nginx: str = str(pathlib.Path(self.__path_millegrilles, 'nginx'))
        self.__path_certissuer: Optional[str] = None
        self.__host_docker_internal = 'docker'
        self.__certissuer_url = 'http://localhost:2080'
        self.__instance_id_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/instance_id.txt'
        self.__instance_idmg_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/idmg.txt'
        self.__instance_securite_path: Optional[str] = None  # = '/var/opt/millegrilles/configuration/securite.txt'
        self.__path_catalogues: Optional[str] = None  # = '/var/opt/millegrilles/configuration/catalogues'
        # self.__path_docker_apps: Optional[str] = None  # = '/var/opt/millegrilles/configuration/docker'
        self.__path_docker_compose = None
        self.__instance_password_mq_path: Optional[str] = None  # = '/var/opt/millegrilles/secrets/passwd.mqadmin.txt'
        self.__config_json: Optional[str] = None  # = '/var/opt/millegrilles/configuration/config.json'

        # self.docker_image_backup = 'docker.maple.maceroc.com:5000/millegrilles_midcompte_python:2023.6.0'

        self.path_app_installation = self.__path_millegrilles.join(['dist', 'installation'])
        # self.ca_pem_path = '/var/opt/millegrilles/secrets/pki.millegrille.cert'
        self.web_cert_pem_path = self.__path_millegrilles.join(['secrets', 'pki.web.cert'])  # '/var/opt/millegrilles/secrets/pki.web.cert'
        self.web_key_pem_path = self.__path_millegrilles.join(['secrets', 'pki.web.key'])  # '/var/opt/millegrilles/secrets/pki.web.key'
        self.port = 2443

        # Apply instance defaults - usual defaults are meant for usage in docker containers
        self.default_override()

    def default_override(self):
        self.cert_path = str(pathlib.Path(self.__path_secrets, 'pki.instance.cert'))
        self.key_path = str(pathlib.Path(self.__path_secrets, 'pki.instance.key'))
        self.ca_path = str(pathlib.Path(self.__path_etc, 'pki.millegrille.cert'))
        self.mq_hostname = 'localhost'
        self.redis_hostname = 'localhost'
        self.redis_password_path = str(pathlib.Path(self.__path_secrets, 'passwd.redis.txt'))

    def parse_config(self):
        """
        Conserver l'information de configuration
        :return:
        """
        super().parse_config()

        # self.__path_millegrilles = os.environ.get(ContantesInstance.MILLEGRILLES_PATH_ENV) or self.__path_millegrilles
        # self.__path_etc = str(pathlib.Path(os.environ.get(ContantesInstance.REPO_ROOT_PATH) or self.__path_millegrilles, 'etc'))
        # self.__path_configuration = os.environ.get(ContantesInstance.INSTANCE_CONFIG_PATH) or str(pathlib.Path(self.__path_millegrilles, 'configuration'))
        # self.__path_secrets = os.environ.get(ContantesInstance.INSTANCE_SECRETS_PATH) or str(pathlib.Path(self.__path_millegrilles, 'secrets'))
        # self.__path_secrets_partages = os.environ.get(ContantesInstance.INSTANCE_SECRETS_PARTAGES_PATH) or str(pathlib.Path(self.__path_millegrilles, 'secrets_partages'))
        self.__path_nginx = os.environ.get(ContantesInstance.INSTANCE_NGINX_PATH) or str(pathlib.Path(self.__path_millegrilles, 'nginx'))
        self.__host_docker_internal = os.environ.get(ContantesInstance.PARAM_INSTANCE_HOST_DOCKER_INTERNAL) or self.__host_docker_internal
        self.__certissuer_url = os.environ.get(ContantesInstance.PARAM_INSTANCE_CERTISSUER_URL) or self.__certissuer_url
        self.__instance_id_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_ID_PATH) or str(pathlib.Path(self.__path_etc, 'instance_id.txt'))
        self.__instance_idmg_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_IDMG_PATH) or str(pathlib.Path(self.__path_etc, 'idmg.txt'))
        self.__instance_securite_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_SECURITE_PATH) or str(pathlib.Path(self.__path_etc, 'securite.txt'))
        self.__instance_password_mq_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_PASSWD_MQ_PATH) or str(pathlib.Path(self.__path_secrets, 'passwd.mqadmin.txt'))

        self.__path_catalogues = str(pathlib.Path(self.__path_etc, 'catalogues'))
        # self.__path_docker_apps = str(pathlib.Path(self.__path_configuration, 'docker'))
        self.__path_docker_compose = str(pathlib.Path(self.__path_etc, 'compose'))
        self.__config_json = str(pathlib.Path(self.__path_etc, 'config.json'))

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
        config.reload()
        return config

    def reload(self):
        """
        Reload values from config.json
        """
        try:
            with open(self.__config_json, 'rt') as fp:
                config = json.load(fp)
        except FileNotFoundError:
            self.__logger.debug("config.json not found")
            return

        self.mq_hostname = os.environ.get(ENV_MQ_HOSTNAME) or config.get('mq_host') or self.mq_hostname
        try:
            mq_port = int(os.environ.get(ENV_MQ_PORT) or config.get('mq_port'))
            self.mq_port = mq_port or self.mq_port
        except (TypeError, ValueError):
            pass

    @property
    def path_etc(self) -> pathlib.Path:
        return pathlib.Path(self.__path_etc)

    @property
    def path_millegrilles(self) -> pathlib.Path:
        return pathlib.Path(self.__path_millegrilles)

    @property
    def path_configuration(self) -> pathlib.Path:
        return pathlib.Path(self.__path_etc)

    @property
    def path_secrets(self) -> pathlib.Path:
        return pathlib.Path(self.__path_secrets)

    # @property
    # def path_secrets_partages(self) -> pathlib.Path:
    #     return pathlib.Path(self.__path_secrets_partages)

    @property
    def path_nginx(self) -> pathlib.Path:
        return pathlib.Path(self.__path_nginx)

    # @property
    # def path_idmg(self) -> pathlib.Path:
    #     return pathlib.Path(self.__instance_idmg_path)

    # @property
    # def path_securite(self) -> pathlib.Path:
    #     return pathlib.Path(self.__instance_securite_path)

    @property
    def path_config_json(self) -> pathlib.Path:
        if not self.__config_json:
            raise Exception("Not defined")
        return pathlib.Path(self.__config_json)

    @property
    def path_catalogues(self) -> pathlib.Path:
        if not self.__path_catalogues:
            raise Exception("Not defined")
        return pathlib.Path(self.__path_catalogues)

    @property
    def path_docker_compose(self) -> pathlib.Path:
        if not self.__path_docker_compose:
            raise Exception("Not defined")
        return pathlib.Path(self.__path_docker_compose)

    @property
    def host_docker_internal(self) -> str:
        return self.__host_docker_internal

    @property
    def certissuer_url(self) -> str:
        return self.__certissuer_url

    def get_instance_id(self) -> str:
        return os.environ.get(ContantesInstance.PARAM_INSTANCE_ID, "")

    def get_idmg(self) -> str:
        with open(self.__instance_idmg_path, 'rt') as fp:
            return fp.read().strip()

    def get_securite(self) -> str:
        with open(self.__instance_securite_path, 'rt') as fp:
            return fp.read().strip()
