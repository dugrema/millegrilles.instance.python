import asyncio
import logging
import tarfile
import io

from asyncio import Event, TimeoutError
from docker.errors import APIError, NotFound
from os import path, unlink, makedirs
from typing import Optional
from base64 import b64decode

from millegrilles_messages.docker.DockerHandler import DockerHandler
from millegrilles_messages.docker import DockerCommandes

from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService
from millegrilles_messages.docker.DockerHandler import CommandeDocker
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur

from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_instance.CommandesDocker import CommandeListeTopologie, CommandeExecuterScriptDansService, \
    CommandeGetServicesBackup
from millegrilles_instance.TorHandler import CommandeOnionizeGetHostname, OnionizeNonDisponibleException


class EtatDockerInstanceSync:

    def __init__(self, etat_instance, docker_handler: DockerHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__docker_handler = docker_handler  # DockerHandler

        self.__etat_instance.ajouter_listener(self.callback_changement_configuration)

        self.__docker_initialise = False

    async def callback_changement_configuration(self, etat_instance):
        self.__logger.info("callback_changement_configuration - Reload configuration")
        await self.verifier_config_instance()

    async def entretien(self, stop_event: Event):
        while stop_event.is_set() is False:

            if self.__docker_initialise is False:
                await self.initialiser_docker()

            if self.__docker_initialise is True:
                self.__logger.debug("Debut Entretien EtatDockerInstanceSync")
                await self.verifier_config_instance()
                self.__logger.debug("Fin Entretien EtatDockerInstanceSync")

            try:
                await asyncio.wait_for(stop_event.wait(), 60)
            except TimeoutError:
                pass

        self.__logger.info("Thread Entretien InstanceDocker terminee")

    async def emettre_presence(self, producer: MessageProducerFormatteur, info: Optional[dict] = None):
        self.__logger.info("Emettre presence")
        if info is not None:
            info_updatee = info.copy()
        else:
            info_updatee = dict()

        commande = CommandeListeTopologie()
        self.ajouter_commande(commande)
        info_instance = await commande.get_info()
        info_updatee.update(info_instance)

        # Trouver l'addresse .onion (TOR) si disponible
        adresse_onion = await self.verifier_tor()
        if adresse_onion is not None:
            info_updatee['onion'] = adresse_onion

        # # Faire la liste des applications installees
        # liste_applications = await self.__etat_instance.get_liste_configurations()
        # info_updatee['applications_configurees'] = liste_applications

        await self.__etat_instance.emettre_presence(producer, info_updatee)

    async def verifier_config_instance(self):
        instance_id = self.__etat_instance.instance_id
        if instance_id is not None:
            await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_ID, instance_id, comparer=True)

        niveau_securite = self.__etat_instance.niveau_securite
        if niveau_securite is not None:
            await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_SECURITE, niveau_securite, comparer=True)

        idmg = self.__etat_instance.idmg
        if idmg is not None:
            await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_INSTANCE_IDMG, idmg, comparer=True)

        certificat_millegrille = self.__etat_instance.certificat_millegrille
        if certificat_millegrille is not None:
            await self.sauvegarder_config(ConstantesInstance.DOCKER_CONFIG_PKI_MILLEGRILLE, certificat_millegrille.certificat_pem)

        await self.verifier_certificat_web()

    async def sauvegarder_config(self, label: str, valeur: str, comparer=False):
        commande = DockerCommandes.CommandeGetConfiguration(label, aio=True)
        self.__docker_handler.ajouter_commande(commande)
        try:
            valeur_docker = await commande.get_data()
            self.__logger.debug("Docker %s : %s" % (label, valeur_docker))
            if comparer is True and valeur_docker != valeur:
                raise Exception("Erreur configuration, %s mismatch" % label)
        except NotFound:
            self.__logger.debug("Docker instance NotFound")
            commande_ajouter = DockerCommandes.CommandeAjouterConfiguration(label, valeur, aio=True)
            self.__docker_handler.ajouter_commande(commande_ajouter)
            await commande_ajouter.attendre()

    async def verifier_certificat_web(self):
        """
        Verifie et met a jour le certificat web au besoin
        :return:
        """
        self.__logger.debug("verifier_certificat_web()")

        path_secrets = self.__etat_instance.configuration.path_secrets

        nom_certificat = 'pki.web.cert'
        nom_cle = 'pki.web.cle'
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

        commande_ajouter_cert = DockerCommandes.CommandeAjouterConfiguration(label_certificat, pem_certificat, labels=labels, aio=True)
        self.__docker_handler.ajouter_commande(commande_ajouter_cert)
        ajoute = False
        try:
            await commande_ajouter_cert.attendre()
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Config existe deja
            else:
                raise apie

        commande_ajouter_cle = DockerCommandes.CommandeAjouterSecret(label_cle, pem_cle, labels=labels, aio=True)
        self.__docker_handler.ajouter_commande(commande_ajouter_cle)
        try:
            await commande_ajouter_cle.attendre()
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Secret existe deja
            else:
                raise apie

        if ajoute:
            self.__logger.debug("Nouveau certificat, reconfigurer module %s" % nom_module)

    async def get_configurations_datees(self):
        commande = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
        self.__docker_handler.ajouter_commande(commande)
        return await commande.get_resultat()

    async def ajouter_password(self, nom_module: str, date: str, value: str):
        prefixe = 'passwd.%s' % nom_module
        label_password = 'passwd.%s.%s' % (nom_module, date)

        labels = {
            'password': 'true',
            'label_prefix': prefixe,
            'date': date,
        }
        commande_ajouter_cle = DockerCommandes.CommandeAjouterSecret(label_password, value, labels=labels, aio=True)

        self.__docker_handler.ajouter_commande(commande_ajouter_cle)
        ajoute = False
        try:
            await commande_ajouter_cle.attendre()
            ajoute = True
        except APIError as apie:
            if apie.status_code == 409:
                pass  # Secret existe deja
            else:
                raise apie

        if ajoute:
            self.__logger.debug("Nouveau password, reconfigurer module %s" % nom_module)

    async def initialiser_docker(self):
        commande_initialiser_swarm = DockerCommandes.CommandeCreerSwarm(aio=True)
        self.__docker_handler.ajouter_commande(commande_initialiser_swarm)
        try:
            await commande_initialiser_swarm.attendre()
        except APIError as e:
            if e.status_code == 503:
                pass  # OK, deja initialise
            else:
                raise e

        commande_initialiser_network = DockerCommandes.CommandeCreerNetworkOverlay('millegrille_net', aio=True)
        self.__docker_handler.ajouter_commande(commande_initialiser_network)
        await commande_initialiser_network.attendre()

        self.__docker_initialise = True

    async def entretien_services(self, services: dict):
        commande_liste_services = DockerCommandes.CommandeListerServices(aio=True)
        self.__docker_handler.ajouter_commande(commande_liste_services)
        liste_services_docker = await commande_liste_services.get_liste()

        commande_config_currente = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
        self.__docker_handler.ajouter_commande(commande_config_currente)
        liste_config_datee = await commande_config_currente.get_resultat()

        # Determiner s'il y a des services manquants
        nom_services_a_installer = set(services.keys())
        for nom_service, config_service in services.items():
            if config_service.get('image') is not None:
                nom_services_a_installer.add(nom_service)

        # Services avec certificats/secrets/passwd a remplacer
        services_a_reconfigurer = set()

        liste_services_docker = trier_services(liste_services_docker)

        for s in liste_services_docker:
            name = s.name
            attrs = s.attrs
            spec = attrs['Spec']
            mode = spec['Mode']
            try:
                replicated = mode['Replicated']
                replicas = replicated['Replicas']
            except KeyError:
                self.__logger.debug("Service %s configure sans replicas, on l'ignore" % name)
                replicas = None

            try:
                nom_services_a_installer.remove(name)
            except KeyError:
                # Ce n'est pas un module de base - verifier si c'est une application gere par l'instance
                labels = spec['Labels']
                if labels.get('application') is None:
                    replicas = None

            service_state_ok = False
            if replicas is not None and replicas > 0:
                # Verifier si le service est actif
                tasks = s.tasks(filters={'desired-state': 'running'})
                for task in tasks:
                    try:
                        status = task['Status']
                        state = status['State']
                        if state in ['running', 'preparing']:
                            service_state_ok = True
                    except KeyError:
                        pass
            else:
                service_state_ok = True

            if service_state_ok is False:
                self.__logger.info("Service %s arrete, on le redemarre" % name)
                s.update(force_update=True)
                action_configurations = DockerCommandes.CommandeRedemarrerService(nom_service=name, aio=True)
                self.__docker_handler.ajouter_commande(action_configurations)
                await action_configurations.attendre()
            else:
                # Verifier si l'etat de la configuration est courant
                container_spec = spec['TaskTemplate']['ContainerSpec']
                try:
                    container_secrets = container_spec['Secrets']
                except KeyError:
                    container_secrets = None
                try:
                    container_config = container_spec['Configs']
                except KeyError:
                    container_config = None

                config_ok = verifier_config_current(liste_config_datee['correspondance'], container_config, container_secrets)
                if config_ok is False:
                    self.__logger.info("Configs/secrets out of date, regenerer config %s" % s.name)
                    services_a_reconfigurer.add(s.name)
                    config_service = services[s.name]
                    await self.maj_configuration_datee_service(s.name, config_service)

        if len(nom_services_a_installer) > 0:
            self.__logger.debug("Services manquants dans docker : %s" % nom_services_a_installer)

            params = await self.get_params_env_service()

            for nom_service in nom_services_a_installer:
                config_service = services[nom_service]
                await self.installer_service(nom_service, config_service, params)

    async def get_params_env_service(self) -> dict:
        # Charger configurations
        action_configurations = DockerCommandes.CommandeListerConfigs(aio=True)
        self.__docker_handler.ajouter_commande(action_configurations)
        docker_configs = await action_configurations.get_resultat()

        action_secrets = DockerCommandes.CommandeListerSecrets(aio=True)
        self.__docker_handler.ajouter_commande(action_secrets)
        docker_secrets = await action_secrets.get_resultat()

        action_datees = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
        self.__docker_handler.ajouter_commande(action_datees)
        config_datees = await action_datees.get_resultat()

        params = {
            'HOSTNAME': self.__etat_instance.hostname,
            'IDMG': self.__etat_instance.idmg,
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
        params['__instance_id'] = self.__etat_instance.instance_id

        mq_hostname = self.__etat_instance.mq_hostname
        if mq_hostname == 'localhost':
            # Remplacer par mq pour applications (via docker)
            mq_hostname = 'mq'
        params['MQ_HOSTNAME'] = mq_hostname
        params['MQ_PORT'] = self.__etat_instance.mq_port or '5673'
        if self.__etat_instance.idmg is not None:
            params['__idmg'] = self.__etat_instance.idmg

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
            commande_ajouter_labels = DockerCommandes.CommandeEnsureNodeLabels(list_labels, aio=True)
            self.__docker_handler.ajouter_commande(commande_ajouter_labels)
            await commande_ajouter_labels.attendre()
        except TypeError:
            pass  # Aucune constraint

        # S'assurer d'avoir l'image
        image = parser.image
        if image is not None:
            commande_image = DockerCommandes.CommandeGetImage(image, pull=True, aio=True)
            self.__docker_handler.ajouter_commande(commande_image)
            image_info = await commande_image.get_resultat()

            image_tag = image_info['tags'][0]
            commande_creer_service = DockerCommandes.CommandeCreerService(image_tag, config_parsed, reinstaller=reinstaller, aio=True)
            self.__docker_handler.ajouter_commande(commande_creer_service)
            resultat = await commande_creer_service.get_resultat()

            return resultat
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

    async def redemarrer_nginx(self):
        self.__logger.info("Redemarrer nginx pour charger configuration maj")
        commande = DockerCommandes.CommandeRedemarrerService('nginx', aio=True)
        self.__docker_handler.ajouter_commande(commande)
        try:
            await commande.attendre()
        except APIError as e:
            if e.status_code == 404:
                pass  # Nginx n'est pas encore installe
            else:
                raise e

    def ajouter_commande(self, commande: CommandeDocker):
        self.__docker_handler.ajouter_commande(commande)

    async def installer_application(self, producer: MessageProducerFormatteur, configuration: dict, reinstaller=False):
        nom_application = configuration['nom']
        nginx = configuration.get('nginx')
        dependances = configuration['dependances']

        commande_config_datees = DockerCommandes.CommandeGetConfigurationsDatees(aio=True)
        self.__docker_handler.ajouter_commande(commande_config_datees)
        commande_config_services = DockerCommandes.CommandeListerServices(filters={'name': nom_application}, aio=True)
        self.__docker_handler.ajouter_commande(commande_config_services)

        resultat_config_datees = await commande_config_datees.get_resultat()
        correspondance = resultat_config_datees['correspondance']
        service_existant = await commande_config_services.get_liste()

        if len(service_existant) > 0 and reinstaller is False:
            return {'ok': False, 'err': 'Service deja installe'}

        # Generer certificats/passwords
        await self.generer_valeurs(correspondance, dependances, nom_application, producer)

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

        redemarrer_nginx = False
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
                    self.__etat_instance.entretien_nginx.ajouter_fichier_configuration(nom_fichier, contenu, params)
                redemarrer_nginx = True

        # Deployer services
        for dep in dependances:
            nom_module = dep['name']
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

        if redemarrer_nginx is True:
            await self.redemarrer_nginx()

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

    async def generer_valeurs(self, correspondance, dependances, nom_application, producer):
        for dep in dependances:
            try:
                certificat = dep['certificat']

                # Verifier si certificat/cle existent deja
                try:
                    current = correspondance['pki.%s' % nom_application]['current']
                    current['key']
                    current['cert']
                except KeyError:
                    self.__logger.info("Generer certificat/secret pour %s" % nom_application)
                    if self.__etat_instance.niveau_securite in [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_SECURE]:
                        clecertificat = await self.__etat_instance.generer_certificats_module(producer, self, nom_application, certificat)
                    else:
                        clecertificat = await self.__etat_instance.generer_certificats_module_satellite(
                            producer, self, nom_application, certificat)
                    # Importer toutes les cles dans docker
                    if self.__docker_initialise is True and clecertificat is not None:
                        await self.assurer_clecertificat(nom_application, clecertificat)

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
        commande_image = DockerCommandes.CommandeDemarrerService(nom_application, replicas=1, aio=True)
        self.__docker_handler.ajouter_commande(commande_image)
        resultat = await commande_image.get_resultat()
        return {'ok': resultat}

    async def arreter_application(self, nom_application: str):
        commande_image = DockerCommandes.CommandeArreterService(nom_application, aio=True)
        self.__docker_handler.ajouter_commande(commande_image)
        resultat = await commande_image.get_resultat()
        return {'ok': resultat}

    async def supprimer_application(self, nom_application: str):
        commande_image = DockerCommandes.CommandeSupprimerService(nom_application, aio=True)
        self.__docker_handler.ajouter_commande(commande_image)
        try:
            resultat = await commande_image.get_resultat()
        except APIError as apie:
            if apie.status_code == 404:
                resultat = True  # Ok, deja supprime
            else:
                raise apie

        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        fichier_config = path.join(path_docker_apps, 'app.%s.json' % nom_application)
        try:
            unlink(fichier_config)
        except FileNotFoundError:
            pass

        return {'ok': resultat}

    async def backup_applications(self):
        """
        Execute les scripts de backup de tous les containers.
        :return:
        """
        commande_services = CommandeGetServicesBackup()
        self.__docker_handler.ajouter_commande(commande_services)
        services_backup = await commande_services.get_services()

        for nom_service, values in services_backup.items():
            try:
                labels = values['labels']
                backup_scripts = labels['backup_scripts']
                backup_scripts = backup_scripts.split(',')
            except KeyError:  # Ne devrait pas arriver, backup_scripts est le filter dans services.list()
                continue

            path_scripts = labels.get('scripts_path') or path.join('/var/opt/millegrilles_scripts', nom_service)

            for script in backup_scripts:
                path_script = path.join(path_scripts, script)
                commande_backup = CommandeExecuterScriptDansService(nom_service, path_script)
                self.__docker_handler.ajouter_commande(commande_backup)
                resultat = await commande_backup.get_resultat()
                code = resultat['code']
                output = resultat['output']
                if code != 0:
                    self.__logger.warning("Resultat backup %s = %s\n%s" % (path_script, code, output))
                else:
                    self.__logger.info("Resultat backup %s = %s" % (path_script, code))

        # Executer backup pour chiffrer archives
        image_backup = self.__etat_instance.configuration.docker_image_backup

        env_backup = {
            'CA_PEM': '/var/opt/millegrilles/configuration/pki.millegrille.cert',
            'CERT_PEM': '/var/opt/millegrilles/secrets/pki.instance.cert',
            'KEY_PEM': '/var/opt/millegrilles/secrets/pki.instance.key',
            'MQ_HOSTNAME': 'mq',
        }
        commande_container_backup = DockerCommandes.CommandeRunContainer(
            image_backup,
            "-m millegrilles_messages.backup backup --source /var/opt/millegrilles_backup",
            environment=env_backup,
        )
        commande_container_backup.ajouter_mount('millegrilles_backup', '/var/opt/millegrilles_backup',
                                                mount_type='volume')
        commande_container_backup.ajouter_mount('/var/opt/millegrilles', '/var/opt/millegrilles',
                                                mount_type='bind', read_only=True)
        self.__docker_handler.ajouter_commande(commande_container_backup)
        resultat = await commande_container_backup.get_resultat()
        self.__logger.debug("Chiffrage backup applications complete : %s" % resultat)

    async def verifier_tor(self):
        commande = CommandeOnionizeGetHostname()
        self.__docker_handler.ajouter_commande(commande)
        try:
            hostname = await commande.get_resultat()
        except OnionizeNonDisponibleException:
            self.__logger.debug("Service onionize non demarre")
            return

        self.__logger.debug("Adresse onionize : %s" % hostname)
        return hostname


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
