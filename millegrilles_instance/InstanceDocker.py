import asyncio
import logging
import io
import json
import pathlib
import tarfile
import threading

import docker.errors

from asyncio import TaskGroup
from docker.errors import APIError, NotFound
from os import path, unlink, makedirs
from typing import Optional
from base64 import b64decode

from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.Interfaces import DockerHandlerInterface
from millegrilles_instance.MaintenanceApplicationService import service_maintenance, get_service_status
from millegrilles_instance.MaintenanceApplicationWeb import installer_archive, check_archive_stale
from millegrilles_instance.ModulesRequisInstance import RequiredModules
from millegrilles_instance.NginxUtils import ajouter_fichier_configuration

from millegrilles_messages.messages import Constantes
from millegrilles_messages.IpUtils import get_hostnames
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.docker.DockerHandler import DockerHandler, DockerState
from millegrilles_messages.docker import DockerCommandes
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService, WebApplicationConfiguration
from millegrilles_messages.docker.DockerHandler import CommandeDocker
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur

from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.CommandesDocker import CommandeListeTopologie, CommandeExecuterScriptDansService, \
    get_docker_image_tag
from millegrilles_instance.TorHandler import CommandeOnionizeGetHostname, OnionizeNonDisponibleException


# LOGGER = logging.getLogger(__name__)


# class EtatDockerInstanceSync:

    # def __init__(self, context: InstanceContext, docker_handler: DockerHandler):
    #     self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
    #     self.__context = context
    #     self.__docker_handler = docker_handler  # DockerHandler
    #
    #     self.__context.ajouter_listener(self.callback_changement_configuration)
    #     self.__context.generateur_certificats.etat_docker = self
    #
    #     self.__docker_initialise = False

