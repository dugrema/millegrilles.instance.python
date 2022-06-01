import asyncio
import json
import logging


from asyncio import Event, TimeoutError
from docker.errors import APIError, NotFound
from os import path, listdir, unlink
from typing import Optional

from millegrilles_messages.docker.DockerHandler import DockerHandler
from millegrilles_messages.docker import DockerCommandes

from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService
from millegrilles_messages.docker.DockerHandler import CommandeDocker
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_instance.CommandesDocker import CommandeListeTopologie


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
                await self.verifier_date_certificats()
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

        info_updatee['fqdn_detecte'] = self.__etat_instance.hostname
        info_updatee['ip_detectee'] = self.__etat_instance.ip_address
        info_updatee['instance_id'] = self.__etat_instance.instance_id
        info_updatee['securite'] = self.__etat_instance.niveau_securite

        # Faire la liste des applications installees
        liste_applications = await self.get_liste_configurations()
        info_updatee['applications_configurees'] = liste_applications

        await producer.emettre_evenement(info_updatee, Constantes.DOMAINE_INSTANCE,
                                         ConstantesInstance.EVENEMENT_PRESENCE_INSTANCE,
                                         exchanges=Constantes.SECURITE_PROTEGE)

    async def verifier_date_certificats(self):
        pass

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

        # Determiner s'il y a des services manquants
        nom_services_a_installer = set(services.keys())
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
            'HOSTNAME': self.__etat_instance.nom_domaine,
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
        if self.__etat_instance.idmg is not None:
            params['__idmg'] = self.__etat_instance.idmg

        parser = ConfigurationService(configuration, params)
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
        commande_image = DockerCommandes.CommandeGetImage(image, pull=True, aio=True)
        self.__docker_handler.ajouter_commande(commande_image)
        image_info = await commande_image.get_resultat()

        image_tag = image_info['tags'][0]
        commande_creer_service = DockerCommandes.CommandeCreerService(image_tag, config_parsed, reinstaller=reinstaller, aio=True)
        self.__docker_handler.ajouter_commande(commande_creer_service)
        resultat = await commande_creer_service.get_resultat()

        pass

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

    async def installer_application(self, configuration: dict, reinstaller=False):
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
                    await self.__etat_instance.generer_certificats_module(self, nom_application, certificat)

            except KeyError:
                pass

            # try:
            #     passwords = dep['passwords']
            #     for password in passwords:
            #         try:
            #             current = correspondance['passwd.%s' % password]['current']
            #             current['password']
            #         except KeyError:
            #             self.__logger.info("Generer password %s pour %s" % (password, nom_application))
            #             await self.__etat_instance.generer_passwords(self, [password])

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

        redemarrer_nginx = False
        if nginx is not None:
            self.__logger.debug("Conserver information nginx")

            # await self.redemarrer_nginx()
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
            params = await self.get_params_env_service()
            params['__nom_application'] = nom_application
            await self.installer_service(nom_module, dep, params, reinstaller)

        if redemarrer_nginx is True:
            await self.redemarrer_nginx()

        return {'ok': True}

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

    async def get_liste_configurations(self) -> list:
        """
        Charge l'information de configuration de toutes les applications connues.
        :return:
        """
        info_configuration = list()
        path_docker_apps = self.__etat_instance.configuration.path_docker_apps
        for fichier_config in listdir(path_docker_apps):
            if not fichier_config.startswith('app.'):
                continue  # Skip, ce n'est pas une application
            with open(path.join(path_docker_apps, fichier_config), 'rb') as fichier:
                contenu = json.load(fichier)
            nom = contenu['nom']
            version = contenu['version']
            info_configuration.append({'nom': nom, 'version': version})

        return info_configuration
