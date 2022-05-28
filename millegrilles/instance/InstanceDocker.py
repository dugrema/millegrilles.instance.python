import asyncio
import logging


from asyncio import Event, TimeoutError
from docker.errors import APIError, NotFound
from os import path

from millegrilles_messages.docker.DockerHandler import DockerHandler
from millegrilles_messages.docker import DockerCommandes

from millegrilles.instance import Constantes
from millegrilles.instance.EtatInstance import EtatInstance
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.docker.ParseConfiguration import ConfigurationService


class EtatDockerInstanceSync:

    def __init__(self, etat_instance: EtatInstance, docker_handler: DockerHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__docker_handler = docker_handler  # DockerHandler

        self.__etat_instance.ajouter_listener(self.callback_changement_configuration)

    async def callback_changement_configuration(self, etat_instance: EtatInstance):
        self.__logger.info("callback_changement_configuration - Reload configuration")
        await self.verifier_config_instance()

    async def entretien(self, stop_event: Event):
        while stop_event.is_set() is False:
            self.__logger.debug("Debut Entretien EtatDockerInstanceSync")
            await self.verifier_config_instance()
            await self.verifier_date_certificats()
            self.__logger.debug("Fin Entretien EtatDockerInstanceSync")

            try:
                await asyncio.wait_for(stop_event.wait(), 60)
            except TimeoutError:
                pass

        self.__logger.info("Thread Entretien InstanceDocker terminee")

    async def verifier_date_certificats(self):
        pass

    async def verifier_config_instance(self):
        instance_id = self.__etat_instance.instance_id
        if instance_id is not None:
            await self.sauvegarder_config(Constantes.DOCKER_CONFIG_INSTANCE_ID, instance_id, comparer=True)

        niveau_securite = self.__etat_instance.niveau_securite
        if niveau_securite is not None:
            await self.sauvegarder_config(Constantes.DOCKER_CONFIG_INSTANCE_SECURITE, niveau_securite, comparer=True)

        idmg = self.__etat_instance.idmg
        if idmg is not None:
            await self.sauvegarder_config(Constantes.DOCKER_CONFIG_INSTANCE_IDMG, idmg, comparer=True)

        certificat_millegrille = self.__etat_instance.certificat_millegrille
        if certificat_millegrille is not None:
            await self.sauvegarder_config(Constantes.DOCKER_CONFIG_PKI_MILLEGRILLE, certificat_millegrille.certificat_pem)

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
        commande_initialiser_network = DockerCommandes.CommandeCreerNetworkOverlay('millegrille_net', aio=True)
        self.__docker_handler.ajouter_commande(commande_initialiser_network)
        await commande_initialiser_network.attendre()

    async def entretien_services(self, services: dict):
        commande_liste_services = DockerCommandes.CommandeListerServices(aio=True)
        self.__docker_handler.ajouter_commande(commande_liste_services)
        liste_services_docker = await commande_liste_services.get_liste()

        # Determiner s'il y a des services manquants
        nom_services_a_installer = set(services.keys())
        for s in liste_services_docker:
            name = s.name
            try:
                nom_services_a_installer.remove(name)
            except KeyError:
                pass

        if len(nom_services_a_installer) > 0:
            self.__logger.debug("Services manquants dans docker : %s" % nom_services_a_installer)

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
                # '__nom_application': nom_service,
                # '__certificat_info': {
                #     'label_prefix': 'pki.mq',
                # },
            }

            for nom_service in nom_services_a_installer:
                config_service = services[nom_service]
                await self.installer_service(nom_service, config_service, params)

    async def installer_service(self, nom_service: str, configuration: dict, params: dict):

        # Copier params, ajouter info service
        params = params.copy()
        params['__nom_application'] = nom_service
        params['__certificat_info'] = {'label_prefix': 'pki.%s' % nom_service}
        params['__password_info'] = {'label_prefix': 'passwd.%s' % nom_service}

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
        commande_creer_service = DockerCommandes.CommandeCreerService(image_tag, config_parsed, aio=True)
        self.__docker_handler.ajouter_commande(commande_creer_service)
        resultat = await commande_creer_service.get_resultat()

        pass
