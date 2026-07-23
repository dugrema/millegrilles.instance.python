import asyncio
import argparse
import logging
import os
import pathlib

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
        '--verbose', action="store_true", required=False,
        help="More logging"
    )

    parser.add_argument(
        '--logtime', action="store_true", required=False,
        help="Add time to logging"
    )

    parser.add_argument(
        '--config', type=str, required=False,
        help="Path to configuration file (config.env)"
    )

    parser.add_argument(
        '--init', action="store_true", required=False,
        help="Run setup only then exit. Used to initialize certificates, nginx config, etc."
    )

    args = parser.parse_args()
    __adjust_logging(args)
    return args


class ConfigurationInstance(MilleGrillesBusConfiguration):

    def __init__(self, args: argparse.Namespace):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)
        self.verbose = args.verbose

        # Load the configuration file
        if args.config:
            self.__millegrille_env = load_dotenv(pathlib.Path(args.config, 'config.env'))
        else:
            try:
                self.__millegrille_env = load_dotenv(pathlib.Path(os.environ["MILLEGRILLES_CONFIG"]))
            except KeyError:
                raise ValueError("Either command line parameter '--config /path/to/config.env' or environment parameter 'MILLEGRILLES_ROOT=/path/to/millegrille' must be provided")

        self.__path_millegrilles = pathlib.Path(self.__millegrille_env['MILLEGRILLES_ROOT'])
        self.__init_only = False  # When True, means that the system should run initial setup only (i.e. certs, nginx config, setup directories) then exit
        self.__instance_id = self.__millegrille_env['INSTANCE_ID']
        self.__instance_name = self.__millegrille_env['INSTANCE_NAME']

        # Set up folders from root
        self.__host_docker_internal = 'docker'
        self.__certissuer_url = 'http://localhost:2080'
        self.__instance_password_mq_path = self.__path_millegrilles / 'secrets/mqadmin.txt'

        # self.web_cert_pem_path = self.__path_millegrilles / 'secrets/web.cert'
        # self.web_key_pem_path = self.__path_millegrilles / 'secrets/web.key'

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
        self.cert_path = self.__path_millegrilles / 'secrets/manager.pem'
        self.key_path = self.__path_millegrilles / 'secrets/manager.pem'
        self.mq_hostname = 'localhost'
        self.redis_hostname = 'localhost'
        self.redis_password_path = self.__path_millegrilles / 'secrets/redis.txt'

    def parse_config(self):
        """
        Conserver l'information de configuration
        :return:
        """
        super().parse_config()

        self.__host_docker_internal = os.environ.get(ContantesInstance.PARAM_INSTANCE_HOST_DOCKER_INTERNAL) or self.__host_docker_internal
        self.__certissuer_url = os.environ.get(ContantesInstance.PARAM_INSTANCE_CERTISSUER_URL) or self.__certissuer_url
        self.__instance_password_mq_path = pathlib.Path(os.environ.get(ContantesInstance.PARAM_INSTANCE_PASSWD_MQ_PATH) or self.__instance_password_mq_path)
        # self.web_cert_pem_path = pathlib.Path(os.environ.get(ContantesInstance.ENV_WEB_CERT_PEM) or self.web_cert_pem_path)
        # self.web_key_pem_path = pathlib.Path(os.environ.get(ContantesInstance.ENV_WEB_KEY_PEM) or self.web_key_pem_path)


    def parse_args(self, args: argparse.Namespace):
        self.__init_only = args.init

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

    @property
    def path_millegrilles(self) -> pathlib.Path:
        return pathlib.Path(self.__path_millegrilles)

    @property
    def host_docker_internal(self) -> str:
        return self.__host_docker_internal

    @property
    def certissuer_url(self) -> str:
        return self.__certissuer_url

    @property
    def port(self) -> int:
        manager_url = urlparse(self.__millegrille_env['MANAGER_URL'])
        return manager_url.port or 2443

    @property
    def init_only(self) -> bool:
        return self.__init_only

    @property
    def instance_id(self) -> str:
        return self.__instance_id

    @property
    def instance_name(self) -> str:
        return self.__instance_name

    @property
    def instance_ports(self) -> dict[str, int]:
        http = int(self.__millegrille_env.get('HTTP_PORT') or 80)
        https = int(self.__millegrille_env.get('HTTPS_PORT') or 443)
        mtls = int(self.__millegrille_env.get('MTLS_PORT') or 444)
        return {
            "http": http,
            "https": https,
            "wss": https,
            "https_mtls": mtls,
            "wss_mtls": mtls,
        }
