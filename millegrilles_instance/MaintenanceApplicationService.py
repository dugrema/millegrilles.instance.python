# Docker service maintenance
import asyncio
import logging
import pathlib
import json

from typing import Optional

import docker.errors
from docker.models.services import Service

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
    web_only: bool
    disabled: bool
    docker_handle: Optional[Service]

    def __init__(self, configuration: dict, installed=False, replicas=None):
        self.name = configuration['name']
        self.configuration = configuration
        self.installed = installed
        self.running = False
        self.preparing = False
        self.replicas = replicas
        self.web_only = False
        self.disabled = False
        self.docker_handle = None

    def __repr__(self):
        return 'ServiceStatus ' + self.name

class ServiceInstallCommand:
    status: ServiceStatus       # Status
    image_tag: Optional[str]    # Docker image reference
    web_only: bool
    reinstall: bool

    def __init__(self, status: ServiceStatus, image_tag: Optional[str] = None, web_only = False, reinstall = False):
        self.status = status
        self.image_tag = image_tag
        self.web_only = web_only
        self.reinstall = reinstall


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


async def get_service_status(etat_instance, docker_handler: DockerHandler, config_modules: list, missing_only=True) -> list[ServiceStatus]:
    # Get list of core services - they must be installed in order and running before installing other services/apps
    core_services = await get_configuration_services(etat_instance, config_modules)

    mapped_services = dict()
    for service in core_services:
        mapped_services[service.name] = service

    commande_liste_services = DockerCommandes.CommandeListerServices(aio=True)
    docker_handler.ajouter_commande(commande_liste_services)
    liste_services_docker = await commande_liste_services.get_liste()

    # Find all installed web applications
    web_apps = pathlib.Path(etat_instance.configuration.path_configuration, 'web_applications.json')
    try:
        with open(web_apps, 'rt') as fichier:
            web_app_configuration = json.load(fichier)
    except FileNotFoundError:
        web_app_configuration = dict()

    for service in liste_services_docker:
        service_name = service.name
        try:
            mapped_service = mapped_services[service_name]
            mapped_service.docker_handle = service
            mapped_service.installed = True
            mapped_service.running = check_service_running(service) > 0
            mapped_service.preparing = check_service_preparing(service) > 0
            replicas = check_replicas(service)
            mapped_service.replicas = replicas
            if replicas == 0:
                mapped_service.disabled = True
        except KeyError:
            pass  # Not in docker

    for service_name, service_config in mapped_services.items():
        try:
            mapped_service = mapped_services[service_name]
            web_service = web_app_configuration[service_name]
            if mapped_service.configuration.get('image') is None and web_service:
                # This is purely a web application, no docker component
                service_config.web_only = True
        except KeyError:
            pass # Not a web application

    if missing_only:
        # Determine which services are not installed and running
        missing_core_services = [c for c in core_services if c.running is not True and c.web_only is not True and c.disabled is not True]
        return missing_core_services

    return core_services


async def download_docker_images(
        etat_instance, docker_handler: DockerHandler, services: list[ServiceStatus],
        service_queue: asyncio.Queue[Optional[ServiceInstallCommand]]):

    try:
        for service in services:
            try:
                image = service.configuration['image']
            except KeyError as e:
                if len(service.configuration['archives']) > 0:
                    # Install service with web apps only
                    command = ServiceInstallCommand(service, None, True)
                    await service_queue.put(command)
                else:
                    raise Exception("Service without image or archives: %s" % service.name)
            else:
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


