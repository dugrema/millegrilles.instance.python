import json
import logging
import lzma

from cryptography.x509.extensions import ExtensionNotFound
from os import listdir, path

from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance import Constantes as ConstantesInstance
from millegrilles_messages.messages import Constantes
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_messages.messages.MessagesModule import MessageWrapper
from millegrilles_instance.EntretienApplications import GestionnaireApplications


class CommandHandler:

    def __init__(self, entretien_instance, etat_instance: EtatInstance,
                 etat_docker: EtatDockerInstanceSync, gestionnaire_applications: GestionnaireApplications):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self._entretien_instance = entretien_instance
        self._etat_instance = etat_instance
        self._etat_docker = etat_docker
        self._gestionnaire_applications = gestionnaire_applications

    async def executer_commande(self, producer: MessageProducerFormatteur, message: MessageWrapper):
        reponse = None

        if message.est_valide is False:
            return {'ok': False, 'err': 'Signature ou certificat invalide'}

        routing_key = message.routing_key
        action = routing_key.split('.').pop()
        exchange = message.exchange
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
            if exchange == Constantes.SECURITE_PROTEGE and Constantes.SECURITE_PROTEGE in exchanges:
                if Constantes.ROLE_CORE in roles:
                    if action == ConstantesInstance.COMMANDE_TRANSMETTRE_CATALOGUES:
                        return await self.transmettre_catalogue(producer)

            elif delegation_globale == Constantes.DELEGATION_GLOBALE_PROPRIETAIRE:
                if action == ConstantesInstance.COMMANDE_APPLICATION_INSTALLER:
                    reponse = await self.installer_application(message)
                elif action == ConstantesInstance.COMMANDE_APPLICATION_SUPPRIMER:
                    reponse = await self.supprimer_application(message)
                elif action == ConstantesInstance.COMMANDE_APPLICATION_DEMARRER:
                    reponse = await self.demarrer_application(message)
                elif action == ConstantesInstance.COMMANDE_APPLICATION_ARRETER:
                    reponse = await self.arreter_application(message)

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
        await self._gestionnaire_applications.installer_application()

    async def supprimer_application(self, message: MessageWrapper):
        await self._gestionnaire_applications.supprimer_application()

    async def demarrer_application(self, message: MessageWrapper):
        await self._gestionnaire_applications.demarrer_application()

    async def arreter_application(self, message: MessageWrapper):
        await self._gestionnaire_applications.arreter_application()
