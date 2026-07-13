import asyncio
from argparse import Namespace

import pytest

from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.apps.AppManager import load_compose_files, extract_certificate_list, \
    extract_certificate_configuration


def load_config():
    args = Namespace(config="/home/mathieu/tas/dev/millegrilles/dev1")
    config = ConfigurationInstance(args)
    return config

@pytest.mark.asyncio
async def test_renew():
    config = load_config()
    configuration_file = load_compose_files(config)
    certs = list()
    for file_content in configuration_file:
        new_certs = extract_certificate_configuration(file_content)
        certs.extend(new_certs)
    print('test_renew')
