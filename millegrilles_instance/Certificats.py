import asyncio
import base64
import datetime
import errno
import logging
import math
import pathlib
import secrets
from asyncio import TaskGroup

import docker.errors
from aiohttp import ClientSession
from aiohttp.client_exceptions import ClientConnectorError, ClientResponseError
from docker.errors import APIError
from os import path, stat
from typing import Optional

from millegrilles_instance.Context import InstanceContext, ValueNotAvailable
from millegrilles_instance.Interfaces import GenerateurCertificatsInterface, DockerHandlerInterface
from millegrilles_instance.MaintenanceApplicationService import charger_configuration_docker, \
    charger_configuration_application, update_stale_configuration
from millegrilles_messages.bus.BusContext import ForceTerminateExecution
from millegrilles_messages.bus.PikaMessageProducer import MilleGrillesPikaMessageProducer
from millegrilles_messages.messages import Constantes
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.certificats.CertificatsWeb import generer_self_signed_rsa
from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat, CertificatExpire
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.GenerateursSecrets import GenerateurEd25519, GenerateurRsa
from millegrilles_messages.docker import DockerCommandes
from millegrilles_messages.messages.MessagesModule import MessageProducerFormatteur

from millegrilles_instance import Constantes as ContantesInstance
# from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync


logger = logging.getLogger(__name__)


def preparer_certificats_web(path_secrets: str):

    # Verifier si le certificat web existe (utiliser de preference)
    path_cert_web = path.join(path_secrets, 'pki.web.cert')
    path_key_web = path.join(path_secrets, 'pki.web.key')
    if path.exists(path_cert_web) and path.exists(path_key_web):
        return path_cert_web, path_key_web

    # Verifier si le certificat self-signed existe
    path_cert_webss = path.join(path_secrets, 'pki.webss.cert')
    path_key_webss = path.join(path_secrets, 'pki.webss.key')
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


async def generer_certificats_modules_satellites(producer: MessageProducerFormatteur, etat_instance,
                                                 docker_handler: Optional[DockerHandlerInterface], configuration: dict):
    # S'assurer que tous les certificats sont presents et courants dans le repertoire secrets
    path_secrets = etat_instance.configuration.path_secrets
    for nom_module, value in configuration.items():
        logger.debug("generer_certificats_modules() Verification certificat %s" % nom_module)

        nom_certificat = 'pki.%s.cert' % nom_module
        nom_cle = 'pki.%s.key' % nom_module
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

        if docker_handler is not None:
            await docker_handler.assurer_clecertificat(nom_module, clecertificat, combiner_keycert)


async def nettoyer_configuration_expiree(docker_handler: DockerHandlerInterface):
    commande_config = DockerCommandes.CommandeGetConfigurationsDatees()
    await docker_handler.run_command(commande_config)
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
        command = DockerCommandes.CommandeSupprimerConfiguration(config_name)
        try:
            await docker_handler.run_command(command)
        except APIError as apie:
            if apie.status_code == 400:  # in use
                pass
            elif apie.status_code == 404:  # deja supprime
                pass
            else:
                raise apie

    for secret_name in secret_a_supprimer:
        command = DockerCommandes.CommandeSupprimerSecret(secret_name)
        try:
            await docker_handler.run_command(command)
        except APIError as apie:
            if apie.status_code == 400:  # in use
                pass
            elif apie.status_code == 404:  # deja supprime
                pass
            else:
                raise apie

    pass


async def renouveler_certificat_instance_protege(context: InstanceContext) -> CleCertificat:

    instance_id = context.instance_id

    clecsr = CleCsrGenere.build(cn=instance_id)
    csr_str = clecsr.get_pem_csr()
    commande = {'csr': csr_str}

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = context.formatteur
    message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, commande)

    logger.debug("Demande de signature de certificat pour instance protegee => %s\n%s" % (message_signe, csr_str))
    url_issuer = context.configuration.certissuer_url
    path_csr = path.join(url_issuer, 'renouvelerInstance')
    try:
        async with context.ssl_session() as session:
            async with session.post(path_csr, json=message_signe) as resp:
                resp.raise_for_status()
                reponse = await resp.json()
        certificat = reponse['certificat']

        # Confirmer correspondance entre certificat et cle
        clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
        if clecertificat.cle_correspondent() is False:
            raise Exception("Erreur cert/cle ne correspondent pas")

        logger.debug("Reponse certissuer certificat protege\n%s" % ''.join(certificat))
        return clecertificat
    except (ClientConnectorError, ClientResponseError) as e:
        logger.exception("Certissuer local non disponible, fallback CorePki")
        try:
            producer = await asyncio.wait_for(context.get_producer(), 3)
            return await renouveler_certificat_satellite(producer, context)
        except asyncio.TimeoutError:
            # MQ (producer) non disponible
            raise e


