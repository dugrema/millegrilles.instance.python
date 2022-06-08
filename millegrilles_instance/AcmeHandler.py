import logging

from millegrilles_messages.docker.DockerHandler import DockerHandler, CommandeDocker, DockerClient


class CommandeAcmeIssue(CommandeDocker):
    """
    Permet de faire un issue pour recuperer un certificat SSL web
    """

    def __init__(self, callback=None):
        super().__init__(callback, aio=True)
        self.facteur_throttle = 0.1

    def executer(self, docker_client: DockerClient):
        pass

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


class AcmeHandler:

    def __init__(self, docker_handler: DockerHandler):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__docker_handler = docker_handler

    def issue(self, params: dict):
        """
        Obtient un nouveau certificat web TLS avec LetsEncrypt
        """
        # Aller chercher le certificat SSL de LetsEncrypt
        domaine_noeud = params['domaine']
        mode_test = params.get('modeTest') or False
        force = params.get('force') or False
        mode_creation = params.get('modeCreation')

        params_environnement = dict()
        params_secrets = dict()

        methode = {
            'modeCreation': mode_creation,
            'params_environnement': params_environnement,
        }

        if mode_creation == 'dns_cloudns':
            subid = params['cloudns_subauthid']
            params_environnement["CLOUDNS_SUB_AUTH_ID"] = subid
            params_secrets["CLOUDNS_AUTH_PASSWORD"] = params['cloudns_password']
            commande_str = '--dns dns_cloudns'
        else:
            commande_str = '--webroot /usr/share/nginx/html'

        configuration_acme = {
            'domain': domaine_noeud,
            'methode': methode,
            'modeTest': mode_test,
        }

        try:
            # Utiliser dnssleep, la detection de presence du record TXT marche rarement
            dnssleep = params['dnssleep']
            methode['dnssleep'] = dnssleep
            commande_str = commande_str + ' --dnssleep %s' % str(dnssleep)
        except KeyError:
            pass

        # Ajouter le domaine principal
        commande_str = commande_str + ' -d %s' % domaine_noeud

        try:
            domaines_additionnels = params['domainesAdditionnels']
            configuration_acme['domaines_additionnels'] = domaines_additionnels
            commande_str = commande_str + ' -d ' + ' -d '.join(domaines_additionnels)
        except KeyError:
            pass

        if force is True:
            commande_str = '--force ' + commande_str

        if mode_test:
            commande_str = '--test ' + commande_str

        params_combines = dict(params_environnement)
        params_combines.update(params_secrets)
        params_combines = ['%s=%s' % item for item in params_combines.items()]

        acme_container_id = gestionnaire_docker.trouver_container_pour_service('acme')
        commande_acme = "acme.sh --issue %s" % commande_str
        configuration_acme['commande'] = commande_acme

        print('commande ACME : %s' % commande_acme)

        # Conserver la configuration ACME immediatement
        self.gestionnaire_docker.sauvegarder_config('acme.configuration', configuration_acme)

        # Retourner la reponse a la commande, poursuivre execution de ACME
        try:
            generateur_transactions = self.generateur_transactions
        except AttributeError:
            generateur_transactions = None

        if generateur_transactions is not None:
            try:
                mq_properties = commande.mq_properties
                reply_to = mq_properties.reply_to
                correlation_id = mq_properties.correlation_id
                reponse = {'ok': True}
                generateur_transactions.transmettre_reponse(reponse, reply_to, correlation_id)
            except Exception:
                self.__logger.exception("Erreur transmission reponse a initialiser_domaine %s" % domaine_noeud)

        resultat_acme, output_acme = gestionnaire_docker.executer_script_blind(
            acme_container_id,
            commande_acme,
            environment=params_combines
        )

        domaine = 'monitor'
        action = 'resultatAcme'
        partition = self.noeud_id
        rk = 'evenement.%s.%s.%s' % (domaine, partition, action)

        # Verifier resultat. 0=OK, 2=Reutilisation certificat existant
        if resultat_acme not in [0, 2]:
            self.__logger.error("Erreur ACME, code : %d\n%s", resultat_acme, output_acme.decode('utf-8'))
            erreur_string = "Erreur ACME, code : %d" % resultat_acme
            evenement_echec = {
                'ok': False,
                'err': erreur_string,
                'code': resultat_acme,
                'output': output_acme.decode('utf-8')
            }
            self._connexion_middleware.generateur_transactions.emettre_message(
                evenement_echec, rk, action=action, partition=partition, ajouter_certificats=True)
            return
            # raise Exception("Erreur creation certificat avec ACME")

        try:
            cert_bytes = gestionnaire_docker.get_archive_bytes(acme_container_id, '/acme.sh/%s' % domaine_noeud)
            io_buffer = io.BytesIO(cert_bytes)
            with tarfile.open(fileobj=io_buffer) as tar_content:
                member_key = tar_content.getmember('%s/%s.key' % (domaine_noeud, domaine_noeud))
                key_bytes = tar_content.extractfile(member_key).read()
                member_fullchain = tar_content.getmember('%s/fullchain.cer' % domaine_noeud)
                fullchain_bytes = tar_content.extractfile(member_fullchain).read()

            # Inserer certificat, cle dans docker
            secret_name, date_secret = gestionnaire_docker.sauvegarder_secret(
                'pki.web.key', key_bytes, ajouter_date=True)

            # gestionnaire_docker.sauvegarder_config('acme.configuration', json.dumps(configuration_acme).encode('utf-8'))
            gestionnaire_docker.sauvegarder_config('pki.web.cert.' + date_secret, fullchain_bytes)

            # Forcer reconfiguration nginx
            gestionnaire_docker.maj_service('nginx')

            if generateur_transactions is not None:
                evenement_succes = {
                    'ok': True,
                    'code': resultat_acme,
                    'output': output_acme.decode('utf-8')
                }
                generateur_transactions.emettre_message(
                    evenement_succes, rk, action=action, partition=partition, ajouter_certificats=True)
        except Exception:
            self.__logger.exception("Erreur sauvegarde certificat ACME dans docker")
            if generateur_transactions is not None:
                evenement_erreur = {
                    'ok': False,
                    'err': 'Erreur sauvegarde certificat ACME dans docker (note: certificat TLS genere OK)',
                    'output': output_acme.decode('utf-8')
                }
                generateur_transactions.emettre_message(
                    evenement_erreur, rk, action=action, partition=partition, ajouter_certificats=True)

    def get_certificate(self):
        # acme.sh --install-cert -d example.com \
        # --key-file       /path/to/keyfile/in/nginx/key.pem  \
        # --fullchain-file /path/to/fullchain/nginx/cert.pem \
        # --reloadcmd     "service nginx force-reload"
        pass
