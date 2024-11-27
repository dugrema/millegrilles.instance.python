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
from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.Interfaces import DockerHandlerInterface
from millegrilles_instance.MaintenanceApplicationWeb import check_archive_stale, installer_archive, \
    sauvegarder_configuration_webapps
from millegrilles_instance.ModulesRequisInstance import RequiredModules
from millegrilles_messages.docker import DockerCommandes
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService

LOGGER = logging.getLogger(__name__)

class ServiceDependency:
    name: str
    image: Optional[str]
    archives: Optional[dict]
    certificate: Optional[dict]
    config: Optional[dict]
    secrets: Optional[dict]
    passwords: Optional[list]

    def __init__(self, value: dict):
        self.__value = value
        self.name = value['name']
        self.image = value.get('image')
        self.archives = value.get('archives')
        self.certificate = value.get('certificat')
        self.config = value.get('config')
        self.secrets = value.get('secrets')
        self.passwords = value.get('passwords') or value.get('generateur')

    @property
    def configuration(self):
        return self.__value

class ServiceStatus:
    name: str
    # configuration: dict
    dependencies: Optional[list[ServiceDependency]]
    installed: bool
    running: bool
    preparing: bool
    replicas: Optional[int]
    disabled: bool
    docker_handle: Optional[Service]

    def __init__(self, app_configuration: dict,  installed=False, replicas=None):
        self.__app_configuration = app_configuration
        self.name = app_configuration['nom']
        self.installed = installed
        self.running = False
        self.preparing = False
        self.replicas = replicas
        self.disabled = False
        self.docker_handle = None

        try:
            dependencies = app_configuration['dependances']
        except KeyError:
            self.dependencies = None
        else:
            deps = list()
            for d in dependencies:
                deps.append(ServiceDependency(d))
            self.dependencies = deps

    @property
    def nginx(self) -> Optional[dict]:
        return self.__app_configuration.get('nginx')

    @property
    def web_config(self) -> Optional[dict]:
        return self.__app_configuration.get('web')

    def to_dict(self):
        return self.__app_configuration

    def __repr__(self):
        return 'ServiceStatus ' + self.name

    @staticmethod
    def from_dependency(dep: dict):
        return ServiceStatus({'nom': dep['name'], 'dependances': [dep]})


class ServiceInstallCommand:
    status: ServiceStatus       # Status
    image_tag: Optional[dict[str, str]]    # Docker image reference
    web_only: bool
    reinstall: bool
    upgrade: bool

    def __init__(self, status: ServiceStatus, image_tags: Optional[dict[str, str]] = None, web_only = False,
                 reinstall = False, upgrade = False):
        self.status = status
        self.image_tag = image_tags
        self.web_only = web_only
        self.reinstall = reinstall
        self.upgrade = upgrade


async def get_configuration_services(etat_instance, config_modules: RequiredModules) -> list[ServiceStatus]:
    """
    Retourne la liste des services a configurer en ordre.
    """
    path_configuration = etat_instance.configuration.path_configuration
    path_configuration_docker = pathlib.Path(path_configuration, 'docker')
    path_configuration_webappconfig = pathlib.Path(path_configuration, 'webappconfig')
    dependances = await charger_configuration_docker(path_configuration_docker, config_modules)

    # map configuration
    services = list()
    for dep in dependances:
        try:
            status = ServiceStatus.from_dependency(dep)
            services.append(status)
        except KeyError:
            pass

    configurations_apps = await charger_configuration_application(path_configuration_docker)
    for app in configurations_apps:
        try:
            status = ServiceStatus(app)
            services.append(status)
        except KeyError:
            pass

    configuration_webapps = await charger_configuration_webapps(path_configuration_webappconfig)
    for webapp in configuration_webapps:
        status = ServiceStatus(webapp)
        services.append(status)

    return services