class InstanceDockerHandler(DockerHandlerInterface):

    def __init__(self, context: InstanceContext, docker_state: DockerState):
        super().__init__()
        self.__logger = logging.getLogger(__name__+'.'+self.__class__.__name__)
        self.__context = context
        self.__docker_state = docker_state
        self.__docker_handler = DockerHandler(docker_state)
        self.__verify_configuration_event = threading.Event()
        self.__applications_changed = asyncio.Event()

    async def run(self):
        try:
            async with TaskGroup() as group:
                group.create_task(self.__docker_handler.run())
                group.create_task(self.__application_maintenance())
                group.create_task(self.initialiser_docker())
                group.create_task(self.__configuration_udpate_thread())
                # group.create_task(self.__service_status_pull())
                group.create_task(self.__stop_thread())
        except *Exception:  # Stop on any thread exception
            if self.__context.stopping is False:
                self.__logger.exception("InstanceDockerHandler Unhandled error, closing")
                self.__context.stop()
                raise ForceTerminateExecution()

    async def __stop_thread(self):
        await self.__context.wait()
        # Release threads
        self.__verify_configuration_event.set()
        self.__applications_changed.set()

    async def __configuration_udpate_thread(self):
        while self.__context.stopping is False:
            await asyncio.to_thread(self.__verify_configuration_event.wait, 600)
            if self.__context.stopping:
                return  # Stopping

            self.__verify_configuration_event.clear()

            try:
                await self.verifier_config_instance()
            except asyncio.CancelledError:
                return
            except:
                self.__logger.exception("Error reloading configuration")

    def callback_changement_configuration(self):
        self.__logger.info("callback_changement_configuration - Reload configuration")
        self.__verify_configuration_event.set()

    async def callback_changement_applications(self):
        self.__applications_changed.set()

    async def __service_status_pull(self):
        while self.__context.stopping is False:
            try:
                if self.__context.application_status.required_modules is not None:
                    # Updates the status in context
                    await get_service_status(self.__context, self.__docker_handler, self.__context.application_status.required_modules)
                await self.emettre_presence()
            except (ValueNotAvailable, asyncio.TimeoutError):
                self.__logger.debug("__service_status_pull Not ready, skipping emettre_presence")
            except:
                self.__logger.exception("__service_status_pull Unhandled exception")

            try:
                await self.__context.wait(15)
            except asyncio.TimeoutError:
                pass

    async def __application_maintenance(self):
        while self.__context.stopping is False:
            try:
                await asyncio.wait_for(self.__applications_changed.wait(), 15)
            except asyncio.TimeoutError:
                pass

            if self.__context.stopping:
                return  # Stopping

            self.__logger.debug("__application_maintenance Debut Entretien")
            self.__applications_changed.clear()
            try:
                config_modules = self.__context.application_status.required_modules
                await service_maintenance(self.__context, self.__docker_handler, config_modules)
            except:
                self.__logger.exception("__application_maintenance Error during maintenance")
            self.__logger.debug("Fin Entretien EtatDockerInstanceSync")

        self.__logger.info("__application_maintenance Thread terminee")

    async def emettre_presence(self):
        info_updatee = dict()

        commande = CommandeListeTopologie()
        await self.run_command(commande)
        info_instance = await commande.get_info()
        info_updatee.update(info_instance)

        # Trouver l'addresse .onion (TOR) si disponible
        adresse_onion = await self.verifier_tor()
        if adresse_onion is not None:
            info_updatee['onion'] = adresse_onion

        info_updatee['hostname'] = self.__context.hostname
        info_updatee['domaine'] = self.__context.hostname
        info_updatee['domaines'] = self.__context.hostnames
        info_updatee['fqdn_detecte'] = get_hostnames(fqdn=True)[0]
        info_updatee['ip_detectee'] = self.__context.ip_address
        info_updatee['instance_id'] = self.__context.instance_id
        info_updatee['securite'] = self.__context.securite

        # Ajouter etat systeme
        # info_updatee.update(self.__etat_systeme.etat)

        # Faire la liste des applications installees
        # liste_applications = await self.get_liste_configurations()
        # info_updatee['applications_configurees'] = liste_applications

        # Liste applications web
        path_conf_applications = pathlib.Path(
            self.__context.configuration.path_configuration,
            ConstantesInstance.CONFIG_NOMFICHIER_CONFIGURATION_WEB_APPLICATIONS)
        try:
            with open(path_conf_applications, 'rt') as fichier:
                configuration_webapps = json.load(fichier)

            webapps_list = list()
            # Merge avec la liste d'applications docker
            for nom, app in configuration_webapps.items():
                for links in app['links']:
                    app_info = links.copy()
                    app_info['name'] = nom
                    webapps_list.append(app_info)

            info_updatee['webapps'] = webapps_list

        except (FileNotFoundError, json.JSONDecodeError):
            self.__logger.info('No web application configuration file present/valid')

        niveau_securite = self.__context.securite
        if niveau_securite == Constantes.SECURITE_SECURE:
            # Downgrade 4.secure a niveau 3.protege
            niveau_securite = Constantes.SECURITE_PROTEGE

        producer = await asyncio.wait_for(self.__context.get_producer(), 3)
        await producer.event(info_updatee, Constantes.DOMAINE_INSTANCE,
                             ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE,
                             exchange=niveau_securite)

    async def verifier_config_instance(self):
        instance_id = self.__context.instance_id
        if instance_id is not None:
            await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_ID, instance_id, comparer=True)

        try:
            niveau_securite = self.__context.securite
            if niveau_securite is not None:
                await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_SECURITE, niveau_securite, comparer=True)

            idmg = self.__context.idmg
            if idmg is not None:
                await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_IDMG, idmg, comparer=True)

            certificat_millegrille = self.__context.ca
            if certificat_millegrille is not None:
                await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_PKI_MILLEGRILLE, certificat_millegrille.certificat_pem)
        except ValueNotAvailable:
            self.__logger.info("Securite, Idmg, certificats non disponibles. Non configures sous docker.")

        await self.verifier_certificat_web()

    async def sauvegarder_config(self, label: str, valeur: str, comparer=False):
        commande = DockerCommandes.CommandeGetConfiguration(label)
        try:
            await self.__docker_handler.run_command(commande)
            valeur_docker = await commande.get_data()
            self.__logger.debug("Docker %s : %s" % (label, valeur_docker))
            if comparer is True and valeur_docker != valeur:
                raise Exception("Erreur configuration, %s mismatch" % label)
        except NotFound:
            self.__logger.debug("Docker instance NotFound")
            commande_ajouter = DockerCommandes.CommandeAjouterConfiguration(label, valeur)
            await self.__docker_handler.run_command(commande_ajouter)

    async def verifier_certificat_web(self):
        """
        Verifie et met a jour le certificat web au besoin
        :return:
        """
        self.__logger.debug("verifier_certificat_web()")

        path_secrets = self.__context.configuration.path_secrets

        nom_certificat = 'pki.web.cert'
        nom_cle = 'pki.web.key'
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)

        clecert_web = CleCertificat.from_files(path_cle, path_certificat)
        await self.assurer_clecertificat('web', clecert_web)

    async def assurer_clecertificat(self, nom_module: str, clecertificat: CleCertificat, combiner=False):
        """
        Commande pour s'assurer qu'un certificat et une cle sont insere dans docker.
        :param label:
        :param clecert:
        :return:
        """
        enveloppe = clecertificat.enveloppe
        if enveloppe.is_root_ca is True:
            # Certificat self-signed, s'assurer que la date est vieille
            date_debut = '20000101000000'
        else:
            date_debut = enveloppe.not_valid_before.strftime('%Y%m%d%H%M%S')
        label_certificat = 'pki.%s.cert.%s' % (nom_module, date_debut)
        label_cle = 'pki.%s.key.%s' % (nom_module, date_debut)
        pem_certificat = '\n'.join(enveloppe.chaine_pem())
        pem_cle = clecertificat.private_key_bytes().decode('utf-8')
        if combiner is True:
            pem_cle = '\n'.join([pem_cle, pem_certificat])

        labels = {
            'certificat': 'true',
            'label_prefix': 'pki.%s' % nom_module,
            'date': date_debut,
        }

        commande_ajouter_cert = DockerCommandes.CommandeAjouterConfiguration(label_certificat, pem_certificat, labels=labels)
        ajoute = False
        try:
            await self.__docker_handler.run_command(commande_ajouter_cert)
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Config existe deja
            else:
                raise apie

        commande_ajouter_cle = DockerCommandes.CommandeAjouterSecret(label_cle, pem_cle, labels=labels)
        try:
            await self.__docker_handler.run_command(commande_ajouter_cle)
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Secret existe deja
            else:
                raise apie

        if ajoute:
            self.__logger.debug("Nouveau certificat, reconfigurer module %s" % nom_module)

    async def get_configurations_datees(self):
        commande = DockerCommandes.CommandeGetConfigurationsDatees()
        return await self.__docker_handler.run_command(commande)

    async def ajouter_password(self, nom_module: str, date: str, value: str):
        prefixe = 'passwd.%s' % nom_module
        label_password = 'passwd.%s.%s' % (nom_module, date)

        labels = {
            'password': 'true',
            'label_prefix': prefixe,
            'date': date,
        }
        commande_ajouter_cle = DockerCommandes.CommandeAjouterSecret(label_password, value, labels=labels)

        ajoute = False
        try:
            await self.__docker_handler.run_command(commande_ajouter_cle)
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Secret existe deja
            else:
                raise apie

        if ajoute:
            self.__logger.debug("Nouveau password, reconfigurer module %s" % nom_module)

    async def initialiser_docker(self):
        try:
            commande_initialiser_swarm = DockerCommandes.CommandeCreerSwarm()
            try:
                await self.__docker_handler.run_command(commande_initialiser_swarm)
            except APIError as e:
                if e.status_code == 503:
                    pass  # OK, deja initialise
                else:
                    raise e

            commande_initialiser_network = DockerCommandes.CommandeCreerNetworkOverlay('millegrille_net')
            await self.__docker_handler.run_command(commande_initialiser_network)
        except asyncio.CancelledError as e:
            self.__logger.error("initialiser_docker Cancelled: %s" % str(e))
        except:
            self.__logger.exception("initialiser_docker Error initializing docker swarm/networking - quitting")
            self.__context.stop()
            raise ForceTerminateExecution()

    async def entretien_services(self, config_modules: RequiredModules):
        changes = await service_maintenance(self.__context, self.__docker_handler, config_modules)
        if changes:
            await self.redemarrer_nginx("entretien_services: Services updated")

    async def get_params_env_service(self) -> dict:
        # Charger configurations
        action_configurations = DockerCommandes.CommandeListerConfigs()
        docker_configs = await self.__docker_handler.run_command(action_configurations)

        action_secrets = DockerCommandes.CommandeListerSecrets()
        docker_secrets = await self.__docker_handler.run_command(action_secrets)

        action_datees = DockerCommandes.CommandeGetConfigurationsDatees()
        config_datees = await self.__docker_handler.run_command(action_datees)

        params = {
            'HOSTNAME': self.__context.hostname,
            'IDMG': self.__context.idmg,
            '__secrets': docker_secrets,
            '__configs': docker_configs,
            '__docker_config_datee': config_datees['correspondance'],
        }

        return params

    async def installer_service(self, nom_service: str, configuration: dict, params: dict, reinstaller=False):
        # Copier params, ajouter info service
        params = params.copy()
        params['__nom_application'] = nom_service
        params['__certificat_info'] = {'label_prefix': 'pki.%s' % nom_service}
        params['__password_info'] = {'label_prefix': 'passwd.%s' % nom_service}
        params['__instance_id'] = self.__context.instance_id

        configuration = self.__context.configuration
        mq_hostname = configuration.mq_hostname
        if mq_hostname == 'localhost':
            # Remplacer par mq pour applications (via docker)
            mq_hostname = 'mq'
        params['MQ_HOSTNAME'] = mq_hostname
        params['MQ_PORT'] = configuration.mq_port or '5673'
        if configuration.idmg is not None:
            params['__idmg'] = configuration.idmg

        config_service = configuration.copy()
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
            await self.__docker_handler.run_command(commande_ajouter_labels)
        except TypeError:
            pass  # Aucune constraint

        # Installer les archives si presentes
        if parser.archives:
            for archive in parser.archives:
                if await asyncio.to_thread(check_archive_stale, self.__context, archive):
                    await asyncio.to_thread(installer_archive, self.__context, archive)

        # S'assurer d'avoir l'image
        image = parser.image
        if image is not None:
            # commande_image = DockerCommandes.CommandeGetImage(image, pull=True, aio=True)
            # self.__docker_handler.ajouter_commande(commande_image)
            # image_info = await commande_image.get_resultat()
            #
            # image_tag = image_info['tags'][0]
            image_tag = await get_docker_image_tag(self.__context, self.__docker_handler, image, pull=True, app_name=image)

            commande_creer_service = DockerCommandes.CommandeCreerService(image_tag, config_parsed, reinstaller=reinstaller)
            return await self.__docker_handler.run_command(commande_creer_service)
        else:
            self.__logger.warning("installer_service() Invoque pour un service sans images : %s", nom_service)

    async def maj_configuration_datee_service(self, nom_service: str, configuration: dict):

        params = await self.get_params_env_service()
        params['__nom_application'] = nom_service

        # Copier params, ajouter info service
        parser = ConfigurationService(configuration, params)
        parser.parse()
        config_parsed = parser.generer_docker_config()

        config_maj = dict()
        try:
            config_maj['configs'] = config_parsed['configs']
        except KeyError:
            pass
        try:
            config_maj['secrets'] = config_parsed['secrets']
        except KeyError:
            pass

        commande_maj = DockerCommandes.CommandeMajService(nom_service, config_maj)
        self.__docker_handler.ajouter_commande(commande_maj)
        await commande_maj.attendre()

    async def redemarrer_nginx(self, reason: Optional[str] = None):
        self.__logger.info("Redemarrer nginx pour charger configuration maj (reason: %s)" % reason)
        try:
            await self.__docker_handler.run_command(DockerCommandes.CommandeReloadNginx())
        except APIError as e:
            if e.status_code == 404:
                pass  # Nginx n'est pas encore installe
            else:
                raise e

    async def nginx_installation_cleanup(self):
        """
        Ensure nginxinstall and other installation services are removed.
        """
        action_remove = DockerCommandes.CommandeSupprimerService("nginxinstall")
        try:
            await self.run_command(action_remove)
        except docker.errors.NotFound:
            pass  # Ok, already removed

    # def ajouter_commande(self, commande: CommandeDocker):
    #     self.__docker_handler.ajouter_commande(commande)

    async def run_command(self, command: CommandeDocker):
        result = await self.__docker_handler.run_command(command)
        try:
            return await command.get_resultat()
        except AttributeError:
            return result

    async def installer_application(self, context: InstanceContext, configuration: dict, reinstaller=False):
        nom_application = configuration['nom']
        nginx = configuration.get('nginx')
        dependances = configuration['dependances']

        commande_config_datees = DockerCommandes.CommandeGetConfigurationsDatees()
        await self.__docker_handler.run_command(commande_config_datees)

        commande_config_services = DockerCommandes.CommandeListerServices(filters={'name': nom_application})
        resultat_config_datees = await self.__docker_handler.run_command(commande_config_services)
        correspondance = resultat_config_datees['correspondance']
        service_existant = await commande_config_services.get_liste()

        if len(service_existant) > 0 and reinstaller is False:
            return {'ok': False, 'err': 'Service deja installe'}

        # Generer certificats/passwords
        await self.generer_valeurs(correspondance, dependances, nom_application)

        # Copier scripts
        try:
            scripts_base64 = configuration['scripts_content']
        except KeyError:
            pass
        else:
            path_scripts = '/var/opt/millegrilles/scripts'
            makedirs(path_scripts, mode=0o755, exist_ok=True)
            path_scripts_app = path.join(path_scripts, nom_application)
            makedirs(path_scripts_app, mode=0o755, exist_ok=True)

            tar_scripts_bytes = b64decode(scripts_base64)
            server_file_obj = io.BytesIO(tar_scripts_bytes)
            tar_content = tarfile.open(fileobj=server_file_obj)
            tar_content.extractall(path_scripts_app)

        rafraichir_nginx = False
        if nginx is not None:
            self.__logger.debug("Conserver information nginx")
            try:
                conf_dict = nginx['conf']
            except KeyError:
                pass
            else:
                params = {
                    'appname': nom_application,
                }
                for nom_fichier, contenu in conf_dict.items():
                    path_nginx = self.__context.configuration.path_nginx
                    path_nginx_module = pathlib.Path(path_nginx, 'modules')
                    ajouter_fichier_configuration(self.__context, path_nginx_module, nom_fichier, contenu, params)
                rafraichir_nginx = True

        # Deployer services
        if dependances is not None:
            for dep in dependances:
                nom_module = dep['name']

                # Installer web apps en premier
                if dep.get('archives') is not None:
                    try:
                        web_links = configuration['web']
                    except KeyError:
                        web_links = dict()
                    # Installer webapp
                    for archive in dep['archives']:
                        app_name = dep['name']
                        config = WebApplicationConfiguration(archive)
                        if await asyncio.to_thread(check_archive_stale, self.__context, config):
                            await asyncio.to_thread(installer_archive, self.__context, app_name, config,
                                                    web_links)

                if dep.get('image') is not None:
                    params = await self.get_params_env_service()
                    params['__nom_application'] = nom_application
                    resultat_installation = await self.installer_service(nom_module, dep, params, reinstaller)

                    try:
                        scripts_module = configuration['scripts_installation'][nom_module]
                    except KeyError:
                        pass
                    else:
                        path_rep = configuration.get('scripts_path') or '/var/opt/millegrilles_scripts'
                        path_scripts = path.join(path_rep, nom_application)
                        scripts_module_path = [path.join(path_scripts, s) for s in scripts_module]
                        await self.executer_scripts_container(nom_module, scripts_module_path)

        if rafraichir_nginx is True:
            await self.redemarrer_nginx("Application %s installee" % nom_application)

        return {'ok': True}

    async def executer_scripts_container(self, nom_container: str, path_scripts: list, codes_ok=frozenset([0])):
        """
        Execute des scripts deja presents dans le container.

        :param nom_container: Nom du service/container (filters: name)
        :param path_scripts: Path du repertoire avec les scripts
        :param codes_ok: Liste de codes de retour qui sont valides
        :return:
        """
        for path_script in path_scripts:
            self.__logger.debug("Executer script %s dans service/containers %s" % (path_script, nom_container))
            commande = CommandeExecuterScriptDansService(nom_container, path_script)
            self.__docker_handler.ajouter_commande(commande)

            resultat = await commande.get_resultat()

            code = resultat['code']
            output = resultat['output']

            if code not in codes_ok:
                self.__logger.error("Resultat execution %s = %s\n%s" % (path_script, code, output))
                raise Exception("Erreur execution script installation %s: %s" % (path_script, code))
            else:
                self.__logger.info("Resultat execution %s\n%s" % (code, output))

    async def generer_valeurs(self, correspondance, dependances, nom_application):
        if dependances is None:
            return  # Rien a faire

        for dep in dependances:
            try:
                certificat = dep['certificat']

                # Verifier si certificat/cle existent deja
                try:
                    current = correspondance['pki.%s' % nom_application]['current']
                    current['key']
                    current['cert']
                except KeyError:
                    self.__logger.info("generer_valeurs Generer certificat/secret pour %s" % nom_application)
                    raise NotImplementedError('todo')
                    # clecertificat = await self.__context.generateur_certificats.demander_signature(nom_application, certificat)
                    # if clecertificat is None:
                    #     raise Exception("generer_valeurs Erreur creation certificat %s" % nom_application)
                    # # Importer toutes les cles dans docker
                    # if self.__docker_initialise is True and clecertificat is not None:
                    #     await self.assurer_clecertificat(nom_application, clecertificat)

            except KeyError:
                pass

            try:
                generateur = dep['generateur']
                for passwd_gen in generateur:
                    if isinstance(passwd_gen, str):
                        label = passwd_gen
                        type_password = 'password'
                    else:
                        label = passwd_gen['label']
                        type_password = passwd_gen['type']
                    try:
                        current = correspondance['passwd.%s' % label]['current']
                        current[type_password]
                    except KeyError:
                        self.__logger.info("Generer password %s pour %s" % (label, nom_application))
                        await self.__etat_instance.generer_passwords(self, [passwd_gen])

            except KeyError:
                pass

    async def demarrer_application(self, nom_application: str):
        commande_image = DockerCommandes.CommandeDemarrerService(nom_application, replicas=1)
        resultat = await self.__docker_handler.run_command(commande_image)
        return {'ok': resultat}

    async def arreter_application(self, nom_application: str):
        commande_image = DockerCommandes.CommandeArreterService(nom_application)
        resultat = await self.__docker_handler.run_command(commande_image)
        return {'ok': resultat}

    async def supprimer_application(self, nom_application: str):
        commande_image = DockerCommandes.CommandeSupprimerService(nom_application)
        try:
            resultat = await self.__docker_handler.run_command(commande_image)
        except APIError as apie:
            if apie.status_code == 404:
                resultat = True  # Ok, deja supprime
            else:
                raise apie

        path_docker_apps = self.__context.configuration.path_docker_apps
        fichier_config = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        try:
            unlink(fichier_config)
        except FileNotFoundError:
            pass

        return {'ok': resultat}

    async def verifier_tor(self):
        commande = CommandeOnionizeGetHostname()
        try:
            await self.__docker_handler.run_command(commande)
            hostname = await commande.get_resultat()
        except OnionizeNonDisponibleException:
            self.__logger.debug("Service onionize non demarre")
            return

        self.__logger.debug("Adresse onionize : %s" % hostname)
        return hostname

