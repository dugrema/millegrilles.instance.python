from os import path


def preparer_certificats_web(path_secrets: str):

    # Verifier si le certificat web existe (utiliser de preference)
    path_cert_web = path.join(path_secrets, 'pki.web.cert')
    path_key_web = path.join(path_secrets, 'pki.web.key')
    if path.exists(path_cert_web) and path.exists(path_key_web):
        return path_cert_web, path_key_web

    # Verifier si le certificat self-signed existe
    path_cert_web = path.join(path_secrets, 'pki.webss.cert')
    path_key_web = path.join(path_secrets, 'pki.webss.key')
    if path.exists(path_cert_web) and path.exists(path_key_web):
        return path_cert_web, path_key_web

    # Generer certificat self-signed


    return path_cert_web, path_key_web


def generer_certificat_nginx_selfsigned(insecure=False):
    """
    Utilise pour genere un certificat self-signed initial pour nginx
    :return:
    """
    generateur = GenerateurCertificatNginxSelfsigned()

    clecert_ed25519 = generateur.generer('Installation')
    cle_pem_bytes_ed25519 = clecert_ed25519.private_key_bytes
    cert_pem_ed25519 = clecert_ed25519.public_bytes

    clecert_web = generateur.generer('Installation', rsa=True)
    cle_pem_web = clecert_web.private_key_bytes
    cert_pem_web = clecert_web.public_bytes

    # # Certificat interne
    # self.ajouter_secret('pki.nginx.key', data=cle_pem_bytes_ed25519)
    # self.ajouter_config('pki.nginx.cert', data=cert_pem_ed25519)
    #
    # # Certificat web
    # self.ajouter_secret('pki.web.key', data=cle_pem_web)
    # self.ajouter_config('pki.web.cert', data=cert_pem_web)

    key_path = path.join(self.secret_path, 'pki.nginx.key.pem')
    try:
        with open(key_path, 'xb') as fichier:
            fichier.write(cle_pem_bytes_ed25519)
    except FileExistsError:
        pass

    key_path = path.join(self.secret_path, 'pki.web.key.pem')
    try:
        with open(key_path, 'xb') as fichier:
            fichier.write(cle_pem_web)
    except FileExistsError:
        pass

    return clecert_ed25519


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
