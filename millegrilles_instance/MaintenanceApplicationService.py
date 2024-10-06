# Docker service maintenance
import asyncio
import logging
import pathlib
import json

from typing import Optional

import docker.errors

from millegrilles_instance.CommandesDocker import check_service_running, check_replicas, check_service_preparing, \
    get_docker_image_tag, UnknownImage
from millegrilles_instance.MaintenanceApplicationWeb import check_archive_stale, installer_archive
from millegrilles_messages.docker.DockerHandler import DockerHandler
from millegrilles_messages.docker import DockerCommandes
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService

LOGGER = logging.getLogger(__name__)


class ServiceStatus:
    name: str
    configuration: dict
    installed: bool
    running: bool
    preparing: bool
    replicas: Optional[int]

    def __init__(self, configuration: dict, installed=False, replicas=None):
        self.name = configuration['name']
        self.configuration = configuration
        self.installed = installed
        self.running = False
        self.preparing = False
        self.replicas = replicas

class ServiceInstallCommand:
    status: ServiceStatus   # Status
    image_tag: str          # Docker image reference

    def __init__(self, status: ServiceStatus, image_tag: str):
        self.status = status
        self.image_tag = image_tag


async def get_configuration_services(etat_instance, config_modules: list) -> list[ServiceStatus]:
    """
    Retourne la liste des services a configurer en ordre.
    """
    path_configuration = etat_instance.configuration.path_configuration
    path_configuration_docker = pathlib.Path(path_configuration, 'docker')
    configurations = await charger_configuration_docker(path_configuration_docker, config_modules)
    configurations_apps = await charger_configuration_application(path_configuration_docker)
    configurations.extend(configurations_apps)

    # map configuration certificat
    services = list()
    for c in configurations:
        try:
            status = ServiceStatus(c)
            services.append(status)
        except KeyError:
            pass

    return services


async def get_missing_services(etat_instance, docker_handler: DockerHandler, config_modules: list) -> list[ServiceStatus]:
    # Get list of core services - they must be installed in order and running before installing other services/apps
    core_services = await get_configuration_services(etat_instance, config_modules)

    mapped_services = dict()
    for service in core_services:
        mapped_services[service.name] = service

    commande_liste_services = DockerCommandes.CommandeListerServices(aio=True)
    docker_handler.ajouter_commande(commande_liste_services)
    liste_services_docker = await commande_liste_services.get_liste()

    for service in liste_services_docker:
        service_name = service.name
        try:
            mapped_service = mapped_services[service_name]
            mapped_service.installed = True
            mapped_service.running = check_service_running(service) > 0
            mapped_service.preparing = check_service_preparing(service) > 0
            mapped_service.replicas = check_replicas(service)
        except KeyError:
            pass  # Unmanaged service

    # Determine which services are not installed and running
    core_services = [c for c in core_services if c.running is not True]

    return core_services


async def download_docker_images(
        etat_instance, docker_handler: DockerHandler, services: list[ServiceStatus],
        service_queue: asyncio.Queue[Optional[ServiceInstallCommand]]):

    try:
        for service in services:
            image = service.configuration['image']
            try:
                image_tag = await get_docker_image_tag(docker_handler, image, pull=False)
            except UnknownImage:
                LOGGER.info('Image %s missing locally, downloading' % image)
                # Todo - download progress
                try:
                    image_tag = await get_docker_image_tag(docker_handler, image, pull=True)
                except UnknownImage:
                    LOGGER.error("Unnkown docker image: %s. Stopping service download/installation" % image)
                    break

            command = ServiceInstallCommand(service, image_tag)
            await service_queue.put(command)
    finally:
        await service_queue.put(None)  # Ensure install thread finishes


async def install_services(
        etat_instance, docker_handler: DockerHandler,
        service_queue: asyncio.Queue[Optional[ServiceInstallCommand]]):
    # Install all services in order. Return on first exception.
    while True:
        command = await service_queue.get()
        if command is None:
            break  # Done

        service = command.status

        service_name = service.name
        try:
            if service.installed is False:
                await install_service(etat_instance, docker_handler, command)
            elif service.replicas == 0:
                pass  # Service is manually disabled
            elif service.preparing and service.running is False:
                raise NotImplementedError('TODO - wait for end of preparation')
            elif service.running is False:
                # Restart service
                LOGGER.info("Restarting service %s" % service_name)
                restart_command = DockerCommandes.CommandeRedemarrerService(nom_service=service_name, aio=True)
                docker_handler.ajouter_commande(restart_command)
                await restart_command.attendre()
            else:
                raise Exception('install_services Service in unknown state: %s' % service_name)
        except Exception:
            LOGGER.exception("Error installing service %s, aborting for this cycle" % service_name)


async def update_stale_configuration(etat_instance, docker_handler: DockerHandler):
    # Check if any existing configuration needs to be updated
    commande_config_courante = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
    docker_handler.ajouter_commande(commande_config_courante)
    liste_config_datee = await commande_config_courante.get_resultat()

    LOGGER.warning("update_stale_configuration NOT IMPLEMENTED - TODO")


