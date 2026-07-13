import pathlib
import os

from argparse import Namespace

import pytest

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.apps.AppManager import load_compose_files, \
    extract_certificate_configuration, check_certificates, signer_module
from millegrilles_messages.bus.BusContext import load_message_formatter
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat

ROOT_PATH = pathlib.Path(os.environ.get("MILLEGRILLES_ROOT") or "/tmp/millegrilles_dev1")

def load_manager_certs():
    args = Namespace(config=ROOT_PATH)
    config = ConfigurationInstance(args)

    manager_pem_path = ROOT_PATH.joinpath("secrets/manager.pem")
    ca_pem_path = ROOT_PATH.joinpath("etc/millegrille.pem")

    manager_key = CleCertificat.from_files(manager_pem_path, manager_pem_path)
    ca = EnveloppeCertificat.from_file(str(ca_pem_path))

    signateur, formatteur = load_message_formatter(manager_key, ca)

    return config, manager_key, ca, signateur, formatteur


@pytest.mark.asyncio
async def test_list_to_renew():
    config, manager_key, ca, signateur, formateur = load_manager_certs()

    # Process config files
    configuration_file = load_compose_files(config)
    certs = list()
    for file_content in configuration_file:
        new_certs = extract_certificate_configuration(file_content)
        certs.extend(new_certs)

    # Get certs to renew
    certs_to_renew = check_certificates(config, certs)
    assert len(certs_to_renew) == len(certs)

    # Submit certs
    for cert_config in certs_to_renew:
        clecert, new_certificate = signer_module(manager_key, cert_config, formateur)
        key_pem = clecert.get_pem_cle().strip()
        cert_pem = "".join(new_certificate).strip()
        if cert_config.get('split'):
            print(f"\nKey PEM:\n{key_pem}\nCert PEM:\n{cert_pem}")
        else:
            pem_content = f"{key_pem}\n{cert_pem}"
            print(f"\nNew combined PEM:\n{pem_content}")
        pass