async def get_service_status(context: InstanceContext, docker_handler: DockerHandlerInterface,
                             missing_only=True) -> list[ServiceStatus]:

    # Get list of core services - they must be installed in order and running before installing other services/apps
    config_modules = context.application_status.required_modules
    core_services = await get_configuration_services(context, config_modules)

    mapped_services: dict[str, ServiceStatus] = dict()
    for service in core_services:
        mapped_services[service.name] = service

    commande_liste_services = DockerCommandes.CommandeListerServices()
    await docker_handler.run_command(commande_liste_services)
    liste_services_docker = await commande_liste_services.get_liste()

    # Find all installed web applications
    web_apps = pathlib.Path(context.configuration.path_configuration, 'web_applications.json')
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
            # mapped_service: ServiceStatus = mapped_services[service_name]
            web_service = web_app_configuration[service_name]
            for app_dependency in service_config.dependencies:
                if app_dependency.image is None and web_service:
                    # This is purely a web application, no docker component
                    service_config.web_only = True

                    # Check if the application is installed
                    path_webapps = pathlib.Path(context.configuration.path_nginx)
                    for archive in app_dependency.archives:
                        location = archive['location']
                        module, app_path = location.split(":")
                        if module == 'nginx':
                            path_webapp = pathlib.Path(path_webapps, app_path)
                            path_version_file = pathlib.Path(path_webapp, '.version')
                            try:
                                with open(path_version_file, 'rt') as fichier:
                                    version = fichier.readline()
                            except FileNotFoundError:
                                version = None
                            if version == archive['digest']:
                                service_config.installed = True
                                service_config.running = True
        except KeyError:
            pass # Not a web application

    service_name_list = [c.name for c in core_services]
    for name, value in mapped_services.items():
        try:
            pos = service_name_list.index(name)
        except ValueError:
            pos = None

        context.update_application_status(name, {
            'status': {
                'disabled': value.disabled,
                'installed': value.installed,
                'preparing': value.preparing,
                'running': value.running,
                'name': name,
                'pos': pos,
            },
        })

    if missing_only:
        # Determine which services are not installed and running
        missing_core_services = [c for c in core_services if (c.installed is not True or c.running is not True) and c.disabled is not True]
        return missing_core_services

    return core_services


async def download_docker_images(
        etat_instance, docker_handler: DockerHandlerInterface,
        input_queue: asyncio.Queue[Optional[ServiceStatus]],
        service_queue: asyncio.Queue[Optional[ServiceInstallCommand]]):

    try:
        while True:
            service: ServiceStatus = await input_queue.get()
            if service is None:
                return  # Exit condition

            image_tags = dict()
            for app_dependency in service.dependencies:
                service_name = service.name
                image = app_dependency.image
                if image is None:
                    try:
                        if len(app_dependency.archives) > 0:
                            # Install service with web apps only
                            command = ServiceInstallCommand(service, None, True)
                            await service_queue.put(command)
                        else:
                            LOGGER.debug("Nothing to download for service %s without image or archives" % service.name)
                    except TypeError:
                        LOGGER.debug("Nothing to download for service %s without image or archives" % service.name)
                else:
                    try:
                        image_tag = await get_docker_image_tag(etat_instance, docker_handler, image, pull=False)
                    except UnknownImage:
                        LOGGER.info('Image %s missing locally, downloading' % image)
                        try:
                            image_tag = await get_docker_image_tag(etat_instance, docker_handler, image, pull=True, app_name=service_name)
                        except UnknownImage:
                            LOGGER.error("Unnkown docker image: %s. Stopping service download/installation" % image)
                            break

                    image_tags[service_name] = image_tag

                command = ServiceInstallCommand(service, image_tags)
                await service_queue.put(command)
    finally:
        await service_queue.put(None)  # Ensure install thread finishes


