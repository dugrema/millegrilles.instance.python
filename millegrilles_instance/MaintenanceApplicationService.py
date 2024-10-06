# Docker service maintenance
import asyncio
import logging
import pathlib
import json

from typing import Optional

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

# def m():
#     services_with_images = dict()
#     for service_key, service_data in services.items():
#         try:
#             _ = service_data['archives']
#         except KeyError:
#             # No archives, keep the service
#             services_with_images[service_key] = service_data
#         else:
#             try:
#                 _ = service_data['image']
#                 services_with_images[service_key] = service_data
#             except KeyError:
#                 pass  # No images, check separately
#
#     commande_liste_services = DockerCommandes.CommandeListerServices(aio=True)
#     self.__docker_handler.ajouter_commande(commande_liste_services)
#     liste_services_docker = await commande_liste_services.get_liste()
#
#     commande_config_currente = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
#     self.__docker_handler.ajouter_commande(commande_config_currente)
#     liste_config_datee = await commande_config_currente.get_resultat()
#
#     # Determiner s'il y a des services manquants
#     nom_services_a_installer = set(services_with_images.keys())
#
#     # Services avec certificats/secrets/passwd a remplacer
#     services_a_reconfigurer = set()
#
#     # Utiliser docker pour determiner la liste de services a reconfigurer
#     liste_services_docker = trier_services(liste_services_docker)
#     for s in liste_services_docker:
#         name = s.name
#         attrs = s.attrs
#         spec = attrs['Spec']
#         mode = spec['Mode']
#         try:
#             replicated = mode['Replicated']
#             replicas = replicated['Replicas']
#         except KeyError:
#             self.__logger.debug("Service %s configure sans replicas, on l'ignore" % name)
#             replicas = None
#
#         try:
#             nom_services_a_installer.remove(name)
#         except KeyError:
#             # Ce n'est pas un module de base - verifier si c'est une application gere par l'instance
#             labels = spec['Labels']
#             if labels.get('application') is None:
#                 replicas = None
#
#         service_state_ok = False
#         if replicas is not None and replicas > 0:
#             # Verifier si le service est actif
#             tasks = s.tasks(filters={'desired-state': 'running'})
#             for task in tasks:
#                 try:
#                     status = task['Status']
#                     state = status['State']
#                     if state in ['running', 'preparing']:
#                         service_state_ok = True
#                 except KeyError:
#                     pass
#         else:
#             service_state_ok = True
#
#         if service_state_ok is False:
#             self.__logger.info("Service %s arrete, on le redemarre" % name)
#             s.update(force_update=True)
#             action_configurations = DockerCommandes.CommandeRedemarrerService(nom_service=name, aio=True)
#             self.__docker_handler.ajouter_commande(action_configurations)
#             await action_configurations.attendre()
#         else:
#             # Verifier si l'etat de la configuration est courant
#             container_spec = spec['TaskTemplate']['ContainerSpec']
#             try:
#                 container_secrets = container_spec['Secrets']
#             except KeyError:
#                 container_secrets = None
#             try:
#                 container_config = container_spec['Configs']
#             except KeyError:
#                 container_config = None
#
#             config_ok = verifier_config_current(liste_config_datee['correspondance'], container_config,
#                                                 container_secrets)
#             if config_ok is False:
#                 self.__logger.info("Configs/secrets out of date, regenerer config %s" % s.name)
#                 services_a_reconfigurer.add(s.name)
#                 config_service = services[s.name]
#                 await self.maj_configuration_datee_service(s.name, config_service)
#
#     # Pour tous les services, verifier s'ils sont bases sur des archives a installer sans docker
#     for nom_service in set(services.keys()):
#         config_service = services[nom_service]
#         archives = config_service.get('archives')
#         if archives:
#             try:
#                 with open(FICHIER_ARCHIVES_APP, 'rt') as fichier:
#                     config_archives = json.load(fichier)
#             except (FileNotFoundError, json.JSONDecodeError):
#                 nom_services_a_installer.add(nom_service)
#                 continue  # Aucun fichier de configuration, aucunes archives d'installees
#
#             try:
#                 for archive in archives:
#                     archive_location = archive['location']
#                     archive_digest = archive['digest']
#                     archive_configuration = config_archives[archive_location]
#                     if archive_configuration['digest'] != archive_digest:
#                         nom_services_a_installer.add(nom_service)
#                         break  # Il faut reinstaller l'application
#                 else:
#                     # Toutes les archives sont installees et avec le meme digest
#                     pass
#
#             except KeyError:
#                 # Il manque un element (probablement location). Reinstaller.
#                 nom_services_a_installer.add(nom_service)
#
#     if len(nom_services_a_installer) > 0:
#         self.__logger.debug("Services manquants dans docker : %s" % nom_services_a_installer)
#
#         params = await self.get_params_env_service()
#
#         for nom_service in nom_services_a_installer:
#             config_service = services[nom_service]
#             await self.installer_service(nom_service, config_service, params)
#
#             try:
#                 web_config = config_service['web']
#                 sauvegarder_configuration_webapps(nom_service, web_config, self.__etat_instance)
#             except KeyError:
#                 pass  # No web configuration


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
                await asyncio.to_thread(installer_archive, etat_instance, archive)

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
