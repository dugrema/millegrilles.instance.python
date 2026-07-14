import asyncio
import base64
import logging
import pathlib
import secrets

from asyncio import TaskGroup

import math
import requests
import yaml

from typing import Optional, Any, TypedDict

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.NginxHandler import NginxHandler
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages import Constantes as MillegrillesConstantes
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles_messages.messages.FormatteurMessages import FormatteurMessageMilleGrilles


LOGGER = logging.getLogger(__name__)


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


def load_compose_files(securite: str, configuration: ConfigurationInstance) -> list[dict[str, Any]]:
    """
    :param configuration: Instance configuration
    :return: Path to the node type's docker-compose yml file for this instance
    """
    composefiles: list[dict[str, Any]] = list()

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


class CertificateConfiguration(TypedDict):
    name: str
    roles: list[str]
    exchanges: Optional[list[str]]
    domaines: Optional[list[str]]
    dns: Optional[dict[str, str]]
    split: Optional[bool]
    key_path: Optional[pathlib.Path]
    cert_path: Optional[pathlib.Path]
    passwords: Optional[list[str]]


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


def check_certificates(configuration: ConfigurationInstance, certs: list[CertificateConfiguration]) -> list[CertificateConfiguration]:
    secret_path = configuration.path_millegrilles / "secrets"

    to_renew = list()

    for cert in certs:
        if cert.get('split'):
            cert_path = secret_path / f"{cert['name']}.cert.pem"
        else:
            cert_path = secret_path / f"{cert['name']}.pem"

        try:
            cert_enveloppe = EnveloppeCertificat.from_file(cert_path)
        except FileNotFoundError:
            to_renew.append(cert)  # Generate new certificate
            continue

        info_expiration = cert_enveloppe.calculer_expiration()
        if info_expiration.get('expire') or info_expiration.get('renouveler'):
            to_renew.append(cert)

    return to_renew


def check_passwords(configuration: ConfigurationInstance, certs: list[CertificateConfiguration]) -> list[str]:
    secret_path = configuration.path_millegrilles / "secrets"

    to_generate = list()

    for cert in certs:
        try:
            passwords = cert['passwords']
            if not passwords:
                continue  # No passwords
        except KeyError:
            continue  # No passwords

        for p in passwords:
            password_path = secret_path / f"{p}.txt"
            if not password_path.exists():
                to_generate.append(p)

    return to_generate


def signer_module(config: ConfigurationInstance, cert_config: CertificateConfiguration, formatteur_message: FormatteurMessageMilleGrilles):
    certificat = formatteur_message.clecert.enveloppe
    instance_id = certificat.subject_common_name
    idmg = certificat.idmg
    # instance_id = config.instance_id
    # idmg = config.idmg
    cle_csr = CleCsrGenere.build(instance_id, idmg)
    csr_str = cle_csr.get_pem_csr()

    cert_request: dict = cert_config.copy()
    cert_request['csr'] = csr_str

    # Demander un nouveau certificat. Timeout long (60 secondes).
    message_signe, _uuid = formatteur_message.signer_message(MillegrillesConstantes.KIND_DOCUMENT, cert_request)

    url_issuer = f"{config.certissuer_url}/signerModule"
    response = requests.post(url_issuer, json=message_signe)
    response.raise_for_status()
    response_message = response.json()
    certificat = response_message['certificat']

    return cle_csr, certificat


def generer_password(type_generateur='password', size: int = None):
    if type_generateur == 'password':
        if size is None:
            size = 32
        generer_bytes = math.ceil(size / 4 * 3)
        pwd_genere = base64.b64encode(secrets.token_bytes(generer_bytes)).decode('utf-8').replace('=', '')
        valeur = pwd_genere[:size]
    else:
        raise ValueError('Type de generateur inconnu : %s' % type_generateur)

    return valeur

def renew_certificates(context: InstanceContext) -> bool:
    """
    Loads all base docker compose files and recursively goes through includes to cumulate the x-certificate-configuration elements.
    Each certificate under secrets/ that matches the configuration is checked and appropriate certificates are created/renewed.
    """

    # Sanity check
    if context.signing_key.enveloppe.calculer_expiration()['expire']:
        raise Exception("Manager certificate is expired - it must be renewed manually")

    # Process config files
    configuration_file = load_compose_files(context.securite, context.configuration)
    certs = list()
    for file_content in configuration_file:
        new_certs = extract_certificate_configuration(file_content)
        certs.extend(new_certs)

    # Get certs to renew
    certs_to_renew = check_certificates(context.configuration, certs)

    changes_pending = False

    # Submit certs
    formatteur = context.formatteur
    secrets_path = context.configuration.path_millegrilles / "secrets"
    for cert_config in certs_to_renew:
        clecert, new_certificate = signer_module(context.configuration, cert_config, formatteur)
        key_pem = clecert.get_pem_cle().strip()
        cert_pem = "".join(new_certificate).strip()
        if cert_config.get('split'):
            key_path = secrets_path / f"{cert_config['name']}.key.pem"
            cert_path = secrets_path / f"{cert_config['name']}.cert.pem"

            # Delete old files when present
            try:
                key_path.unlink()
            except FileNotFoundError:
                pass
            try:
                cert_path.unlink()
            except FileNotFoundError:
                pass

            # Write new files
            with open(key_path, "w") as key_file:
                key_file.write(key_pem)
            with open(cert_path, "w") as cert_file:
                cert_file.write(cert_pem)
        else:
            # Combined key/cert pem file
            pem_path = secrets_path / f"{cert_config['name']}.pem"
            with open(pem_path, "w") as pem_file:
                pem_file.write(key_pem)
                pem_file.write("\n")
                pem_file.write(cert_pem)

        LOGGER.debug(f"Certificate {cert_config['name']} renewed")
        changes_pending = True

    # Generate missing passwords
    passwords_to_generate = check_passwords(context.configuration, certs)
    for p in passwords_to_generate:
        password = generer_password()
        filename = secrets_path / f"{p}.txt"
        with open(filename, "w") as file:
            file.write(password)
        changes_pending = True
        LOGGER.debug(f"Password {p} generated")

    return changes_pending
