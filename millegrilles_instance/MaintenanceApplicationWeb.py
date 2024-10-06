# Standalone web application maintenance
import asyncio
import json
import logging
import pathlib
import shutil
import tarfile

import requests

from millegrilles_instance.Constantes import FICHIER_ARCHIVES_APP
from millegrilles_messages.docker.ParseConfiguration import WebApplicationConfiguration
from millegrilles_messages.messages.Hachage import VerificateurHachage

CONST_VERSION_FILE = '.version'

LOGGER = logging.getLogger(__name__)


def check_archive_stale(etat_instance, archive: WebApplicationConfiguration) -> bool:
    """
    Returns true if the web application is stale and should be replaced.
    """
    module = archive.module
    sub_path = archive.path

    if module == 'nginx':
        module_path = etat_instance.configuration.path_nginx
    else:
        raise Exception('Module %s is not supported' % module)

    installation_path = pathlib.Path(module_path, sub_path)

    try:
        digest = archive.digest
        digest_check_path = pathlib.Path(installation_path, CONST_VERSION_FILE)
        with open(digest_check_path, 'rt') as fichier:
            digest_value = fichier.readline()
        return digest_value != digest  # If different, archive is stale
    except FileNotFoundError:
        # Not installed -> stale
        return True


def installer_archive(etat_instance, archive: WebApplicationConfiguration):
    module = archive.module
    sub_path = archive.path
    app_url = archive.app_url

    if module == 'nginx':
        module_path = etat_instance.configuration.path_nginx
    else:
        raise Exception('Module %s is not supported' % module)

    installation_path = pathlib.Path(module_path, sub_path)
    tmp_extract_path = pathlib.Path(installation_path.parent, installation_path.name + '.new')
    tmp_old_path = pathlib.Path(installation_path.parent, installation_path.name + '.old')
    download_path = pathlib.Path(installation_path.parent, '.download')
    file_download_path = pathlib.Path(download_path, archive.filename)

    try:
        # Creer le repertoire
        download_path.mkdir(parents=True, exist_ok=True)
        # Cleanup
        try:
            shutil.rmtree(tmp_extract_path)
        except FileNotFoundError:
            pass  # Ok

        # Verifier hachage au vol
        hachage = 'm' + archive.digest  # Multibase base64 (char m)
        verificateur = VerificateurHachage(hachage)

        # Download file
        LOGGER.info('Downloading %s' % app_url.geturl())
        with open(file_download_path, 'wb') as output:
            with requests.get(app_url.geturl(), stream=True) as r:
                r.raise_for_status()
                for chunk in r.iter_content(1024*64):
                    output.write(chunk)
                    verificateur.update(chunk)

        # Verifier hachage, lance exception si incorrect
        verificateur.verify()

        LOGGER.info('Extracting %s' % file_download_path)
        with tarfile.open(file_download_path, 'r:gz') as fichier:
            fichier.extractall(tmp_extract_path)

        # Save the digest in .version file. Allows easily checking if the application is stale
        digest_check_path = pathlib.Path(tmp_extract_path, CONST_VERSION_FILE)
        with open(digest_check_path, 'wt') as fichier:
            fichier.write(archive.digest)

        LOGGER.info('Replacing %s' % installation_path)
        try:
            installation_path.rename(tmp_old_path)
        except FileNotFoundError:
            pass  # Le repertoire n'existait pas
        tmp_extract_path.rename(installation_path)

        try:
            shutil.rmtree(tmp_old_path)
        except FileNotFoundError:
            pass  # Ok

        # Conserver l'information d'installation
        try:
            with open(FICHIER_ARCHIVES_APP, 'rt+') as fichier:
                # Read file
                try:
                    config_locale = json.load(fichier)
                except json.JSONDecodeError:
                    # Likely an empty file
                    LOGGER.info("Overriding/creating new archives.json configuration file")
                    config_locale = dict()

                config_locale[archive.location] = archive.__dict__

                # Overwrite file
                fichier.seek(0)
                json.dump(config_locale, fichier)

                # Truncate when shortened
                fichier.truncate()
        except FileNotFoundError:
            # New file
            with open(FICHIER_ARCHIVES_APP, 'wt') as fichier:
                config_locale = {archive.location: archive.__dict__}
                json.dump(config_locale, fichier)

    except Exception as e:
        # If the old path is present, restore it
        if tmp_old_path.exists():
            try:
                shutil.rmtree(installation_path)
            except FileNotFoundError:
                pass # Ok
            tmp_old_path.rename(installation_path)

        raise e
    finally:
        try:
            shutil.rmtree(tmp_extract_path)
        except FileNotFoundError:
            pass  # Ok

        file_download_path.unlink(missing_ok=True)

    pass


async def entretien_webapps_installation(etat_instance):
    """
    S'assure que toutes les web apps d'installation (millegrilles/configuration/webappconfig) sont deployees
    """
    path_configuration = pathlib.Path(etat_instance.configuration.path_configuration)
    path_webapps = pathlib.Path(path_configuration, 'webappconfig')

    for config_file in path_webapps.iterdir():
        if config_file.is_file() and config_file.name.endswith('.json'):
            LOGGER.debug("Check app %s" % config_file)

            with open(config_file, 'rt') as fichier:
                config = json.load(fichier)

            for dep in config['dependances']:
                try:
                    archives = dep['archives']
                except KeyError:
                    pass
                else:
                    for archive_dict in archives:
                        archive = WebApplicationConfiguration(archive_dict)
                        try:
                            if await asyncio.to_thread(check_archive_stale, etat_instance, archive):
                                await asyncio.to_thread(installer_archive, etat_instance, archive)
                        except:
                            LOGGER.exception("Error checking web app %s", config_file.name)