async def renouveler_certificat_satellite(producer: MilleGrillesPikaMessageProducer, context: InstanceContext) -> CleCertificat:

    instance_id = context.instance_id
    niveau_securite = context.securite

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

    path_secrets = context.configuration.path_secrets
    nom_certificat = 'pki.instance.cert'
    nom_cle = 'pki.instance.key'
    path_certificat = path.join(path_secrets, nom_certificat)
    path_cle = path.join(path_secrets, nom_cle)

    # Emettre commande de signature, attendre resultat
    message_reponse = await producer.command(configuration, 'CorePki', 'signerCsr', exchange=Constantes.SECURITE_PUBLIC)
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


async def generer_nouveau_certificat(client_session: ClientSession,
                                     context: InstanceContext,
                                     nom_module: str,
                                     configuration: dict) -> CleCertificat:
    instance_id = context.instance_id
    idmg = context.ca.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = context.hostname
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = context.formatteur
    message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, configuration)

    logger.debug("generer_nouveau_certificat Demande de signature de certificat pour %s => %s\n%s" % (nom_module, message_signe, csr_str))
    url_issuer = context.configuration.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    try:
        async with client_session.post(path_csr, json=message_signe) as resp:
            resp.raise_for_status()
            reponse = await resp.json()

        certificat = reponse['certificat']
    except (ClientConnectorError, ClientResponseError) as e:
        logger.warning("generer_nouveau_certificat Certissuer local non disponible, fallback CorePki (Erreur https : %s)" % str(e))
        try:
            producer = await asyncio.wait_for(context.get_producer(), 2)
            if producer is not None:
                try:
                    message_reponse = await producer.command(
                        configuration, 'CorePki', 'signerCsr', exchange=Constantes.SECURITE_PUBLIC)
                    reponse = message_reponse.parsed
                    certificat = reponse['certificat']
                    logger.info("generer_nouveau_certificat Certificat %s recu via MQ pour" % nom_module)
                except Exception as e:
                    logger.exception(
                        "generer_nouveau_certificat ERRERUR Generation certificat %s : echec creation certificat en https et mq" % nom_module)
                    raise e
            else:
                logger.warning("generer_nouveau_certificat Echec genere certificat en https et producer MQ est None")
                # Producer (MQ) non disponible
                raise e
        except asyncio.TimeoutError:
            # No producer, raise previous error
            raise e

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    logger.debug("generer_nouveau_certificat Reponse certissuer certificat %s\n%s" % (nom_module, ''.join(certificat)))
    return clecertificat


async def demander_nouveau_certificat(producer: MessageProducerFormatteur, context: InstanceContext, nom_module: str,
                                      configuration: dict) -> CleCertificat:
    instance_id = context.instance_id
    idmg = context.ca.idmg
    clecsr = CleCsrGenere.build(instance_id, idmg)
    csr_str = clecsr.get_pem_csr()

    # Preparer configuration dns au besoin
    configuration = configuration.copy()
    try:
        dns = configuration['dns'].copy()
        if dns.get('domain') is True:
            nom_domaine = context.hostname
            hostnames = [nom_domaine]
            if dns.get('hostnames') is not None:
                hostnames.extend(dns['hostnames'])
            dns['hostnames'] = hostnames
            configuration['dns'] = dns
    except KeyError:
        pass

    configuration['csr'] = csr_str

    # Emettre commande de signature, attendre resultat
    niveau_securite = context.securite
    if niveau_securite == '4.secure':
        instance_id = context.instance_id

        clecsr = CleCsrGenere.build(cn=instance_id)
        csr_str = clecsr.get_pem_csr()
        commande = {'csr': csr_str}

        # Signer avec notre certificat (instance), requis par le certissuer
        formatteur_message = context.formatteur
        message_signe, _uuid = formatteur_message.signer_message(Constantes.KIND_DOCUMENT, commande)

        url_issuer = context.configuration.certissuer_url
        path_csr = path.join(url_issuer, 'renouvelerInstance')
        async with context.ssl_session() as session:
            async with session.post(path_csr, json=message_signe) as resp:
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


