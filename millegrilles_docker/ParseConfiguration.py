# Parsing de la configuration d'un service/container
import logging
import urllib.parse
from typing import Optional, Any
from urllib.parse import urlparse

from docker.types import NetworkAttachmentConfig, Resources, RestartPolicy, ServiceMode, EndpointSpec, Mount, \
    SecretReference, ConfigReference


class WebApplicationConfiguration:

    def __init__(self, element: dict):
        self.location = element['location']
        self.digest = element['digest']
        self.src = element['src']

    @property
    def module(self):
        return self.location.split(':')[0]

    @property
    def path(self):
        return self.location.split(':')[1]

    @property
    def app_url(self) -> urllib.parse.ParseResult:
        return urlparse(self.src)

    @property
    def filename(self):
        return self.app_url.path.split('/')[-1]


class ConfigurationService:
    """
    Converti format config MilleGrilles en format du module docker
    """

    def __init__(self, configuration: dict, params: Optional[dict] = None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__params = params
        self.__parsed: Optional[dict] = None

        self.__name: Optional[str] = None
        self.__hostname: Optional[str] = None
        self.__args: Optional[list] = None
        self.__image: Optional[str] = None
        self.__environment: Optional[list] = None
        self.__mounts: Optional[list] = None
        self.__constraints: Optional[list] = None
        self.__config: Optional[list] = None
        self.__secrets: Optional[list] = None
        self.__endpoint_spec: Optional[EndpointSpec] = None
        self.__networks: Optional[list] = None
        self.__labels: Optional[list] = None
        self.__resources: Optional[Resources] = None
        self.__mode: Optional[ServiceMode] = None
        self.__restart_policy: Optional[RestartPolicy] = None
        self.__archives: Optional[list[WebApplicationConfiguration]] = None

    @property
    def archives(self) -> Optional[list[WebApplicationConfiguration]]:
        return self.__archives

    def parse(self):
        self.__name = self.__configuration['name']

        try:
            self.__image = self.__configuration['image']
        except KeyError:
            self.__logger.warning("Configuration %s sans image - entretien generateurs uniquement" % self.__name)

        try:
            self.__hostname = self.__configuration['hostname']
        except KeyError:
            pass

        try:
            self.__args = self.__configuration['args']
        except KeyError:
            pass

        try:
            self.__constraints = self.__configuration['constraints']
        except KeyError:
            pass

        self._parse_resources()
        self._parse_restart_policy()
        self._parse_service_mode()
        self._parse_mounts()
        self._parse_env()
        self._parse_configs()
        self._parse_secrets()
        self._parse_labels()
        self._parse_container_labels()
        self._parse_networks()
        self._parse_endpoint_specs()
        self._parse_archives()

    def _mapping_valeur(self, value: Any):

        if not isinstance(value, str):
            return value

        if self.__params:
            for param_key, param_value in self.__params.items():
                if isinstance(param_value, str):
                    value = value.replace('${%s}' % param_key, param_value)
                elif isinstance(param_value, int):
                    value = value.replace('${%s}' % param_key, str(param_value))
        return value

    def _parse_resources(self):
        try:
            resources = self.__configuration['resources']
            self.__resources = Resources(**resources)
        except KeyError:
            pass

    def _parse_restart_policy(self):
        try:
            policy = self.__configuration['restart_policy']
            self.__restart_policy = RestartPolicy(**policy)
        except KeyError:
            pass

    def _parse_service_mode(self):
        try:
            config = self.__configuration['mode']
            self.__mode = ServiceMode(**config)
        except KeyError:
            pass

    def _parse_mounts(self):
        try:
            mounts = self.__configuration['mounts']
        except KeyError:
            return

        mounts_list = list()
        for mount in mounts:
            target = self._mapping_valeur(mount['target'])
            source = self._mapping_valeur(mount['source'])
            volume_type = mount['type']
            read_only = mount.get('read_only') or False
            mount_obj = Mount(target, source, volume_type, read_only)
            mounts_list.append(mount_obj)

        self.__mounts = mounts_list

    def _parse_env(self):
        try:
            env_config = self.__configuration['env'].copy()

            for key, value in env_config.items():
                env_config[key] = self._mapping_valeur(env_config[key])

        except KeyError:
            env_config = dict()

        if self.__params is not None:
            try:
                env_config["INSTANCE_ID"] = self.__params['__instance_id']
            except KeyError:
                pass
            try:
                env_config["IDMG"] = self.__params['__idmg']
            except KeyError:
                pass

        config_env_list = ['='.join(i) for i in env_config.items()]
        self.__environment = config_env_list

    def _parse_configs(self):
        try:
            docker_configs = self.__configuration['configs']
        except KeyError:
            return

        liste_configs = list()
        for elem_config in docker_configs:
            type_current = elem_config.get('current')
            config_name = elem_config['name']
            if type_current is not None:
                try:
                    config_current = self.__params['__docker_config_datee'][config_name]['current']
                except KeyError as ke:
                    raise CertificatAbsent(str(ke))
                id_c = config_current[type_current]['id']
                config_name = config_current[type_current]['name']
            else:
                config_name = elem_config['name']
                configs = self.__params['__configs']
                id_c = configs[config_name]

            config_reference = {
                'config_id': id_c,
                'config_name': config_name,
                'filename': elem_config['filename'],
                'uid': elem_config.get('uid') or 0,
                'gid': elem_config.get('gid') or 0,
                'mode': elem_config.get('mode') or 0o444,
            }

            liste_configs.append(ConfigReference(**config_reference))

        self.__config = liste_configs

    def _parse_secrets(self):
        try:
            docker_secrets = self.__configuration['secrets']
        except KeyError:
            return

        liste_secrets = list()
        for elem_secret in docker_secrets:
            # if elem_secret.get('key') is True:
            #     secret_name = self.__params['__certificat_info']['label_prefix']
            #     config_current = self.__params['__docker_config_datee'][secret_name]['current']
            #     id_c = config_current['key']['id']
            #     secret_name = config_current['key']['name']
            # elif elem_secret.get('password') is True:
            #     secret_name = self.__params['__password_info']['label_prefix']
            #     config_current = self.__params['__docker_config_datee'][secret_name]['current']
            #     id_c = config_current['password']['id']
            #     secret_name = config_current['password']['name']
            # else:
            type_current = elem_secret.get('current')
            secret_name = elem_secret['name']
            if type_current is not None:
                config_datee = self.__params['__docker_config_datee']
                current_secret = config_datee[secret_name]['current'][type_current]
                id_c = current_secret['id']
                secret_name = current_secret['name']
            else:
                secrets = self.__params['__secrets']
                id_c = secrets[secret_name]

            secret_reference = {
                'secret_id': id_c,
                'secret_name': secret_name,
                'filename': elem_secret['filename'],
                'uid': elem_secret.get('uid') or 0,
                'gid': elem_secret.get('gid') or 0,
                'mode': elem_secret.get('mode') or 0o444,
            }

            liste_secrets.append(SecretReference(**secret_reference))

        self.__secrets = liste_secrets

    def _parse_labels(self):
        try:
            labels_src = self.__configuration['labels']
        except KeyError:
            labels_src = dict()

        # Map labels
        labels = dict()
        for key, value in labels_src.items():
            value = self._mapping_valeur(value)
            labels[key] = value

        if self.__params is not None:
            try:
                certificat_info = self.__params['__certificat_info']
                labels['certificat'] = 'true'
                labels['certificat_label_prefix'] = certificat_info['label_prefix']
            except KeyError:
                pass

            try:
                nom_application = self.__params['__nom_application']
                labels['application'] = nom_application

                # Nom human readable
                if labels.get('nom_application') is None:
                    labels['nom_application'] = nom_application
            except KeyError:
                pass

            try:
                labels['package_name'] = self.__params['__package_name']
            except KeyError:
                pass

        self.__labels = labels

    def _parse_container_labels(self):
        try:
            labels_src = self.__configuration['container_labels']
        except KeyError:
            labels_src = dict()

        # Map labels
        labels = dict()
        for key, value in labels_src.items():
            value = self._mapping_valeur(value)
            labels[key] = value

        self.__container_labels = labels

    def _parse_networks(self):
        try:
            config_networks = self.__configuration['networks']
        except KeyError:
            return

        networks = list()
        for network in config_networks:
            network['target'] = self._mapping_valeur(network['target'])
            networks.append(NetworkAttachmentConfig(**network))

        self.__networks = networks

    def _parse_endpoint_specs(self):
        # Ports
        try:
            config_endpoint_spec = self.__configuration['endpoint_spec']
        except KeyError:
            return

        ports = dict()
        mode = config_endpoint_spec.get('mode') or 'vip'
        for port in config_endpoint_spec.get('ports'):
            published_port = port['published_port']
            target_port = port['target_port']
            protocol = port.get('protocol') or 'tcp'
            publish_mode = port.get('publish_mode') or 'ingress'

            if protocol or publish_mode:
                ports[published_port] = (target_port, protocol, publish_mode)
            else:
                ports[published_port] = target_port

        self.__endpoint_spec = EndpointSpec(mode=mode, ports=ports)

    def _parse_archives(self) -> Optional[list[WebApplicationConfiguration]]:
        try:
            archives_elements: list = self.__configuration['archives']
        except KeyError:
            return

        self.__archives = [WebApplicationConfiguration(a) for a in archives_elements]

    def generer_docker_config(self) -> dict:
        config = {
            'name': self.__name,
            'image': self.__image,
        }

        if self.__hostname is not None:
            config['hostname'] = self.__hostname

        if self.__args is not None:
            config['args'] = self.__args

        if self.__environment is not None:
            config['env'] = self.__environment

        if self.__restart_policy is not None:
            config['restart_policy'] = self.__restart_policy

        if self.__mode is not None:
            config['mode'] = self.__mode

        if self.__labels is not None:
            config['labels'] = self.__labels

        if self.__container_labels is not None:
            config['container_labels'] = self.__container_labels

        if self.__networks is not None:
            config['networks'] = self.__networks

        if self.__mounts is not None:
            config['mounts'] = self.__mounts

        if self.__constraints is not None:
            config['constraints'] = self.__constraints

        if self.__config is not None:
            config['configs'] = self.__config

        if self.__secrets is not None:
            config['secrets'] = self.__secrets

        if self.__endpoint_spec is not None:
            config['endpoint_spec'] = self.__endpoint_spec

        if self.__resources is not None:
            config['resources'] = self.__resources

        return config

    @property
    def constraints(self):
        return self.__constraints

    @property
    def image(self):
        return self.__image


class ConfigurationContainer:

    def __init__(self):
        pass


class CertificatAbsent(Exception):
    pass

