import asyncio
import base64
import datetime
import errno
import logging
import math
import pathlib
import secrets

from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError
from docker.errors import APIError
from os import path, stat
from typing import Optional

from millegrilles_messages.messages import Constantes
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.certificats.CertificatsWeb import generer_self_signed_rsa
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_messages.GenerateursSecrets import GenerateurEd25519, GenerateurRsa
from millegrilles_messages.docker import DockerCommandes
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur


logger = logging.getLogger(__name__)


def preparer_certificats_web(path_secrets: str):

    # Verifier si le certificat web existe (utiliser de preference)
    path_cert_web = path.join(path_secrets, 'pki.web.cert')
    path_key_web = path.join(path_secrets, 'pki.web.cle')
    if path.exists(path_cert_web) and path.exists(path_key_web):
        return path_cert_web, path_key_web

    # Verifier si le certificat self-signed existe
    path_cert_webss = path.join(path_secrets, 'pki.webss.cert')
    path_key_webss = path.join(path_secrets, 'pki.webss.cle')
    if path.exists(path_cert_webss) and path.exists(path_key_webss):
        clecertificat_genere = CleCertificat.from_files(path_key_webss, path_cert_webss)
        pem_certificat = clecertificat_genere.enveloppe.chaine_pem()
        certificat = ''.join(pem_certificat)
    else:
        # Generer certificat self-signed
        clecertificat_genere = generer_self_signed_rsa('localhost')

        certificat = ''.join(clecertificat_genere.get_pem_certificat())
        with open(path_cert_webss, 'w') as fichier:
            fichier.write(certificat)
        with open(path_key_webss, 'w') as fichier:
            fichier.write(clecertificat_genere.get_pem_cle())

    with open(path_cert_web, 'w') as fichier:
        fichier.write(certificat)
    with open(path_key_web, 'wb') as fichier:
        fichier.write(clecertificat_genere.clecertificat.private_key_bytes())

    return path_cert_web, path_key_web


async def generer_certificats_modules(producer: MessageProducerFormatteur, client_session: ClientSession, etat_instance, configuration: dict,
                                      etat_docker: Optional[EtatDockerInstanceSync] = None):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_local_certificat = value.get('nom') or nom_module

        nom_certificat = 'pki.%s.cert' % nom_local_certificat
        nom_cle = 'pki.%s.cle' % nom_local_certificat
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)
        combiner_keycert = value.get('combiner_keycert') or False

        sauvegarder = False
        try:
            clecertificat = CleCertificat.from_files(path_cle, path_certificat)
            enveloppe = clecertificat.enveloppe

            # Ok, verifier si le certificat doit etre renouvele
            detail_expiration = enveloppe.calculer_expiration()
            roles = enveloppe.get_roles
            #if 'maitredescles' in roles:
            #    logger.error("!!! Certiticats.generer_certificats_modules HACK MaitreDesCles !!!!")
            #    detail_expiration['renouveler'] = True

            if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                if 'maitredescles' in roles:
                    # Verifier si on est en cours de rotation d'un certificat de maitre des cles
                    # Il faut laisser le temps aux cles de finir d'etre rechiffrees
                    if detail_expiration['expire'] is True or etat_instance.is_rotation_maitredescles() is False:
                        clecertificat = await generer_nouveau_certificat(
                            producer, client_session, etat_instance, nom_local_certificat, value)
                        sauvegarder = True

                        if detail_expiration['expire'] is not True:
                            # Rotation du certificat qui n'est pas expire
                            # Emettre une commande de rotation pour le maitre des cles, attendre reponse
                            commande = {
                                'certificat': clecertificat.enveloppe.chaine_pem(),
                            }
                            try:
                                reponse = await producer.executer_commande(
                                    commande, 'MaitreDesCles', 'rotationCertificat',
                                    exchange='3.protege',
                                    partition=enveloppe.fingerprint
                                )
                            except Exception as e:
                                if detail_expiration['expire'] is True:
                                    # Pas le choix - le certificat est expire, on force la rotation
                                    logger.error(
                                        "generer_certificats_modules Erreur rotation cle certificat (FORCE) : %s" % e)
                                else:
                                    # Skip, la rotation a ecohoue. On va ressayer plus tard.
                                    logger.warning(
                                        "generer_certificats_modules Erreur rotation cle certificat (SKIP) : %s" % e)
                                    continue

                        etat_instance.set_rotation_maitredescles()
                else:
                    clecertificat = await generer_nouveau_certificat(producer, client_session, etat_instance, nom_local_certificat, value)
                    sauvegarder = True

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_local_certificat)
            clecertificat = await generer_nouveau_certificat(producer, client_session, etat_instance, nom_local_certificat, value)
            sauvegarder = True

        # Verifier si le certificat et la cle sont stocke dans docker
        if sauvegarder is True:

            cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
            with open(path_cle, 'wb') as fichier:
                fichier.write(clecertificat.private_key_bytes())
                if combiner_keycert is True:
                    fichier.write(cert_str.encode('utf-8'))
            with open(path_certificat, 'w') as fichier:
                cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
                fichier.write(cert_str)

        if etat_docker is not None:
            await etat_docker.assurer_clecertificat(nom_local_certificat, clecertificat, combiner_keycert)


