import base64
import datetime
import logging
import math
import secrets

from aiohttp import ClientSession
from docker.errors import APIError
from os import path, stat
from typing import Optional

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
        fichier.write(clecertificat_genere.private_key_bytes())

    return path_cert_web, path_key_web


async def generer_certificats_modules(client_session: ClientSession, etat_instance, configuration: dict,
                                      etat_docker: Optional[EtatDockerInstanceSync] = None):
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
                roles = enveloppe.get_roles
                if 'maitredescles' in roles:
                    # Verifier si on est en cours de rotation d'un certificat de maitre des cles
                    # Il faut laisser le temps aux cles de finir d'etre rechiffrees
                    if detail_expiration['expire'] is True or etat_instance.is_rotation_maitredescles() is False:
                        clecertificat = await generer_nouveau_certificat(
                            client_session, etat_instance, nom_module, value)
                        sauvegarder = True
                        etat_instance.set_rotation_maitredescles()
                else:
                    clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
                    sauvegarder = True

        except FileNotFoundError:
            logger.info("Certificat %s non trouve, on le genere" % nom_module)
            clecertificat = await generer_nouveau_certificat(client_session, etat_instance, nom_module, value)
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
        current_config = element_config['current']
        set_names_courants = set([v['name'] for v in current_config.values()])

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


async def renouveler_certificat_instance_protege(client_session: ClientSession, etat_instance) -> CleCertificat:

    instance_id = etat_instance.instance_id

    clecsr = CleCsrGenere.build(cn=instance_id)
    csr_str = clecsr.get_pem_csr()
    commande = {'csr_instance': csr_str}

    # Signer avec notre certificat (instance), requis par le certissuer
    formatteur_message = etat_instance.formatteur_message
    message_signe, _uuid = formatteur_message.signer_message(commande)

    logger.debug("Demande de signature de certificat pour instance protegee => %s\n%s" % (message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'renouvelerInstance')
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


async def renouveler_certificat_satellite(producer: MessageProducerFormatteur, etat_instance) -> CleCertificat:

    instance_id = etat_instance.instance_id

    clecsr = CleCsrGenere.build(cn=instance_id)
    csr_str = clecsr.get_pem_csr()
    configuration = {'csr_instance': csr_str, 'roles': ['instance']}

    path_secrets = etat_instance.configuration.path_secrets
    nom_certificat = 'pki.instance.cert'
    nom_cle = 'pki.instance.key'
    path_certificat = path.join(path_secrets, nom_certificat)
    path_cle = path.join(path_secrets, nom_cle)

    # Emettre commande de signature, attendre resultat
    niveau_securite = etat_instance.niveau_securite
    message_reponse = await producer.executer_commande(configuration, 'CorePki', 'signerCsr', exchange=niveau_securite)
    reponse = message_reponse.parsed

    certificat = reponse['certificat']

    # Confirmer correspondance entre certificat et cle
    clecertificat = CleCertificat.from_pems(clecsr.get_pem_cle(), ''.join(certificat))
    if clecertificat.cle_correspondent() is False:
        raise Exception("Erreur cert/cle ne correspondent pas")

    cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
    with open(path_cle, 'wb') as fichier:
        fichier.write(clecertificat.private_key_bytes())
    with open(path_certificat, 'w') as fichier:
        cert_str = '\n'.join(clecertificat.enveloppe.chaine_pem())
        fichier.write(cert_str)

    logger.debug("Reponse certissuer certificat satellite\n%s" % ''.join(certificat))
    return clecertificat


async def generer_nouveau_certificat(client_session: ClientSession, etat_instance, nom_module: str,
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
    message_signe, _uuid = formatteur_message.signer_message(configuration)

    logger.debug("Demande de signature de certificat pour %s => %s\n%s" % (nom_module, message_signe, csr_str))
    url_issuer = etat_instance.certissuer_url
    path_csr = path.join(url_issuer, 'signerModule')
    async with client_session.post(path_csr, json=message_signe) as resp:
        resp.raise_for_status()
        reponse = await resp.json()

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
        commande = {'csr_instance': csr_str}

        # Signer avec notre certificat (instance), requis par le certissuer
        formatteur_message = etat_instance.formatteur_message
        message_signe, _uuid = formatteur_message.signer_message(commande)

        url_issuer = etat_instance.certissuer_url
        path_csr = path.join(url_issuer, 'renouvelerInstance')
        client_session = etat_instance.client_session
        async with client_session.post(path_csr, json=message_signe) as resp:
            resp.raise_for_status()
            reponse = await resp.json()

        certificat = reponse['certificat']
    else:
        message_reponse = await producer.executer_commande(configuration, 'CorePki', 'signerCsr', exchange=niveau_securite)
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