async def generer_passwords(context: InstanceContext, docker_handler: Optional[DockerHandlerInterface],
                            liste_passwords: list):
    """
    Generer les passwords manquants.
    :param context:
    :param docker_handler:
    :param liste_passwords:
    :return:
    """
    path_secrets = context.configuration.path_secrets
    # if docker_handler is not None:
    #     configurations = await docker_handler.get_configurations_datees()
    #     secrets_dict = configurations['secrets']
    # else:
    #     secrets_dict = dict()

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

        # logger.debug("Date password : %s" % date_password)
        date_password = datetime.datetime.fromtimestamp(date_password)
        date_password_str = date_password.strftime('%Y%m%d%H%M%S')

        # label_passord = '%s.%s' % (prefixe, date_password_str)

        # Ajouter mot de passe
        if docker_handler is not None:
            try:
                await docker_handler.ajouter_password(label, date_password_str, password)
            except docker.errors.APIError as e:
                if e.errno == 409:
                    pass  # Password already exists - OK
                else:
                    raise e

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

    def __init__(self, context: InstanceContext, docker_handler: DockerHandlerInterface):
        self._context = context
        self._docker_handler: DockerHandlerInterface = docker_handler
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
    def result(self):
        return self.__result

    async def done(self, timeout=120):
        await asyncio.wait_for(self.__event_done.wait(), timeout=timeout)
        if self.__exception:
            raise self.__exception
        return self.__result

    async def run_command(self):
        try:
            self.__result = await self._run()
        except Exception as e:
            self.__exception = e

        self.__event_done.set()

    async def _run(self):
        raise NotImplementedError('must implement')


def sauvegarder_clecert(path_secrets: pathlib.Path, nom_module: str, clecertificat: CleCertificat,
                        combiner_keycert=False):
    nom_certificat = f'pki.{nom_module}.cert'
    nom_cle = f'pki.{nom_module}.key'
    path_certificat = pathlib.Path(path_secrets, nom_certificat)
    path_cle = pathlib.Path(path_secrets, nom_cle)

    path_cle_old = pathlib.Path(str(path_cle) + '.old')
    path_certificat_old = pathlib.Path(str(path_certificat) + '.old')
    path_cle_work = pathlib.Path(str(path_cle) + '.work')
    path_certificat_work = pathlib.Path(str(path_certificat) + '.work')

    # Conserver le contenu dans des fichiers .work - permet de reduire risque de perte de certificat sur renouvellement
    cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
    with open(path_cle_work, 'wb') as fichier:
        fichier.write(clecertificat.private_key_bytes())
        if combiner_keycert is True:
            fichier.write(cert_str.encode('utf-8'))
    with open(path_certificat_work, 'w') as fichier:
        fichier.write(cert_str)

    # Preparation a la sauvegarde - rotation de old avec courant
    path_cle_old.unlink(missing_ok=True)
    path_certificat_old.unlink(missing_ok=True)
    try:
        path_cle.rename(path_cle_old)
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass  # Fichier original n'existe pas - sauvegarder le nouveau
        else:
            raise e
    try:
        path_certificat.rename(path_certificat_old)
    except OSError as e:
        if e.errno == errno.ENOENT:
            pass  # Fichier original n'existe pas - sauvegarder le nouveau
        else:
            raise e

    # Sauvegarder les nouveaux certificats
    path_cle_work.rename(path_cle)
    path_certificat_work.rename(path_certificat)