async def generer_certificats_modules_satellites(producer: MessageProducerFormatteur, etat_instance,
                                                 etat_docker: Optional[EtatDockerInstanceSync], configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_certificat = 'pki.%s.cert' % nom_module
        nom_cle = 'pki.%s.cle' % nom_module
        path_certificat = path.join(path_secrets, nom_certificat)
        path_cle = path.join(path_secrets, nom_cle)
        combiner_keycert = value.get('combiner_keycert') or False

        sauvegarder = False
        try:
            clecertificat = CleCertificat.from_files(path_cle, path_certificat)
            enveloppe = clecertificat.enveloppe

            # Ok, verifier si le certificat doit etre renouvele
            detail_expiration = enveloppe.calculer_expiration()
            if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                clecertificat = await demander_nouveau_certificat(producer, etat_instance, nom_module, value)
                sauvegarder = True

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_module)
            clecertificat = await demander_nouveau_certificat(producer, etat_instance, nom_module, value)
            sauvegarder = True

        # Verifier si le certificat et la cle sont stocke dans docker
        if sauvegarder is True:

            cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
            with open(path_cle, 'wb') as fichier:
                fichier.write(clecertificat.private_key_bytes())
                if combiner_keycert is True:
                    fichier.write(cert_str.encode('utf-8'))
            with open(path_certificat, 'w') as fichier:
                cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
                fichier.write(cert_str)

        if etat_docker is not None:
            await etat_docker.assurer_clecertificat(nom_module, clecertificat, combiner_keycert)


async def nettoyer_configuration_expiree(etat_docker: EtatDockerInstanceSync):
    commande_config = DockerCommandes.CommandeGetConfigurationsDatees()
    etat_docker.ajouter_commande(commande_config)
    config_datees = await commande_config.get_resultat()

    config_a_supprimer = set()
    secret_a_supprimer = set()
    correspondance = config_datees['correspondance']
    for element_config in correspondance.values():
        try:
            current_config = element_config['current']
            set_names_courants = set([v['name'] for v in current_config.values()])
        except KeyError:
            set_names_courants = set()

        for elem in element_config.values():
            for elem_config in elem.values():
                name_elem = elem_config['name']
                if name_elem not in set_names_courants:
                    name_split = name_elem.split('.')
                    if name_split[2] == 'cert':
                        config_a_supprimer.add(name_elem)
                    else:
                        secret_a_supprimer.add(name_elem)

    for config_name in config_a_supprimer:
        command = DockerCommandes.CommandeSupprimerConfiguration(config_name, aio=True)
        etat_docker.ajouter_commande(command)
        try:
            await command.attendre()
        except APIError as apie:
            if apie.status_code == 400:  # in use
                pass
            elif apie.status_code == 404:  # deja supprime
                pass
            else:
                raise apie

    for secret_name in secret_a_supprimer:
        command = DockerCommandes.CommandeSupprimerSecret(secret_name, aio=True)
        etat_docker.ajouter_commande(command)
        try:
            await command.attendre()
        except APIError as apie:
            if apie.status_code == 400:  # in use
                pass
            elif apie.status_code == 404:  # deja supprime
                pass
            else:
                raise apie

    pass