async def service_maintenance(etat_instance, docker_handler: DockerHandler, config_modules: list):
    # Try to update any stale configuration (e.g. expired certificates)
    await update_stale_configuration(etat_instance, docker_handler)

    # Configure and install missing services
    missing_services = await get_missing_services(etat_instance, docker_handler, config_modules)
    if len(missing_services) > 0:
        LOGGER.info("Install %d missing services" % len(missing_services))

        service_install_queue = asyncio.Queue()
        # Run download and install in parallel. If install fails, download keeps going.
        task_download = download_docker_images(etat_instance, docker_handler, missing_services, service_install_queue)
        task_install = install_services(etat_instance, docker_handler, service_install_queue)
        await asyncio.gather(task_install, task_download)
        LOGGER.debug("Install missing services DONE")


async def charger_configuration_docker(path_configuration: pathlib.Path, fichiers: list) -> list:
    configuration = []
    for filename in fichiers:
        path_fichier = pathlib.Path(path_configuration, filename)
        try:
            with open(path_fichier, 'rb') as fichier:
                contenu = json.load(fichier)
            configuration.append(contenu)
        except FileNotFoundError:
            LOGGER.error("Fichier de module manquant : %s" % path_fichier)

    return configuration


async def charger_configuration_application(path_configuration: pathlib.Path) -> list:
    configuration = []
    try:
        filenames = path_configuration.iterdir()
    except FileNotFoundError:
        # Aucune configuration
        return list()

    for file in filenames:
        filename = file.name
        if filename.startswith('app.'):
            path_fichier = pathlib.Path(path_configuration, filename)
            try:
                with open(path_fichier, 'rb') as fichier:
                    contenu = json.load(fichier)

                deps = contenu['dependances']

                configuration.extend(deps)
            except FileNotFoundError:
                LOGGER.error("Fichier de module manquant : %s" % path_fichier)

    return configuration


async def install_service(etat_instance, docker_handler: DockerHandler, command: ServiceInstallCommand):
    service_name = command.status.name
    LOGGER.info("Installing service %s" % service_name)
    image_tag = command.image_tag

    # Copier params, ajouter info service
    params = await get_params_env_service(etat_instance, docker_handler)
    params['__nom_application'] = service_name
    params['__certificat_info'] = {'label_prefix': 'pki.%s' % service_name}
    params['__password_info'] = {'label_prefix': 'passwd.%s' % service_name}
    params['__instance_id'] = etat_instance.instance_id

    mq_hostname = etat_instance.mq_hostname
    if mq_hostname == 'localhost':
        # Remplacer par mq pour applications (via docker)
        mq_hostname = 'mq'
    params['MQ_HOSTNAME'] = mq_hostname
    params['MQ_PORT'] = etat_instance.mq_port or '5673'
    if etat_instance.idmg is not None:
        params['__idmg'] = etat_instance.idmg

    config_service = command.status.configuration.copy()
    try:
        config_service.update(config_service['config'])  # Combiner la configuration de base et du service
    except KeyError:
        pass

    parser = ConfigurationService(config_service, params)
    parser.parse()
    config_parsed = parser.generer_docker_config()

    # Creer node-labels pour les constraints
    constraints = parser.constraints
    list_labels = list()
    try:
        for constraint in constraints:
            nom_constraint = constraint.split('=')[0]
            nom_constraint = nom_constraint.replace('node.labels.', '').strip()
            list_labels.append(nom_constraint)
        commande_ajouter_labels = DockerCommandes.CommandeEnsureNodeLabels(list_labels, aio=True)
        docker_handler.ajouter_commande(commande_ajouter_labels)
        await commande_ajouter_labels.attendre()
    except TypeError:
        pass  # Aucune constraint

    # Installer les archives si presentes
    if parser.archives:
        for archive in parser.archives:
            if await asyncio.to_thread(check_archive_stale, etat_instance, archive):
                service_name = command.status.name
                web_links = command.status.configuration.get('web')
                await asyncio.to_thread(installer_archive, etat_instance, service_name, archive, web_links)

    # S'assurer d'avoir l'image
    image = parser.image
    if image is not None:
        commande_creer_service = DockerCommandes.CommandeCreerService(
            image_tag, config_parsed, reinstaller=False, aio=True)
        docker_handler.ajouter_commande(commande_creer_service)
        resultat = await commande_creer_service.get_resultat()

        return resultat
    else:
        LOGGER.debug("installer_service() Invoque pour un service sans images : %s", service_name)


async def get_params_env_service(etat_instance, docker_handler: DockerHandler) -> dict:
    # Charger configurations
    action_configurations = DockerCommandes.CommandeListerConfigs(aio=True)
    docker_handler.ajouter_commande(action_configurations)
    docker_configs = await action_configurations.get_resultat()

    action_secrets = DockerCommandes.CommandeListerSecrets(aio=True)
    docker_handler.ajouter_commande(action_secrets)
    docker_secrets = await action_secrets.get_resultat()

    action_datees = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
    docker_handler.ajouter_commande(action_datees)
    config_datees = await action_datees.get_resultat()

    params = {
        'HOSTNAME': etat_instance.hostname,
        'IDMG': etat_instance.idmg,
        '__secrets': docker_secrets,
        '__configs': docker_configs,
        '__docker_config_datee': config_datees['correspondance'],
    }

    return params


async def nginx_installation_cleanup(etat_instance, docker_handler: DockerHandler):
    """
    Ensure nginxinstall and other installation services are removed.
    """
    action_remove = DockerCommandes.CommandeSupprimerService("nginxinstall", aio=True)
    docker_handler.ajouter_commande(action_remove)
    try:
        await action_remove.get_resultat()
    except docker.errors.NotFound:
        pass  # Ok, already removed