async def install_services(
        context: InstanceContext, docker_handler: DockerHandlerInterface,
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
                await install_service(context, docker_handler, command)
            elif service.replicas == 0:
                pass  # Service is manually disabled
            elif service.preparing and service.running is False:
                raise NotImplementedError('TODO - wait for end of preparation')
            elif service.running is False:
                # Restart service
                LOGGER.info("Restarting service %s" % service_name)
                restart_command = DockerCommandes.CommandeRedemarrerService(nom_service=service_name)
                await docker_handler.run_command(restart_command)
            else:
                raise Exception('install_services Service in unknown state: %s' % service_name)
        except asyncio.CancelledError as e:
            raise e
        except Exception:
            LOGGER.exception("Error installing service %s, aborting for this cycle" % service_name)


async def update_stale_configuration(context: InstanceContext, docker_handler: DockerHandlerInterface):
    # Check if any existing configuration needs to be updated
    liste_services_docker = await get_service_status(context, docker_handler, missing_only=False)
    mapped_services = dict()
    for service in liste_services_docker:
        mapped_services[service.name] = service

    commande_config_courante = DockerCommandes.CommandeGetConfigurationsDatees()
    await docker_handler.run_command(commande_config_courante)
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
            for dep in service_status.dependencies:
                image = dep.image
                if image:
                    image_tag = await get_docker_image_tag(context, docker_handler, image)
                else:
                    image_tag = None
                install_command = ServiceInstallCommand(service, image_tag, False, True)
                await install_service(context, docker_handler, install_command)

async def service_maintenance(context: InstanceContext, docker_handler: DockerHandlerInterface):
    # Try to update any stale configuration (e.g. expired certificates)
    await update_stale_configuration(context, docker_handler)

    # # Configure and install missing services
    # missing_services = await get_service_status(context, docker_handler, config_modules)
    # if len(missing_services) > 0:
    #     LOGGER.info("Install %d missing or stopped services" % len(missing_services))
    #     LOGGER.debug("Missing services %s" % missing_services)
    #
    #     service_install_queue = asyncio.Queue()
    #     # Run download and install in parallel. If install fails, download keeps going.
    #     task_download = download_docker_images(context, docker_handler, missing_services, service_install_queue)
    #     task_install = install_services(context, docker_handler, service_install_queue)
    #     await asyncio.gather(task_install, task_download)
    #     LOGGER.debug("Install missing or stopped services DONE")
    #     return True
    #
    # return False


async def charger_configuration_docker(path_configuration: pathlib.Path, required_modules: RequiredModules) -> list[dict]:
    configuration = []
    for filename in required_modules.modules:
        path_fichier = pathlib.Path(path_configuration, filename)
        try:
            with open(path_fichier, 'rb') as fichier:
                contenu = json.load(fichier)
            configuration.append(contenu)
        except FileNotFoundError:
            LOGGER.error("Fichier de module manquant : %s" % path_fichier)

    return configuration

async def charger_configuration_webapps(path_configuration: pathlib.Path) -> list:
    configuration = []
    for file in path_configuration.iterdir():
        if file.is_file() and file.name.endswith('.json'):
            filename = file.name
            path_fichier = pathlib.Path(path_configuration, filename)
            with open(path_fichier, 'rb') as fichier:
                contenu = json.load(fichier)
            configuration.append(contenu)

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

                # deps = contenu['dependances']

                configuration.append(contenu)
            except FileNotFoundError:
                LOGGER.error("Fichier de module manquant : %s" % path_fichier)
            except TypeError:
                LOGGER.debug("charger_configuration_application: application %s sans dependances (e.g. pur nginx config)" % filename)

    return configuration


async def install_service(context: InstanceContext, docker_handler: DockerHandlerInterface, command: ServiceInstallCommand):
    service_name = command.status.name
    LOGGER.info("Installing service %s" % service_name)
    image_tag = command.image_tag

    # Copier params, ajouter info service
    params = await get_params_env_service(context, docker_handler)
    params['__nom_application'] = service_name
    params['__certificat_info'] = {'label_prefix': 'pki.%s' % service_name}
    params['__password_info'] = {'label_prefix': 'passwd.%s' % service_name}
    params['__instance_id'] = context.instance_id

    configuration = context.configuration
    mq_hostname = configuration.mq_hostname
    if mq_hostname == 'localhost':
        # Remplacer par mq pour applications (via docker)
        mq_hostname = 'mq'
    params['MQ_HOSTNAME'] = mq_hostname
    params['MQ_PORT'] = configuration.mq_port or '5673'
    try:
        params['__idmg'] = context.idmg
    except ValueNotAvailable:
        pass

    for dep in command.status.dependencies:
        config_service = dep.configuration.copy()
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
            commande_ajouter_labels = DockerCommandes.CommandeEnsureNodeLabels(list_labels)
            await docker_handler.run_command(commande_ajouter_labels)
        except TypeError:
            pass  # Aucune constraint

        # Installer les archives si presentes
        if parser.archives:
            for archive in parser.archives:
                service_name = command.status.name
                web_links = command.status.web_config['web']
                # web_links = command.status.configuration.get('web') or command.status.web_config
                if await asyncio.to_thread(check_archive_stale, context, archive):
                    await asyncio.to_thread(installer_archive, context, service_name, archive, web_links)
                else:
                    # Mettre a jour configuration des liens web
                    LOGGER.info("installer_service Mettre a jour configuration web links pour %s", service_name)
                    sauvegarder_configuration_webapps(context, service_name, web_links)

        # S'assurer d'avoir l'image
        image = parser.image
        if image is not None:
            commande_creer_service = DockerCommandes.CommandeCreerService(
                image_tag, config_parsed, reinstaller=command.reinstall)
            try:
                resultat = await docker_handler.run_command(commande_creer_service)
                return resultat
            except docker.errors.APIError as e:
                if e.status_code == 409:
                    # Already installed (duplicate install command) - OK
                    return {'ok': True}
                else:
                    raise e

        else:
            LOGGER.debug("installer_service() Invoque pour un service sans images : %s", service_name)

    pass

async def get_params_env_service(context: InstanceContext, docker_handler: DockerHandlerInterface) -> dict:
    # Charger configurations
    action_configurations = DockerCommandes.CommandeListerConfigs()
    await docker_handler.run_command(action_configurations)
    docker_configs = await action_configurations.get_resultat()

    action_secrets = DockerCommandes.CommandeListerSecrets()
    await docker_handler.run_command(action_secrets)
    docker_secrets = await action_secrets.get_resultat()

    action_datees = DockerCommandes.CommandeGetConfigurationsDatees()
    await docker_handler.run_command(action_datees)
    config_datees = await action_datees.get_resultat()

    try:
        idmg = context.idmg
    except ValueNotAvailable:
        idmg = None
    params = {
        'HOSTNAME': context.hostname,
        'IDMG': idmg,
        '__secrets': docker_secrets,
        '__configs': docker_configs,
        '__docker_config_datee': config_datees['correspondance'],
    }

    return params


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

    services_speciaux = ['nginx', 'redis', 'mq', 'mongo', 'certissuer', 'midcompte']

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


def list_images(package_configuration: ServiceStatus):
    images = set()
    for dep in package_configuration.dependencies:
        try:
            images.add(dep.image)
        except KeyError:
            pass
    return images


async def pull_images(etat_instance, docker_handler, images: list, app_name: str):
    all_done = True
    for image in images:
        try:
            await get_docker_image_tag(etat_instance, docker_handler, image, pull=False)
        except UnknownImage:
            LOGGER.info('Image %s missing locally, downloading' % image)
            try:
                await get_docker_image_tag(etat_instance, docker_handler, image, pull=True, app_name=app_name)
            except UnknownImage:
                LOGGER.error("Unnkown docker image: %s. Stopping service download/installation" % image)
                all_done = False
    return all_done