class CommandeSignatureInstance(CommandeSignature):

    def __init__(self, context: InstanceContext, docker_handler: DockerHandlerInterface):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        super().__init__(context, docker_handler)

    async def _run(self):
        try:
            producer = await self._context.get_producer()
        except Exception as e:
            self.__logger.info("Producer (MQ) non disponible, utiliser MQ")
            producer = None

        clecertificat = await renouveler_certificat_instance_protege(self._context)

        if clecertificat is not None:
            await self.sauvegarder_clecert(clecertificat)

            # Reload configuration avec le nouveau certificat
            self.__logger.info("CommandeSignatureInstance.run Nouveau certificat d'instance installe - reload configuration")
            await self._context.reload_wait()

            return clecertificat

    async def sauvegarder_clecert(self, clecertificat: CleCertificat):
        path_secrets = pathlib.Path(self._context.configuration.path_secrets)
        nom_certificat = 'pki.instance.cert'
        nom_cle = 'pki.instance.key'
        path_certificat = pathlib.Path(path_secrets, nom_certificat)
        path_cle = pathlib.Path(path_secrets, nom_cle)

        path_cle_old = pathlib.Path(str(path_cle) + '.old')
        path_certificat_old = pathlib.Path(str(path_certificat) + '.old')
        path_cle_work = pathlib.Path(str(path_cle) + '.work')
        path_certificat_work = pathlib.Path(str(path_certificat) + '.work')

        # Conserver le contenu dans des fichiers .work.
        # Permet de reduire risque de perte de certificat sur renouvellement
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
            if e.errno == errno.ENOENT:
                pass  # Fichier original n'existe pas - sauvegarder le nouveau
            else:
                raise e
        try:
            path_certificat.rename(path_certificat_old)
        except OSError as e:
            if e.errno == errno.ENOENT:
                pass  # Fichier original n'existe pas - sauvegarder le nouveau
            else:
                raise e

        # Sauvegarder les nouveaux certificats
        path_cle_work.rename(path_cle)
        path_certificat_work.rename(path_certificat)


class CommandeSignatureModule(CommandeSignature):

    def __init__(self, context: InstanceContext, docker_handler: DockerHandlerInterface, nom_module: str,
                 configuration: Optional[dict] = None):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        super().__init__(context, docker_handler)
        self._nom_module = nom_module
        self._configuration = configuration

    @property
    def nom_module(self):
        return self._configuration['module']

    async def _run(self):
        async with self._context.ssl_session() as session:
            value = self._configuration or dict()
            nom_local_certificat = value.get('nom') or self._nom_module

            clecertificat = await generer_nouveau_certificat(session, self._context, nom_local_certificat, value)

        path_secrets = pathlib.Path(self._context.configuration.path_secrets)
        sauvegarder_clecert(path_secrets, nom_local_certificat, clecertificat)

        if self._docker_handler:
            combiner_keycert = value.get('combiner_keycert') or False
            await self._docker_handler.assurer_clecertificat(
                nom_local_certificat, clecertificat, combiner_keycert)

        return clecertificat


class CommandeRotationMaitredescles(CommandeSignatureModule):

    def __init__(self, context: InstanceContext, docker_handler: DockerHandlerInterface, nom_module: str,
                 configuration: Optional[dict] = None,
                 enveloppe_courante: Optional[EnveloppeCertificat] = None):
        super().__init__(context, docker_handler, nom_module, configuration)
        self.__enveloppe_courante = enveloppe_courante

    async def _run(self):
        async with self._context.ssl_session() as session:
            value = self._configuration or dict()
            nom_local_certificat = value.get('nom') or self._nom_module

            clecertificat = await generer_nouveau_certificat(
                session, self._context, nom_local_certificat, value)

        # Executer une rotation du certificat - le maitre des cles va chiffrer la cle symmetrique pour
        # ce nouveau certificat. Permet de continuer au demarrage avec le nouveau certificat sans
        # interruptions.
        if self.__enveloppe_courante:
            producer = await self._context.get_producer()
            fingerprint = self.__enveloppe_courante.fingerprint
            commande = {
                'certificat': clecertificat.enveloppe.chaine_pem(),
            }
            reponse = await producer.command(
                commande, 'MaitreDesCles', 'rotationCertificat',
                exchange='3.protege',
                partition=fingerprint
            )
            if reponse.parsed['ok'] is False:
                raise Exception('erreur de rotation du certificat de maitre des cles')

        path_secrets = pathlib.Path(self._context.configuration.path_secrets)
        sauvegarder_clecert(path_secrets, nom_local_certificat, clecertificat)

        if self._docker_handler:
            combiner_keycert = value.get('combiner_keycert') or False
            await self._docker_handler.assurer_clecertificat(
                nom_local_certificat, clecertificat, combiner_keycert)

        return clecertificat