async def renouveler_certificat_instance_protege(
        producer: MessageProducerFormatteur, client_session: ClientSession, etat_instance) -> CleCertificat:

    instance_id = etat_instance.instance_id

    clecsr = CleCsrGenere.build(cn=instance_id)
    csr_str = clecsr.get_pem_csr()
    commande = {'csr': csr_str}

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = etat_instance.formatteur_message
    message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, commande)

    logger.debug("Demande de signature de certificat pour instance protegee => %s\n%s" % (message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'renouvelerInstance')
    try:
        async with client_session.post(path_csr, json=message_signe) as resp:
            resp.raise_for_status()
            reponse = await resp.json()
        certificat = reponse['certificat']

        # Confirmer correspondance entre certificat et cle
        clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
        if clecertificat.cle_correspondent() is False:
            raise Exception("Erreur cert/cle ne correspondent pas")

        logger.debug("Reponse certissuer certificat protege\n%s" % ''.join(certificat))
        return clecertificat
    except (ClientConnectorError, ClientResponseError):
        logger.exception("Certissuer local non disponible, fallback CorePki")
        return await renouveler_certificat_satellite(producer, etat_instance)


async def renouveler_certificat_satellite(producer: MessageProducerFormatteur, etat_instance) -> CleCertificat:

    instance_id = etat_instance.instance_id
    niveau_securite = etat_instance.niveau_securite

    exchanges = [Constantes.SECURITE_SECURE, Constantes.SECURITE_PROTEGE, Constantes.SECURITE_PRIVE, Constantes.SECURITE_PUBLIC]
    while exchanges[0] != niveau_securite:
        exchanges.pop(0)

    clecsr = CleCsrGenere.build(cn=instance_id)
    csr_str = clecsr.get_pem_csr()
    configuration = {
        'csr': csr_str,
        'roles': ['instance'],
        'exchanges': exchanges
    }

    path_secrets = etat_instance.configuration.path_secrets
    nom_certificat = 'pki.instance.cert'
    nom_cle = 'pki.instance.key'
    path_certificat = path.join(path_secrets, nom_certificat)
    path_cle = path.join(path_secrets, nom_cle)

    # Emettre commande de signature, attendre resultat
    message_reponse = await producer.executer_commande(configuration, 'CorePki', 'signerCsr', exchange=Constantes.SECURITE_PUBLIC)
    reponse = message_reponse.parsed

    certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    with open(path_cle, 'wb') as fichier:
        fichier.write(clecertificat.private_key_bytes())
    with open(path_certificat, 'w') as fichier:
        cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
        fichier.write(cert_str)

    logger.debug("Reponse certissuer certificat satellite\n%s" % ''.join(certificat))
    return clecertificat


async def generer_nouveau_certificat(producer: MessageProducerFormatteur,
                                     client_session: ClientSession,
                                     etat_instance,
                                     nom_module: str,
                                     configuration: dict) -> CleCertificat:
    instance_id = etat_instance.instance_id
    idmg = etat_instance.certificat_millegrille.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = etat_instance.hostname
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = etat_instance.formatteur_message
    message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, configuration)

    logger.debug("Demande de signature de certificat pour %s => %s\n%s" % (nom_module, message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    try:
        async with client_session.post(path_csr, json=message_signe) as resp:
            resp.raise_for_status()
            reponse = await resp.json()

        certificat = reponse['certificat']
    except (ClientConnectorError, ClientResponseError):
        logger.exception("Certissuer local non disponible, fallback CorePki")
        message_reponse = await producer.executer_commande(
            configuration, 'CorePki', 'signerCsr', exchange=etat_instance.niveau_securite)
        reponse = message_reponse.parsed
        certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    logger.debug("Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
    return clecertificat


async def demander_nouveau_certificat(producer: MessageProducerFormatteur, etat_instance, nom_module: str, configuration: dict) -> CleCertificat:
    instance_id = etat_instance.instance_id
    idmg = etat_instance.certificat_millegrille.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = etat_instance.hostname
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Emettre commande de signature, attendre resultat
    niveau_securite = etat_instance.niveau_securite
    if niveau_securite == '4.secure':
        instance_id = etat_instance.instance_id

        clecsr = CleCsrGenere.build(cn=instance_id)
        csr_str = clecsr.get_pem_csr()
        commande = {'csr': csr_str}

        # Signer avec notre certificat (instance), requis par le certissuer
        formatteur_message = etat_instance.formatteur_message
        message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, commande)

        url_issuer = etat_instance.certissuer_url
        path_csr = path.join(url_issuer, 'renouvelerInstance')
        client_session = etat_instance.client_session
        async with client_session.post(path_csr, json=message_signe) as resp:
            resp.raise_for_status()
            reponse = await resp.json()

        certificat = reponse['certificat']
    else:
        # Demander un nouveau certificat. Timeout long (60 secondes).
        message_reponse = await producer.executer_commande(
            configuration, 'CorePki', 'signerCsr', exchange=niveau_securite, timeout=60)
        reponse = message_reponse.parsed
        certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    logger.debug("Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
    return clecertificat


async def signer_certificat_instance_secure(etat_instance, message: dict) -> CleCertificat:
    """
    Permet de signer localement un certificat en utiliser le certissuer local (toujours present sur instance secure)
    """
    logger.debug("Demande de signature de certificat via instance secure => %s" % message)
    client_session = etat_instance.client_session
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    async with client_session.post(path_csr, json=message) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    logger.debug("Reponse certissuer signer_certificat_instance_secure\n%s" % ''.join(reponse))
    return reponse


async def signer_certificat_usager_via_secure(etat_instance, message: dict) -> CleCertificat:
    """
    Permet de signer localement un certificat en utiliser le certissuer local (toujours present sur instance secure)
    """
    logger.debug("Demande de signature de certificat via instance secure => %s" % message)
    client_session = etat_instance.client_session
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerUsager')
    async with client_session.post(path_csr, json=message) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    logger.debug("Reponse certissuer signer_certificat_instance_secure\n%s" % ''.join(reponse))
    return reponse


async def signer_certificat_public_key_via_secure(etat_instance, message: dict) -> CleCertificat:
    """
    Permet de signer localement un certificat en utiliser le certissuer local (toujours present sur instance secure)
    """
    logger.debug("Demande de signature de certificat via instance secure => %s" % message)
    client_session = etat_instance.client_session
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerPublickeyDomaine')
    async with client_session.post(path_csr, json=message) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

    logger.debug("Reponse certissuer signer_certificat_instance_secure\n%s" % ''.join(reponse))
    return reponse


async def generer_passwords(etat_instance, etat_docker: Optional[EtatDockerInstanceSync],
                            liste_passwords: list):
    """
    Generer les passwords manquants.
    :param etat_instance:
    :param etat_docker:
    :param liste_noms_passwords:
    :return:
    """
    path_secrets = etat_instance.configuration.path_secrets
    if etat_docker is not None:
        configurations = await etat_docker.get_configurations_datees()
        secrets_dict = configurations['secrets']
    else:
        secrets_dict = dict()

    for gen_password in liste_passwords:
        if isinstance(gen_password, dict):
            label = gen_password['label']
            type_password = gen_password['type']
            size = gen_password.get('size')
        elif isinstance(gen_password, str):
            label = gen_password
            type_password = 'password'
            size = 32
        else:
            raise ValueError('Mauvais type de generateur de mot de passe : %s' % gen_password)

        prefixe = 'passwd.%s' % label
        path_password = path.join(path_secrets, prefixe + '.txt')

        try:
            with open(path_password, 'r') as fichier:
                password = fichier.read().strip()
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime
        except FileNotFoundError:
            # Fichier non trouve, on doit le creer
            password = generer_password(type_password, size)
            with open(path_password, 'w') as fichier:
                fichier.write(password)
            info_fichier = stat(path_password)
            date_password = info_fichier.st_mtime

        logger.debug("Date password : %s" % date_password)
        date_password = datetime.datetime.utcfromtimestamp(date_password)
        date_password_str = date_password.strftime('%Y%m%d%H%M%S')

        label_passord = '%s.%s' % (prefixe, date_password_str)
        try:
            secrets_dict[label_passord]
            continue  # Mot de passe existe
        except KeyError:
            pass  # Le mot de passe n'existe pas

        # Ajouter mot de passe
        if etat_docker is not None:
            await etat_docker.ajouter_password(label, date_password_str, password)


def generer_password(type_generateur='password', size: int = None):
    if type_generateur == 'password':
        if size is None:
            size = 32
        generer_bytes = math.ceil(size / 4 * 3)
        pwd_genere = base64.b64encode(secrets.token_bytes(generer_bytes)).decode('utf-8').replace('=', '')
        valeur = pwd_genere[:size]
    elif type_generateur == 'ed25519':
        generateur = GenerateurEd25519()
        valeur = generateur.generer_private_openssh().decode('utf-8')
    elif type_generateur == 'rsa':
        generateur = GenerateurRsa()
        valeur = generateur.generer_private_openssh().decode('utf-8')
    else:
        raise ValueError('Type de generateur inconnu : %s' % type_generateur)

    return valeur


class CommandeSignature:

    def __init__(self, etat_instance):
        self._etat_instance = etat_instance
        self.__event_done = asyncio.Event()
        self.__exception = None
        self.__result = None

    def set_done(self):
        self.__event_done.set()

    @property
    def exception(self):
        return self.__exception

    @exception.setter
    def exception(self, exception):
        self.__exception = exception

    @property
    async def done(self, timeout=120):
        await asyncio.wait_for(self.__event_done.wait(), timeout=timeout)
        if self.__exception:
            raise self.__exception
        return self.__result

    async def run(self, producer=None):
        raise NotImplementedError('must implement')


class CommandeSignatureInstance(CommandeSignature):

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        super().__init__(etat_instance)

    async def run(self, producer=None):
        producer = await self._etat_instance.get_producer()

        # Determiner niveau de securite de l'instance
        niveau = self.get_niveau()

        clecertificat = None
        if niveau in [Constantes.SECURITE_SECURE, Constantes.SECURITE_PROTEGE]:
            # Tenter de generer le certificat avec le certissuer local en premier
            try:
                clecertificat = await renouveler_certificat_instance_protege(
                    producer, self._etat_instance.client_session, self._etat_instance)
            except asyncio.TimeoutError:
                self.__logger.warning(
                    "CommandeSignatureInstance.run Timeout utilisation certissuer local, fallback sur CorePki")
            except Exception:
                self.__logger.exception("CommandeSignatureInstance.run Erreur utilisation certissuer local, fallback sur CorePki")

        if clecertificat is None:
            self.__logger.info("CommandeSignatureInstance.run Demander certificat instance via CorPki.signerCsr")
            clecertificat = await renouveler_certificat_satellite(producer, self._etat_instance)

        if clecertificat is not None:
            await self.sauvegarder_clecert(clecertificat)

            # self.__logger.info("CommandeSignatureInstance.run Nouveau certificat d'instance installe - redemarrer")
            # await self._etat_instance.stop()

            # Reload configuration avec le nouveau certificat
            self.__logger.info("CommandeSignatureInstance.run Nouveau certificat d'instance installe - reload configuration")
            await self._etat_instance.reload_configuration()

    def get_niveau(self):
        clecertificat_courant: CleCertificat = self._etat_instance.clecertificat
        exchanges = clecertificat_courant.get_exchanges
        niveaux = [Constantes.SECURITE_SECURE, Constantes.SECURITE_PROTEGE, Constantes.SECURITE_PRIVE, Constantes.SECURITE_PUBLIC]
        for niveau in niveaux:
            if niveau in exchanges:
                return niveau

        raise Exception('certificat courant sans niveau de securite')

    async def sauvegarder_clecert(self, clecertificat: CleCertificat):
        path_secrets = pathlib.Path(self._etat_instance.configuration.path_secrets)
        nom_certificat = 'pki.instance.cert'
        nom_cle = 'pki.instance.key'
        path_certificat = pathlib.Path(path_secrets, nom_certificat)
        path_cle = pathlib.Path(path_secrets, nom_cle)

        path_cle_old = pathlib.Path(str(path_cle) + '.old')
        path_certificat_old = pathlib.Path(str(path_certificat) + '.old')
        path_cle_work = pathlib.Path(str(path_cle) + '.work')
        path_certificat_work = pathlib.Path(str(path_certificat) + '.work')

        # Conserver le contenu dans des fichiers .work - permet de reduire risque de perte de certificat sur renouvellement
        with open(path_cle_work, 'wb') as fichier:
            fichier.write(clecertificat.private_key_bytes())
        with open(path_certificat_work, 'w') as fichier:
            cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
            fichier.write(cert_str)

        # Preparation a la sauvegarde - rotation de old avec courant
        path_cle_old.unlink(missing_ok=True)
        path_certificat_old.unlink(missing_ok=True)
        try:
            path_cle.rename(path_cle_old)
        except OSError as e:
            if e.errno == errno.ENONET:
                pass  # Fichier original n'existe pas - sauvegarder le nouveau
            else:
                raise e
        try:
            path_certificat.rename(path_certificat_old)
        except OSError as e:
            if e.errno == errno.ENONET:
                pass  # Fichier original n'existe pas - sauvegarder le nouveau
            else:
                raise e

        # Sauvegarder les nouveaux certificats
        path_cle_work.rename(path_cle)
        path_certificat_work.rename(path_certificat)


class CommandeSignatureModule(CommandeSignature):

    def __init__(self, etat_instance, nom_module: str):
        super().__init__(etat_instance)
        self.__nom_module = nom_module

    @property
    def nom_module(self):
        return self.__nom_module

    async def run(self, producer=None):
        raise NotImplementedError('must implement')


class GenerateurCertificatsHandler:

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance
        self.__etat_docker = None
        self.__derniere_notification: Optional[datetime.datetime] = None
        self.__intervalle_notifications = datetime.timedelta(hours=12)

        # Queue de certificats a signer
        self.__q_signer = asyncio.Queue(maxsize=20)

    @property
    def etat_docker(self):
        return self.__etat_docker

    @etat_docker.setter
    def etat_docker(self, etat_docker):
        self.__etat_docker = etat_docker

    async def threads(self):
        tasks = [
            asyncio.create_task(self.thread_entretien()),
            asyncio.create_task(self.thread_signature()),
        ]
        await asyncio.gather(*tasks)

    async def thread_entretien(self):
        """
        Entretien des certificats. Gerer le repertoire de secrets et docker (si disponible).
        """
        while self.__etat_instance.stop_event.is_set() is False:
            self.__logger.debug("thread_entretien Debut entretien")

            try:
                await self.entretien_repertoire_secrets()
            except Exception:
                self.__logger.exception("thread_entretien Erreur entretien_repertoire_secrets")

            if self.__etat_docker is not None:
                try:
                    await self.entretien_docker()
                except Exception:
                    self.__logger.exception("thread_entretien Erreur entretien_repertoire_secrets")

            self.__logger.debug("thread_entretien Fin entretien")
            try:
                await asyncio.wait_for(self.__etat_instance.stop_event.wait(), timeout=900)
            except asyncio.TimeoutError:
                pass  # OK

    async def thread_signature(self):
        pending = {asyncio.create_task(self.__etat_instance.stop_event.wait())}

        while self.__etat_instance.stop_event.is_set() is False:
            pending.add(asyncio.create_task(self.__q_signer.get()))
            done, pending = await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED)
            for d in done:
                if d.exception():
                    self.__logger.exception("thread_signature Erreur task : %s" % d.exception())
                else:
                    result: CommandeSignature = d.result()
                    await self.__signer(result)
                    if result.exception:
                        self.__logger.error("thread_signature Erreur execution commande %s : %s" % (result.__class__, result.exception))

        for p in pending:
            p.cancel()
            try:
                await p
            except asyncio.CancelledError:
                pass  # OK

    async def entretien_repertoire_secrets(self):
        # Detecter expiration certificat instance
        try:
            await self.entretien_certificat_instance()
        except Exception:
            self.__logger.exception("entretien_repertoire_secrets Erreur entretien certificat instance")

        # Verifier certificats de modules

        pass

    async def entretien_docker(self):
        if self.__etat_docker is None:
            raise Exception('etat_docker is None')

        try:
            await nettoyer_configuration_expiree(self.__etat_docker)
        except Exception:
            self.__logger.exception('entretien_docker Erreur nettoyer_configuration_expiree')

    async def entretien_certificat_instance(self):
        enveloppe_instance = self.__etat_instance.clecertificat.enveloppe
        expiration_instance = enveloppe_instance.calculer_expiration()
        if expiration_instance.get('expire') is True:
            self.__logger.error("Certificat d'instance expire (%s), on met l'instance en mode d'attente")
            # Fermer l'instance, elle va redemarrer en mode expire (similare a mode d'installation locked)
            await self.__etat_instance.stop()
        elif expiration_instance.get('renouveler') is True:
            self.__logger.info("Certificat d'instance peut etre renouvele")
            await self.__q_signer.put(CommandeSignatureInstance(self.__etat_instance))

    async def __signer(self, commande: CommandeSignature):
        try:
            await commande.run(self.__etat_instance)
        except Exception as e:
            commande.exception = e
        finally:
            commande.set_done()

    async def sauvegarder_certificat(self, commande: CommandeSignature, reponse: dict):
        pass
