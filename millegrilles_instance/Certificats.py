import base64
import datetime
import logging
import math
import secrets

from aiohttp import ClientSession
from os import path, stat

from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.certificats.Generes import CleCsrGenere
from millegrilles_messages.certificats.CertificatsWeb import generer_self_signed_rsa
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_messages.GenerateursSecrets import GenerateurEd25519, GenerateurRsa


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
        certificat = ''.join(clecertificat_genere.get_pem_certificat())
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
    with open(path_key_web, 'w') as fichier:
        fichier.write(clecertificat_genere.get_pem_cle())

    return path_cert_web, path_key_web


async def generer_certificats_modules(client_session: ClientSession, etat_instance,
                                      etat_docker: EtatDockerInstanceSync, configuration: dict):
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

        await etat_docker.assurer_clecertificat(nom_module, clecertificat, combiner_keycert)


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
            nom_domaine = etat_instance.nom_domaine
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


async def generer_passwords(etat_instance, etat_docker: EtatDockerInstanceSync,
                            liste_passwords: list):
    """
    Generer les passwords manquants.
    :param etat_instance:
    :param etat_docker:
    :param liste_noms_passwords:
    :return:
    """
    path_secrets = etat_instance.configuration.path_secrets
    configurations = await etat_docker.get_configurations_datees()
    secrets_dict = configurations['secrets']

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


# def generer_certificat_nginx_selfsigned(insecure=False):
#     """
#     Utilise pour genere un certificat self-signed initial pour nginx
#     :return:
#     """
#     generateur = GenerateurCertificatNginxSelfsigned()
#
#     clecert_ed25519 = generateur.generer('Installation')
#     cle_pem_bytes_ed25519 = clecert_ed25519.private_key_bytes
#     cert_pem_ed25519 = clecert_ed25519.public_bytes
#
#     clecert_web = generateur.generer('Installation', rsa=True)
#     cle_pem_web = clecert_web.private_key_bytes
#     cert_pem_web = clecert_web.public_bytes
#
#     # # Certificat interne
#     # self.ajouter_secret('pki.nginx.key', data=cle_pem_bytes_ed25519)
#     # self.ajouter_config('pki.nginx.cert', data=cert_pem_ed25519)
#     #
#     # # Certificat web
#     # self.ajouter_secret('pki.web.key', data=cle_pem_web)
#     # self.ajouter_config('pki.web.cert', data=cert_pem_web)
#
#     key_path = path.join(self.secret_path, 'pki.nginx.key.pem')
#     try:
#         with open(key_path, 'xb') as fichier:
#             fichier.write(cle_pem_bytes_ed25519)
#     except FileExistsError:
#         pass
#
#     key_path = path.join(self.secret_path, 'pki.web.key.pem')
#     try:
#         with open(key_path, 'xb') as fichier:
#             fichier.write(cle_pem_web)
#     except FileExistsError:
#         pass
#
#     return clecert_ed25519


# class GenerateurCertificatNginxSelfsigned:
#     """
#     Genere un certificat self-signed pour Nginx pour l'installation d'un nouveau noeud.
#     """
#
#     def generer(self, server_name: str, rsa=False):
#         clecert = EnveloppeCleCert()
#         if rsa is True:
#             clecert.generer_private_key(generer_password=False, keysize=2048)
#         else:
#             # Va utilise type par defaut (EdDSA25519)
#             clecert.generer_private_key(generer_password=False)
#
#         public_key = clecert.private_key.public_key()
#         builder = x509.CertificateBuilder()
#         builder = builder.not_valid_before(datetime.datetime.utcnow() - ConstantesGenerateurCertificat.DELTA_INITIAL)
#         builder = builder.not_valid_after(datetime.datetime.utcnow() + ConstantesGenerateurCertificat.DUREE_CERT_INSTALLATION)
#         builder = builder.serial_number(x509.random_serial_number())
#         builder = builder.public_key(public_key)
#
#         builder = builder.add_extension(
#             x509.SubjectKeyIdentifier.from_public_key(public_key),
#             critical=False
#         )
#
#         name = x509.Name([
#             x509.NameAttribute(x509.name.NameOID.ORGANIZATION_NAME, u'MilleGrille'),
#             x509.NameAttribute(x509.name.NameOID.COMMON_NAME, server_name),
#         ])
#         builder = builder.subject_name(name)
#         builder = builder.issuer_name(name)
#
#         builder = builder.add_extension(
#             x509.BasicConstraints(ca=True, path_length=0),
#             critical=True,
#         )
#
#         ski = x509.SubjectKeyIdentifier.from_public_key(clecert.private_key.public_key())
#         builder = builder.add_extension(
#             x509.AuthorityKeyIdentifier(
#                 ski.digest,
#                 None,
#                 None
#             ),
#             critical=False
#         )
#
#         if rsa is True:
#             certificate = builder.sign(
#                 private_key=clecert.private_key,
#                 algorithm=hashes.SHA512(),
#                 backend=default_backend()
#             )
#         else:
#             certificate = builder.sign(
#                 private_key=clecert.private_key,
#                 algorithm=None,
#                 backend=default_backend()
#             )
#
#         clecert.set_cert(certificate)
#
#         return clecert