async def update_stale_configuration(etat_instance, docker_handler: DockerHandler, config_modules: list):
    # Check if any existing configuration needs to be updated
    liste_services_docker = await get_service_status(etat_instance, docker_handler, config_modules, missing_only=False)
    mapped_services = dict()
    for service in liste_services_docker:
        mapped_services[service.name] = service

    commande_config_courante = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
    docker_handler.ajouter_commande(commande_config_courante)
    resulat_liste_config_datee = await commande_config_courante.get_resultat()
    correspondance_liste_datee = resulat_liste_config_datee['correspondance']

    for service in liste_services_docker:

        try:
            spec = service.docker_handle.attrs['Spec']['TaskTemplate']['ContainerSpec']
        except (KeyError, AttributeError):
            LOGGER.debug("update_stale_configuration No ContainerSpec for service %s" % service.name)
            continue

        try:
            secret_list = spec['Secrets']
        except KeyError:
            secret_list = None
        try:
            config_list = spec['Configs']
        except KeyError:
            config_list = None
        is_current = verifier_config_current(correspondance_liste_datee, config_list, secret_list)
        if is_current is False:
            LOGGER.info("Service %s stale, update config/secrets" % service.name)
            service_status = mapped_services[service.name]
            image = service_status.configuration['image']
            image_tag = await get_docker_image_tag(docker_handler, image)
            install_command = ServiceInstallCommand(service, image_tag, False, True)
            await install_service(etat_instance, docker_handler, install_command)


async def service_maintenance(etat_instance, docker_handler: DockerHandler, config_modules: list):
    # Try to update any stale configuration (e.g. expired certificates)
    await update_stale_configuration(etat_instance, docker_handler, config_modules)

    # Configure and install missing services
    missing_services = await get_service_status(etat_instance, docker_handler, config_modules)
    if len(missing_services) > 0:
        LOGGER.info("Install %d missing or stopped services" % len(missing_services))
        LOGGER.debug("Missing services %s" % missing_services)

        service_install_queue = asyncio.Queue()
        # Run download and install in parallel. If install fails, download keeps going.
        task_download = download_docker_images(etat_instance, docker_handler, missing_services, service_install_queue)
        task_install = install_services(etat_instance, docker_handler, service_install_queue)
        await asyncio.gather(task_install, task_download)
        LOGGER.debug("Install missing or stopped services DONE")


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
            except TypeError:
                LOGGER.debug("Installation d'une application sans dependances (e.g. pur nginx config)")

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
            image_tag, config_parsed, reinstaller=command.reinstall, aio=True)
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


async def remove_service(etat_instance, docker_handler: DockerHandler, app_name: str):
    pass


def verifier_config_current(liste_config_datee: dict, container_config: Optional[list], container_secrets: Optional[list]):

    if container_config is not None:
        for cs in container_config:
            container_name = cs['ConfigName']
            try:
                name_split = container_name.split('.')
                prefix = '.'.join(name_split[0:2])
                if name_split[0] == 'pki':
                    type_data = 'cert'
                else:
                    continue

                current_name = liste_config_datee[prefix]['current'][type_data]['name']

                if current_name != container_name:
                    # On a un mismatch, il faut regenerer la configuration
                    return False
            except KeyError:
                pass  # Secret n'a pas le bon format, pas gere

    if container_secrets is not None:
        for cs in container_secrets:
            container_name = cs['SecretName']
            try:
                name_split = container_name.split('.')
                prefix = '.'.join(name_split[0:2])
                if name_split[0] == 'passwd':
                    type_data = 'password'
                elif name_split[0] == 'pki':
                    type_data = 'key'
                else:
                    continue

                current_name = liste_config_datee[prefix]['current'][type_data]['name']

                if current_name != container_name:
                    # On a un mismatch, il faut regenerer la configuration
                    return False
            except KeyError:
                pass  # Secret n'a pas le bon format, pas gere

    return True


def trier_services(liste_services: list) -> list:

    services_speciaux = ['mq', 'mongo', 'certissuer', 'midcompte', 'nginx', 'redis']

    map_services_parnom = dict()
    liste_services_finale = list()
    for service in liste_services:
        nom_service = service.attrs['Spec']['Name']
        if nom_service in services_speciaux:
            map_services_parnom[nom_service] = service
        else:
            liste_services_finale.append(service)

    # Mettre services par ordre de priorite
    services_speciaux.reverse()
    for nom_service in services_speciaux:
        try:
            service = map_services_parnom[nom_service]
            liste_services_finale.insert(0, service)
        except KeyError:
            pass

    return liste_services_finale