class GenerateurCertificatsHandler(GenerateurCertificatsInterface):

    def __init__(self, context: InstanceContext, docker_handler: Optional[DockerHandlerInterface]):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__docker_handler = docker_handler
        self.__derniere_notification: Optional[datetime.datetime] = None
        self.__intervalle_notifications = datetime.timedelta(hours=12)

        # Queue de certificats a signer
        self.__q_signer: asyncio.Queue[Optional[CommandeSignature]] = asyncio.Queue(maxsize=20)

        # Fonction qui retourne un dict des modules pour entretien
        self.__get_configuration_modules = None

        self.__event_setup_initial_certificats = asyncio.Event()

    def set_configuration_modules_getter(self, getter):
        self.__get_configuration_modules = getter

    @property
    def event_entretien_initial(self):
        return self.__event_setup_initial_certificats

    async def run(self):
        self.__logger.debug("GenerateurCertificatsHandler thread started")
        try:
            async with TaskGroup() as group:
                group.create_task(self.thread_entretien())
                group.create_task(self.__thread_signature())
                group.create_task(self.__stop_thread())
        except *Exception as e:  # Stop on any thread exception
            if self.__context.stopping is False:
                self.__logger.exception("GenerateurCertificatsHandler Unhandled error, closing")
                self.__context.stop()
                raise ForceTerminateExecution()
            else:
                raise e
        self.__logger.debug("GenerateurCertificatsHandler thread done")

    async def thread_entretien(self):
        """
        Entretien des certificats. Gerer le repertoire de secrets et services docker (si disponible).
        """
        while self.__context.stopping is False:
            self.__logger.debug("thread_entretien Debut entretien")

            try:
                await self.entretien_repertoire_secrets()
            except CertificatExpire:
                self.__logger.warning("Instance certificate expired")
                await self.__context.wait(30)
                continue
            except Exception:
                self.__logger.exception("thread_entretien Erreur entretien_repertoire_secrets")

            if self.__docker_handler is not None:
                try:
                    # Apply all the new certificates to existing docker services
                    await self.entretien_modules()
                except Exception:
                    self.__logger.exception("thread_entretien Erreur entretien_repertoire_secrets")

            self.__event_setup_initial_certificats.set()

            self.__logger.debug("thread_entretien Fin entretien")
            await self.__context.wait(ContantesInstance.INTERVALLE_VERIFIER_CERTIFICATS)

    async def __stop_thread(self):
        await self.__context.wait()
        await self.__q_signer.put(None)  # Exit condition
        self.__event_setup_initial_certificats.set()

    async def __thread_signature(self):
        while self.__context.stopping is False:
            command = await self.__q_signer.get()
            if command is None:
                return  # Exit condition
            try:
                await self.__signer(command)
            except:
                self.__logger.exception("Error signing request")

    async def entretien_repertoire_secrets(self):
        # Detecter expiration certificat instance
        try:
            await self.entretien_certificat_instance()
        except CertificatExpire as e:
            raise e
        except asyncio.CancelledError as e:
            raise e
        except Exception:
            self.__logger.exception("entretien_repertoire_secrets Erreur entretien certificat instance")

    async def entretien_modules(self):

        if self.__context.application_status.required_modules is None:
            self.__logger.info("entretien_modules Premature modules maintenance, modules not loaded")
            return

        # Verifier certificats de modules
        try:
            await self.generer_commandes_modules()
            await self.entretien_passwords_modules()
        except Exception:
            self.__logger.exception("entretien_docker Erreur generer_commandes_modules")

        if self.__docker_handler is not None:
            # Entretien config/secrets
            try:
                await nettoyer_configuration_expiree(self.__docker_handler)
            except Exception:
                self.__logger.exception('entretien_docker Erreur nettoyer_configuration_expiree')

        # Reconfigure all modules with the most recent docker config/secret information
        await update_stale_configuration(self.__context, self.__docker_handler)

    async def entretien_certificat_instance(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            return  # Installation mode

        try:
            enveloppe_instance = self.__context.signing_key.enveloppe
        except AttributeError:
            # Certificate is expired/invalid, it was not
            raise CertificatExpire()

        expiration_instance = enveloppe_instance.calculer_expiration()
        if expiration_instance.get('expire') is True:
            self.__logger.info("entretien_certificat_instance Instance certificate has expired.")
            raise CertificatExpire()

        elif expiration_instance.get('renouveler') is True:
            self.__logger.info("Certificat d'instance peut etre renouvele")
            await self.__q_signer.put(CommandeSignatureInstance(self.__context, self.__docker_handler))

    async def __signer(self, commande: CommandeSignature):
        try:
            await commande.run_command()
        except Exception as e:
            commande.exception = e
        finally:
            commande.set_done()  # S'assurer que done est set, e.g. apres exception

    async def generer_commandes_modules(self):
        configuration = await get_configuration_certificats(self.__context)

        # Verifier certificats de module dans le repertoire secret. Generer commandes si necessaire.
        path_secrets = self.__context.configuration.path_secrets
        for nom_module, value in configuration.items():
            self.__logger.debug("generer_commandes_modules Verification certificat %s" % nom_module)

            nom_certificat = 'pki.%s.cert' % nom_module
            nom_cle = 'pki.%s.key' % nom_module
            path_certificat = path.join(path_secrets, nom_certificat)
            path_cle = path.join(path_secrets, nom_cle)
            try:
                combiner_certificat = value['combiner_keycert'] is True
            except KeyError:
                combiner_certificat = False

            doit_generer = False
            detail_expiration = dict()
            roles = list()
            clecertificat = None
            try:
                clecertificat = CleCertificat.from_files(path_cle, path_certificat)
                enveloppe = clecertificat.enveloppe
                roles = enveloppe.get_roles or roles

                # Ok, verifier si le certificat doit etre renouvele
                detail_expiration = enveloppe.calculer_expiration()
                if detail_expiration['expire'] is True or detail_expiration['renouveler'] is True:
                    doit_generer = True

            except FileNotFoundError:
                self.__logger.debug("generer_commandes_modules Certificat %s non trouve, on le genere" % nom_module)
                doit_generer = True
                enveloppe = None

            if doit_generer:
                self.__logger.debug("generer_commandes_modules Generer nouveau certificat pour %s" % nom_module)
                if 'maitredescles' in roles:
                    expire = detail_expiration.get('expire')
                    if expire is None:
                        expire = True
                    if expire is not True:
                        enveloppe_requete = enveloppe
                    else:
                        enveloppe_requete = None
                    commande = CommandeRotationMaitredescles(
                        self.__context, self.__docker_handler, nom_module, value, enveloppe_requete)
                else:
                    commande = CommandeSignatureModule(self.__context, self.__docker_handler, nom_module, value)
                await self.__q_signer.put(commande)

                try:
                    await commande.done()
                    clecertificat = CleCertificat.from_files(path_cle, path_certificat)
                except asyncio.CancelledError as e:
                    raise e
                except:
                    self.__logger.exception("Error generating new certificate for %s", nom_module)

            if clecertificat and self.__docker_handler:
                await self.__docker_handler.assurer_clecertificat(nom_module, clecertificat, combiner_certificat)

    async def entretien_passwords_modules(self):
        try:
            securite = self.__context.securite
        except ValueNotAvailable:
            return  # Installation mode

        list_passwds = await get_configuration_passwords(self.__context)
        self.__logger.debug("generer_passwords_modules Verification liste passwds %s" % list_passwds)
        await generer_passwords(self.__context, self.__docker_handler, list_passwds)

    async def demander_signature(self, nom_module: str, params: Optional[dict] = None, timeout=45):
        commande = CommandeSignatureModule(self.__context, self.__docker_handler, nom_module, params)
        await self.__q_signer.put(commande)
        return await commande.done(timeout)


async def get_configuration_certificats(context: InstanceContext) -> dict:
    path_configuration = context.configuration.path_configuration
    path_configuration_docker = pathlib.Path(path_configuration, 'docker')
    config_modules = context.application_status.required_modules

    # map configuration certificat
    config_certificats = dict()

    configurations = await charger_configuration_docker(path_configuration_docker, config_modules)
    for dep in configurations:
        try:
            certificat = dep['certificat']
            nom = dep['name']
            config_certificats[nom] = certificat
        except KeyError:
            pass

    configurations_apps = await charger_configuration_application(path_configuration_docker)
    for app_configuration in configurations_apps:
        try:
            for dep in app_configuration['dependances']:
                certificat = dep['certificat']
                nom = dep['name']
                config_certificats[nom] = certificat
        except (TypeError, KeyError):
            pass

    return config_certificats


async def get_configuration_passwords(context: InstanceContext) -> list:
    path_configuration = context.configuration.path_configuration
    path_configuration_docker = pathlib.Path(path_configuration, 'docker')
    config_modules = context.application_status.required_modules
    configurations = await charger_configuration_docker(path_configuration_docker, config_modules)
    configurations_apps = await charger_configuration_application(path_configuration_docker)
    configurations.extend(configurations_apps)

    # map configuration certificat
    liste_noms_passwords = list()
    for c in configurations:
        try:
            p = c.get('generateur') or c['passwords']
            liste_noms_passwords.extend(p)
        except KeyError:
            pass

    return liste_noms_passwords
