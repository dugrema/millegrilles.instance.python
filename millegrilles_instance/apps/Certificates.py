import asyncio
import base64
import logging
import pathlib
import secrets

import math
import requests
import yaml

from typing import Optional, Any, TypedDict

from aiohttp import ClientError, ClientSession, TCPConnector, ClientTimeout

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_messages.bus.PikaMessageProducer import MilleGrillesPikaMessageProducer
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.messages import Constantes as MillegrillesConstantes
from millegrilles_messages.messages.CleCertificat import CleCertificat
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
            try:
                include_file = include_file['path']
            except (TypeError, KeyError):
                pass
            yaml_file_parent = yaml_file.parent
            parent_join = yaml_file_parent.joinpath(include_file)
            include_file_path = parent_join.resolve()
            file_content = load_yaml_recursive(include_file_path)
            files_dict[include_file_path] = file_content
    except KeyError:
        pass

    return compose_configuration


def load_compose_files(securite: str, configuration: ConfigurationInstance) -> list[dict[str, Any]]:
    """
    :param securite: Security level of the node
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

    compose_file_nodetype = configuration.path_millegrilles / "etc/compose/middleware" / filename
    config_nodetype = load_yaml_recursive(compose_file_nodetype)
    composefiles.append(config_nodetype)

    # Add service dependencies (certs, downloading new docker images)
    if securite == MillegrillesConstantes.SECURITE_SECURE:
        certs_service_file = configuration.path_millegrilles / "etc/compose/include/secure_service_deps.yml"
    elif securite == MillegrillesConstantes.SECURITE_PROTEGE:
        certs_service_file = configuration.path_millegrilles / "etc/compose/include/protege_service_deps.yml"
    elif securite == MillegrillesConstantes.SECURITE_PRIVE:
        certs_service_file = configuration.path_millegrilles / "etc/compose/include/private_service_deps.yml"
    elif securite == MillegrillesConstantes.SECURITE_PUBLIC:
        certs_service_file = configuration.path_millegrilles / "etc/compose/include/public_service_deps.yml"
    else:
        certs_service_file = None

    if certs_service_file:
        config_services = load_yaml_recursive(certs_service_file)
        composefiles.append(config_services)

    applications_file = configuration.path_millegrilles / "etc/compose/applications.yml"
    if applications_file.exists():
        config_applications = load_yaml_recursive(applications_file)
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
    init_only = configuration.init_only

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
        if info_expiration.get('expire'):
            # Always regenerate certificates that are expired immediately
            # This has an impact on some domains like Maitredescles (it needs to be notified on key changes to migrate its secrets)
            to_renew.append(cert)
        elif not init_only and info_expiration.get('renouveler'):
            # Only renew certificates if the manager is currently running (so not in --init mode)
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


async def signer_module_core(producer: MilleGrillesPikaMessageProducer, context: InstanceContext, configuration_cert: CertificateConfiguration) -> CleCertificat:
    """
    Uses the MQ Bus with Core to renew certificates. Used when local certissuer is not available (e.g. public/private satellite nodes)
    """
    config = context.configuration
    instance_id = config.instance_id
    idmg = config.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    configuration_cert['csr'] = csr_str

    # Demander un nouveau certificat. Timeout long (60 secondes).
    message_reponse = await producer.command(configuration_cert, 'CorePki', 'signerCsr',
                                             exchange=MillegrillesConstantes.SECURITE_PUBLIC, timeout=3)
    reponse = message_reponse.parsed
    certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    return clecertificat


async def check_certissuer_available(context: InstanceContext):
    config = context.configuration
    url_issuer = f"{config.certissuer_url}/certificate.pem"
    timeout = ClientTimeout(3)
    if url_issuer.startswith('https'):
        connector = TCPConnector(ssl=context.ssl_context)
        session = ClientSession(timeout=timeout, connector=connector)
        session.verify = True
    else:
        session = ClientSession(timeout=timeout)
    try:
        async with session.get(url_issuer) as response:
            return response.status == 200
    except ClientError as e:
        LOGGER.info(f"Local certissuer not available: {e}")
        return False
    finally:
        await session.close()



def signer_module_certissuer(config: ConfigurationInstance, cert_config: CertificateConfiguration, formatteur_message: FormatteurMessageMilleGrilles) -> CleCertificat:
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

    clecertificat = CleCertificat.from_pems(cle_csr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    return clecertificat


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

async def renew_certificates(context: InstanceContext) -> list[dict]:
    """
    Loads all base docker compose files and recursively goes through includes to cumulate the x-certificate-configuration elements.
    Each certificate under secrets/ that matches the configuration is checked and appropriate certificates are created/renewed.
    """
    if context.configuration.is_docker_disabled:
        return []  # Nothing to manage

    # Sanity check
    if context.signing_key.enveloppe.calculer_expiration()['expire']:
        raise Exception("Manager certificate is expired - it must be renewed manually")

    # Process config files
    certs = list()
    configuration_file = load_compose_files(context.securite, context.configuration)
    for file_content in configuration_file:
        new_certs = extract_certificate_configuration(file_content)
        certs.extend(new_certs)

    # Get certs to renew
    certs_to_renew = check_certificates(context.configuration, certs)

    if not certs_to_renew:
        return []  # Done

    cert_issuer_avaiable = await check_certissuer_available(context)
    if not cert_issuer_avaiable:
        # Ensure that we have access to the MQ producer
        producer = await asyncio.wait_for(context.get_producer(), 1)
    else:
        producer = None

    renewed_config: list[dict] = list()

    # Submit certs
    formatteur = context.formatteur
    secrets_path = context.configuration.path_millegrilles / "secrets"
    for cert_config in certs_to_renew:
        # Inject local hostname when required
        cert_config_copy: CertificateConfiguration = cert_config.copy()
        try:
            dns = cert_config_copy['dns'].copy()
            if dns.get('domain') is True:
                hostname = context.hostname
                hostnames = [hostname]
                short_name = hostname.split('.')[0]
                if short_name != hostname:
                    hostnames.append(short_name)
                if dns.get('hostnames') is not None:
                    hostnames.extend(dns['hostnames'])
                dns['hostnames'] = hostnames
                cert_config_copy['dns'] = dns
        except KeyError:
            pass

        # Remove passwords, they are handled separately
        keys = set(cert_config_copy.keys())
        keys.remove('name')
        try:
            keys.remove('passwords')
        except KeyError:
            pass  # No passwords

        if len(keys) > 0:
            if cert_issuer_avaiable:
                cle_certificat = signer_module_certissuer(context.configuration, cert_config_copy, formatteur)
            elif producer:
                cle_certificat = await signer_module_core(producer, context, cert_config_copy)
            else:
                raise Exception('No means of accessing certissuer found')

            key_pem = cle_certificat.private_key_bytes().decode('utf-8')
            new_certificate = cle_certificat.enveloppe
            cert_pem = "\n".join(new_certificate.chaine_pem()) + "\n"

            # Check if we have to notify the maitre des cles (if --init, the certificate will only show up when ALREADY expired)
            if not context.configuration.init_only and not context.configuration.is_docker_disabled:
                try:
                    if MillegrillesConstantes.DOMAINE_MAITRE_DES_CLES in cert_config_copy['domaines']:
                        try:
                            cert_path = secrets_path / f"{cert_config_copy['name']}.cert.pem"
                            old_cert = EnveloppeCertificat.from_file(cert_path)
                            await rotation_maitredescles(context, old_cert, new_certificate)
                        except (TimeoutError, ValueError):
                            LOGGER.exception("Error rotation certificate for keymaster")
                            continue  # Keep going with other certificates
                        except FileNotFoundError:
                            LOGGER.warning("Old keymaster certificate cannot be loaded, rotating without warning")
                except KeyError:
                    pass

            if cert_config.get('split'):
                key_path = secrets_path / f"{cert_config_copy['name']}.key.pem"
                cert_path = secrets_path / f"{cert_config_copy['name']}.cert.pem"

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
                pem_path = secrets_path / f"{cert_config_copy['name']}.pem"
                with open(pem_path, "w") as pem_file:
                    pem_file.write(key_pem)
                    pem_file.write("\n")
                    pem_file.write(cert_pem)

            LOGGER.debug(f"Certificate {cert_config_copy['name']} renewed")
            renewed_config.append(cert_config_copy)

    # Generate missing passwords
    passwords_to_generate = check_passwords(context.configuration, certs)
    for p in passwords_to_generate:
        password = generer_password()
        filename = secrets_path / f"{p}.txt"
        with open(filename, "w") as file:
            file.write(password)
        LOGGER.debug(f"Password {p} generated")

    return renewed_config


async def rotation_maitredescles(context: InstanceContext, old_certificate: EnveloppeCertificat, new_certificate: EnveloppeCertificat):
    producer = await context.get_producer()

    fingerprint = old_certificate.fingerprint
    command = {
        'certificat': new_certificate.chaine_pem(),
    }

    LOGGER.info(f"Requesting rotation of keymaster with key fingerprint {fingerprint}")
    response = await producer.command(
        command, 'MaitreDesCles', 'rotationCertificat',
        exchange='3.protege',
        partition=fingerprint
    )

    if not response:
        raise ValueError("No response received from MaitreDesCles for rotationCertificat")

    if response.parsed['ok'] is False:
        raise ValueError(f'Error trying to rotate a keymaster certificate: {response.parsed.get('err')}')
