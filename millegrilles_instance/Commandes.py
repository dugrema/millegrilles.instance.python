import json
import logging
import lzma

from cryptography.x509.extensions import ExtensionNotFound
from os import listdir, path
from typing import Optional

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_messages.messages.MessagesModule import MessageWrapper
from millegrilles_instance.EntretienApplications import GestionnaireApplications
from millegrilles_instance.AcmeHandler import CommandeAcmeIssue, CommandeAcmeExtractCertificates


class CommandHandler:

    def __init__(self, entretien_instance, etat_instance: EtatInstance,
                 etat_docker: Optional[EtatDockerInstanceSync], gestionnaire_applications: GestionnaireApplications):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._entretien_instance = entretien_instance
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker
        self._gestionnaire_applications = gestionnaire_applications

    async def executer_commande(self, producer: MessageProducerFormatteur, message: MessageWrapper):
        reponse = None

        routing_key = message.routing_key
        exchange = message.exchange
        if exchange is None or exchange == '':
            self.__logger.warning("Message reponse recu sur Q commande, on le drop (RK: %s)" % routing_key)
            return

        if message.est_valide is False:
            return {'ok': False, 'err': 'Signature ou certificat invalide'}

        action = routing_key.split('.').pop()
        enveloppe = message.certificat

        try:
            exchanges = enveloppe.get_exchanges
        except ExtensionNotFound:
            exchanges = list()

        try:
            roles = enveloppe.get_roles
        except ExtensionNotFound:
            roles = list()

        try:
            delegation_globale = enveloppe.get_delegation_globale
        except ExtensionNotFound:
            delegation_globale = None

        try:
            if exchange == Constantes.SECURITE_PUBLIC and Constantes.SECURITE_PUBLIC in exchanges:
                if Constantes.ROLE_CORE in roles:
                    if action == ConstantesInstance.EVENEMENT_TOPOLOGIE_FICHEPUBLIQUE:
                        return await self.sauvegarder_fiche_publique(message)

            if exchange == Constantes.SECURITE_PUBLIC and delegation_globale == Constantes.DELEGATION_GLOBALE_PROPRIETAIRE:
                if action == ConstantesInstance.REQUETE_CONFIGURATION_ACME:
                    return await self.get_configuration_acme(message)

            if exchange == Constantes.SECURITE_PROTEGE and Constantes.SECURITE_PROTEGE in exchanges:
                if Constantes.ROLE_CORE in roles:
                    if action == ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES:
                        return await self.transmettre_catalogue(producer)

            if self._etat_instance.niveau_securite == Constantes.SECURITE_SECURE:
                securite_effectif = Constantes.SECURITE_PROTEGE
            else:
                securite_effectif = self._etat_instance.niveau_securite

            if exchange == securite_effectif:  # Doit etre meme niveau que l'instance
                if delegation_globale == Constantes.DELEGATION_GLOBALE_PROPRIETAIRE:
                    if action == ConstantesInstance.COMMANDE_APPLICATION_INSTALLER:
                        return await self.installer_application(message)
                    if action == ConstantesInstance.COMMANDE_APPLICATION_SUPPRIMER:
                        return await self.supprimer_application(message)
                    if action == ConstantesInstance.COMMANDE_APPLICATION_DEMARRER:
                        return await self.demarrer_application(message)
                    if action == ConstantesInstance.COMMANDE_APPLICATION_ARRETER:
                        return await self.arreter_application(message)
                    if action == ConstantesInstance.COMMANDE_APPLICATION_REQUETE_CONFIG:
                        return await self.get_application_configuration(message)
                    if action == ConstantesInstance.COMMANDE_APPLICATION_CONFIGURER:
                        return await self.configurer_application(message)
                    if action == ConstantesInstance.COMMANDE_CONFIGURER_DOMAINE:
                        return await self.configurer_domaine(message)

                    # Exchange protege seulement
                    if exchange == Constantes.SECURITE_PROTEGE:
                        if action == ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES:
                            return await self.transmettre_catalogue(producer)

            if reponse is None:
                reponse = {'ok': False, 'err': 'Commande inconnue ou acces refuse'}
        except Exception as e:
            self.__logger.exception("Erreur execution commande")
            reponse = {'ok': False, 'err': str(e)}

        return reponse

    async def transmettre_catalogue(self, producer: MessageProducerFormatteur):
        self.__logger.info("Transmettre catalogues")
        path_catalogues = self._etat_instance.configuration.path_catalogues

        liste_fichiers_apps = listdir(path_catalogues)

        info_apps = [path.join(path_catalogues, f) for f in liste_fichiers_apps if f.endswith('.json.xz')]
        for app_path in info_apps:
            with lzma.open(app_path, 'rt') as fichier:
                app_transaction = json.load(fichier)

            commande = {"catalogue": app_transaction}
            await producer.executer_commande(commande, domaine=Constantes.DOMAINE_CORE_CATALOGUES,
                                             action='catalogueApplication', exchange=Constantes.SECURITE_PROTEGE,
                                             nowait=True)

        return {'ok': True}

    async def installer_application(self, message: MessageWrapper):
        contenu = message.parsed
        # nom_application = contenu['nom_application']
        configuration = contenu['configuration']
        return await self._gestionnaire_applications.installer_application(configuration)

    async def supprimer_application(self, message: MessageWrapper):
        contenu = message.parsed
        nom_application = contenu['nom_application']
        return await self._gestionnaire_applications.supprimer_application(nom_application)

    async def demarrer_application(self, message: MessageWrapper):
        contenu = message.parsed
        nom_application = contenu['nom_application']
        return await self._gestionnaire_applications.demarrer_application(nom_application)

    async def arreter_application(self, message: MessageWrapper):
        contenu = message.parsed
        nom_application = contenu['nom_application']
        return await self._gestionnaire_applications.arreter_application(nom_application)

    async def sauvegarder_fiche_publique(self, message: MessageWrapper):
        self.__logger.debug("Sauvegarder fiche publique")
        parsed = message.parsed
        self._entretien_instance.sauvegarder_nginx_data('fiche.json', parsed, path_html=True)
        return {'ok': True}

    async def get_application_configuration(self, message: MessageWrapper):
        path_catalogues = self._etat_instance.configuration.path_docker_apps
        parsed = message.parsed
        nom_application = parsed['nom_application']
        path_fichier = path.join(path_catalogues, 'app.%s.json' % nom_application)
        with open(path_fichier, 'rb') as fichier:
            configuration_dict = json.load(fichier)

        return {'nom_application': nom_application, 'configuration': configuration_dict}

    async def configurer_application(self, message: MessageWrapper):
        parsed = message.parsed
        nom_application = parsed['nom_application']
        configuration = parsed['configuration']

        configuration_str = json.dumps(configuration)

        path_catalogues = self._etat_instance.configuration.path_docker_apps
        path_fichier = path.join(path_catalogues, 'app.%s.json' % nom_application)
        with open(path_fichier, 'w') as fichier:
            fichier.write(configuration_str)

        return await self._gestionnaire_applications.installer_application(configuration, reinstaller=True)

    async def configurer_domaine(self, message: MessageWrapper):
        parsed = message.parsed

        # Preparer configuration pour sauvegarde
        path_configuration = self._etat_instance.configuration.path_configuration
        path_fichier_acme = path.join(path_configuration, ConstantesInstance.CONFIG_NOMFICHIER_ACME)
        elems = [
            'modeCreation', 'force', 'modeTest',
            'domainesAdditionnels', 'dnssleep',
            'cloudns_subauthid',
            # 'cloudns_password',
        ]
        configuration = dict()
        for elem in elems:
            try:
                configuration[elem] = parsed[elem]
            except KeyError:
                pass

        # Executer issue ACME
        hostname = self._etat_instance.hostname
        commande = CommandeAcmeIssue(hostname, parsed)
        self._etat_docker.ajouter_commande(commande)
        resultat = await commande.get_resultat()

        if resultat['code'] not in [0, 2]:
            return {'ok': False, 'code': resultat['code'], 'err': "Echec creation certificat pour %s" % hostname}

        try:
            with open(path_fichier_acme, 'w') as fichier:
                json.dump(configuration, fichier, indent=2)

            # Declencher chargement certificat web
            await self._etat_instance.reload_configuration()

            return {'ok': True}
        except Exception as e:
            self.__logger.exception("Erreur sauvegarde configuration acme.json")
            return {'ok': False, 'err': str(e)}

    async def get_configuration_acme(self, message: MessageWrapper):
        path_configuration = self._etat_instance.configuration.path_configuration
        path_fichier_acme = path.join(path_configuration, ConstantesInstance.CONFIG_NOMFICHIER_ACME)
        try:
            with open(path_fichier_acme, 'r') as fichier:
                configuration = json.load(fichier)
            configuration['ok'] = True
            return configuration
        except FileNotFoundError:
            return {'ok': False, 'err': 'Configuration absente'}

    async def set_hostname(self, message: MessageWrapper):
        hostname = message.parsed['hostname']
        self._etat_instance.maj_configuration_json({'hostname': hostname})
        return {'ok': True}
