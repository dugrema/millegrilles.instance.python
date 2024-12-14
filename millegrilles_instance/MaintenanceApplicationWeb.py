# Standalone web application maintenance
import asyncio
import json
import logging
import pathlib
import shutil
import tarfile

import requests

from typing import Optional

from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.Context import InstanceContext
from millegrilles_docker.ParseConfiguration import WebApplicationConfiguration
from millegrilles_messages.messages.Hachage import VerificateurHachage

CONST_VERSION_FILE = '.version'

LOGGER = logging.getLogger(__name__)


def check_archive_stale(context: InstanceContext, archive: WebApplicationConfiguration) -> bool:
    """
    Returns true if the web application is stale and should be replaced.
    """
    module = archive.module
    sub_path = archive.path

    if module == 'nginx':
        module_path = context.configuration.path_nginx
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


def installer_archive(context: InstanceContext, app_name: str, archive: WebApplicationConfiguration, web_links: Optional[dict]=None):
    module = archive.module
    sub_path = archive.path
    app_url = archive.app_url

    if module == 'nginx':
        module_path = context.configuration.path_nginx
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

        LOGGER.debug('Extracting %s' % file_download_path)
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
        path_archives_json = pathlib.Path(context.configuration.path_configuration,
                                          ConstantesInstance.FICHIER_CONFIG_ARCHIVES_APP_JSON)
        try:
            with open(path_archives_json, 'rt+') as fichier:
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
            with open(path_archives_json, 'wt') as fichier:
                config_locale = {archive.location: archive.__dict__}
                json.dump(config_locale, fichier)

        # Conserver url links de l'application
        if web_links is not None:
            sauvegarder_configuration_webapps(context, app_name, web_links)

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
                name = config['nom']
                try:
                    archives = dep['archives']
                except KeyError:
                    pass
                else:
                    for archive_dict in archives:
                        archive = WebApplicationConfiguration(archive_dict)
                        try:
                            if await asyncio.to_thread(check_archive_stale, etat_instance, archive):
                                await asyncio.to_thread(installer_archive, etat_instance, name, archive, config.get('web'))
                        except:
                            LOGGER.exception("Error checking web app %s", config_file.name)


def sauvegarder_configuration_webapps(context: InstanceContext, nom_application: str, web_links: dict):
    LOGGER.debug("Sauvegarder configuration pour web app %s" % nom_application)

    configuration = context.configuration

    path_conf_applications = pathlib.Path(
        configuration.path_configuration,
        ConstantesInstance.CONFIG_NOMFICHIER_CONFIGURATION_WEB_APPLICATIONS)

    hostname = context.hostname
    try:
        links = web_links['links']
    except (TypeError, KeyError):
        LOGGER.debug("sauvegarder_configuration_webapps Aucun web links pour %s" % nom_application)
    else:
        for link in links:
            try:
                link['url'] = link['url'].replace('${HOSTNAME}', hostname)
            except KeyError:
                pass  # No url
        try:
            with open(path_conf_applications, 'rt+') as fichier:
                config_apps_json = json.load(fichier)
                config_apps_json[nom_application] = web_links
                fichier.seek(0)
                json.dump(config_apps_json, fichier)
                fichier.truncate()
        except (FileNotFoundError, json.JSONDecodeError):
            config_apps_json = dict()
            config_apps_json[nom_application] = web_links
            with open(path_conf_applications, 'wt') as fichier:
                json.dump(config_apps_json, fichier)
