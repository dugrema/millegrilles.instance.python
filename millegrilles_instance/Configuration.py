import asyncio
import argparse
import logging
import os
import pathlib

from typing import Optional
from urllib.parse import urlparse

from millegrilles_instance import Constantes as ContantesInstance
from millegrilles_messages.bus.BusConfiguration import MilleGrillesBusConfiguration

LOGGING_NAMES = [__name__, 'millegrilles_messages', 'millegrilles_instance']


def load_dotenv(file: os.PathLike):
    with open(file) as f:
        config = {
            k.strip(): v.strip().strip('"')
            for line in f
            if line.strip() and not line.startswith("#")
            for k, v in [line.strip().split("=", 1)]
        }
    return config


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
        '--config', type=str, required=False,
        help="Path to configuration file (config.env)"
    )

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


class ConfigurationInstance(MilleGrillesBusConfiguration):

    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)

        # Load the configuration file
        if args.config:
            self.__millegrille_env = load_dotenv(pathlib.Path(args.config, 'config.env'))
        else:
            try:
                self.__millegrille_env = load_dotenv(pathlib.Path(os.environ["MILLEGRILLES_CONFIG"]))
            except KeyError:
                raise ValueError("Either command line parameter '--config /path/to/config.env' or environment parameter 'MILLEGRILLES_ROOT=/path/to/millegrille' must be provided")

        self.__path_millegrilles = pathlib.Path(self.__millegrille_env['MILLEGRILLES_ROOT'])

        # Set up folders from root
        self.__path_etc = self.__path_millegrilles.joinpath('etc')
        self.__path_secrets = self.__path_etc.joinpath('secrets')
        self.__path_nginx = self.__path_millegrilles.joinpath('nginx')
        self.__host_docker_internal = 'docker'
        # self.__certissuer_url = 'http://localhost:2080'
        self.__path_catalogues: Optional[str] = None  # = '/var/opt/millegrilles/configuration/catalogues'
        # self.__path_docker_apps: Optional[str] = None  # = '/var/opt/millegrilles/configuration/docker'
        self.__path_docker_compose = self.__path_millegrilles.joinpath('compose')
        self.__instance_password_mq_path: Optional[str] = None  # = '/var/opt/millegrilles/secrets/passwd.mqadmin.txt'

        # self.path_app_installation = self.__path_millegrilles.joinpath('dist/installation')
        # self.ca_pem_path = 'secrets/pki.millegrille.cert'
        self.web_cert_pem_path = self.__path_millegrilles / 'secrets/web.cert'
        self.web_key_pem_path = self.__path_millegrilles / 'secrets/web.key'
        # self.port = 2443

        # Apply instance defaults - usual defaults are meant for usage in docker containers
        self.default_override()
        self.__apply_config_env()

    def reload_config_env(self):
        self.__millegrille_env = load_dotenv(self.__path_millegrilles.joinpath('config.env'))
        self.__apply_config_env()

    def __apply_config_env(self):
        # Push configuration values to superclass
        try:
            mq_url = urlparse(self.__millegrille_env['MQ_URL'])
        except KeyError:
            mq_url = urlparse('amqps://localhost:5673')

        self.mq_hostname = mq_url.hostname
        self.mq_port = mq_url.port

    def save_config_env(self):
        raise NotImplementedError('TODO')

    def default_override(self):
        self.key_path = self.__path_millegrilles / 'secrets/manager.pem'
        self.ca_path = self.__path_millegrilles / 'etc/millegrille.pem'
        self.mq_hostname = 'localhost'
        self.redis_hostname = 'localhost'
        self.redis_password_path = str(self.__path_secrets.joinpath('passwd.redis.txt'))

    def parse_config(self):
        """
        Conserver l'information de configuration
        :return:
        """
        super().parse_config()

        self.__path_nginx = os.environ.get(ContantesInstance.INSTANCE_NGINX_PATH) or self.__path_millegrilles / 'etc/nginx'
        self.__host_docker_internal = os.environ.get(ContantesInstance.PARAM_INSTANCE_HOST_DOCKER_INTERNAL) or self.__host_docker_internal
        # self.__certissuer_url = os.environ.get(ContantesInstance.PARAM_INSTANCE_CERTISSUER_URL) or self.__certissuer_url
        self.__instance_password_mq_path = os.environ.get(ContantesInstance.PARAM_INSTANCE_PASSWD_MQ_PATH) or str(pathlib.Path(self.__path_secrets, 'passwd.mqadmin.txt'))

        self.__path_catalogues = str(pathlib.Path(self.__path_etc, 'catalogues'))
        # self.__path_docker_apps = str(pathlib.Path(self.__path_configuration, 'docker'))
        self.__path_docker_compose = str(pathlib.Path(self.__path_etc, 'compose'))

        # self.path_app_installation = os.environ.get(ContantesInstance.WEB_APP_PATH) or str(pathlib.Path(self.__path_millegrilles, 'dist/installation'))
        # self.ca_pem_path = os.environ.get(ContantesInstance.ENV_CA_PEM) or self.ca_pem_path
        self.web_cert_pem_path = os.environ.get(ContantesInstance.ENV_WEB_CERT_PEM) or str(pathlib.Path(self.__path_secrets, 'pki.web.cert'))
        self.web_key_pem_path = os.environ.get(ContantesInstance.ENV_WEB_KEY_PEM) or str(pathlib.Path(self.__path_secrets, 'pki.web.key'))

    def parse_args(self, args: argparse.Namespace):
        pass

    @staticmethod
    def load():
        # Override
        args = _parse_command_line()
        config = ConfigurationInstance(args)
        config.parse_config()
        config.parse_args(args)
        config.reload()
        return config

    def reload(self):
        """
        Reload values from config files
        """
        self.reload_config_env()
        # try:
        #     with open(self.__config_json, 'rt') as fp:
        #         config = json.load(fp)
        # except FileNotFoundError:
        #     self.__logger.debug("config.json not found")
        #     return
        #
        # self.mq_hostname = os.environ.get(ENV_MQ_HOSTNAME) or config.get('mq_host') or self.mq_hostname
        # try:
        #     mq_port = int(os.environ.get(ENV_MQ_PORT) or config.get('mq_port'))
        #     self.mq_port = mq_port or self.mq_port
        # except (TypeError, ValueError):
        #     pass

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

    @property
    def path_nginx(self) -> pathlib.Path:
        return pathlib.Path(self.__path_nginx)

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
        return self.__millegrille_env['CERTISSUER_URL']

    @property
    def instance_id(self) -> str:
        return self.__millegrille_env['INSTANCE_ID']

    @property
    def idmg(self) -> Optional[str]:
        return self.__millegrille_env.get('IDMG')

    @property
    def securite(self) -> Optional[str]:
        return self.__millegrille_env.get('SECURITE')

    @property
    def port(self) -> int:
        manager_url = urlparse(self.__millegrille_env['MANAGER_URL'])
        return manager_url.port or 2443

    @property
    def instance_name(self):
        return self.__millegrille_env['INSTANCE_NAME']