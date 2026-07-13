import asyncio
import logging
import pathlib
import yaml

from typing import Optional, Any

from attr import dataclass
from requests import certs

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_messages.messages import Constantes as MillegrillesConstantes

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.InstanceDocker import InstanceDockerHandler


def extract_certificate_list(configuration_file: dict):
    certificats_to_manage = []
    for key, value in configuration_file.items():
        try:
            services = value['services']
        except KeyError:
            continue

        for service_name, service_config in services.items():
            try:
                certificate_config = service_config['x-millegrilles-certificat'].copy()
                certificate_config['name'] = service_name
                certificats_to_manage.append(certificate_config)
            except KeyError:
                continue


def load_yaml_recursive(yaml_file: pathlib.Path) -> dict:
    with open(yaml_file) as f:
        compose_configuration: dict = yaml.safe_load(f)

    try:
        include_files = compose_configuration['include']
        files_dict = dict()
        compose_configuration['x-include-content'] = files_dict
        for include_file in include_files:
            include_file_path = yaml_file.parent.joinpath(include_file).resolve()
            file_content = load_yaml_recursive(include_file_path)
            files_dict[include_file_path] = file_content
    except KeyError:
        pass

    return compose_configuration


def load_compose_files(configuration: ConfigurationInstance) -> list[dict[str, Any]]:
    """
    :param configuration: Instance configuration
    :return: Path to the node type's docker-compose yml file for this instance
    """
    composefiles: list[dict[str, Any]] = list()

    securite = configuration.securite
    if securite == MillegrillesConstantes.SECURITE_PUBLIC:
        filename = 'node-public.yml'
    elif securite == MillegrillesConstantes.SECURITE_PRIVE:
        filename = 'node-prive.yml'
    elif securite == MillegrillesConstantes.SECURITE_PROTEGE:
        filename = 'node-protege.yml'
    elif securite == MillegrillesConstantes.SECURITE_SECURE:
        filename = 'node-secure.yml'
    else:
        raise ValueError("Unsupported security type")

    compose_file_nodetype = configuration.path_millegrilles / "etc/compose/nodetypes" / filename
    config_nodetype = load_yaml_recursive(compose_file_nodetype)
    composefiles.append(config_nodetype)

    applications_file = configuration.path_millegrilles / "etc/compose/applications.yml"
    if applications_file.exists():
        config_applications = load_yaml_recursive(compose_file_nodetype)
        composefiles.append(config_applications)

    return composefiles


@dataclass
class CertificateConfiguration:
    name: str
    roles: list[str]
    exchanges: Optional[list[str]]
    domaines: Optional[list[str]]
    dns: Optional[dict[str, str]]
    split: Optional[bool]
    key_path: Optional[pathlib.Path]
    cert_path: Optional[pathlib.Path]


def extract_certificate_configuration(config_file: dict) -> list[CertificateConfiguration]:
    certs = list()

    try:
        content_dict = config_file['x-include-content']
    except KeyError:
        pass  # No x-include-content
    else:
        for sub_name, sub_content in content_dict.items():
            new_certs = extract_certificate_configuration(sub_content)
            certs.extend(new_certs)

    try:
        services = config_file['services']
    except KeyError:
        pass
    else:
        for service_name, service_config in services.items():
            try:
                cert_config = service_config['x-millegrilles-certificat']
                cert_config['name'] = service_name
                certs.append(cert_config)
            except KeyError:
                pass

    return certs

class AppManager:

    def __init__(self, context: InstanceContext, docker_handler: InstanceDockerHandler):
        self.__logger = logging.getLogger(__name__)
        self.__context: InstanceContext = context
        self.__docker_handler = docker_handler

        self.__applications_changed = asyncio.Event()

    async def maintenance(self):
        await self.renew_certificates()

    async def renew_certificates(self):
        """
        Loads all base docker compose files and recursively goes through includes to cumulate the x-certificate-configuration elements.
        Each certificate under secrets/ that matches the configuration is checked and appropriate certificates are created/renewed.
        """

        certificates_to_check = []

        # Load the node compose file
        nodetype_file = composefile_path_by_nodetype(self.__context.configuration)

        # Load the deployed apps compose file

        # Load each certificate and check if it is missing/expired/about to expire.
        certificates_to_renew: list[CertificateConfiguration] = []

        if len(certificates_to_renew) == 0:
            return  # Nothing to do

        for certificate in certificates_to_renew:
            raise NotImplementedError("TODO")

        # The
        self.__applications_changed.set()
