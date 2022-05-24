import logging

from os import path, remove
from typing import Optional

from millegrilles.certificats.CertificatsMillegrille import generer_csr_intermediaire
from millegrilles.certificats.Generes import CleCsrGenere
from millegrilles.certissuer.Configuration import ConfigurationCertissuer
from millegrilles.messages.EnveloppeCertificat import EnveloppeCertificat
from millegrilles.messages.CleCertificat import CleCertificat
from millegrilles.messages.ValidateurCertificats import ValidateurCertificat


class EtatCertissuer:

    def __init__(self, configuration: ConfigurationCertissuer):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__csr: Optional[CleCsrGenere] = None

        self.__idmg: Optional[str] = None
        self.__ca: Optional[EnveloppeCertificat] = None
        self.__cle_intermediaire: Optional[CleCertificat] = None
        self.__validateur: Optional[ValidateurCertificat] = None

        self.charger_init()

    def charger_init(self):
        path_certissuer = self.__configuration.path_certissuer
        path_ca = path.join(path_certissuer, 'millegrille.pem')
        try:
            self.__ca = EnveloppeCertificat.from_file(path_ca)
            self.__validateur = ValidateurCertificat(self.__ca)
        except FileNotFoundError:
            pass

        path_cert = path.join(path_certissuer, 'cert.pem')
        path_cle = path.join(path_certissuer, 'key.pem')
        path_password = path.join(path_certissuer, 'password.txt')
        try:
            cle_intermediaire = CleCertificat.from_files(path_cle, path_cert, path_password)
            if cle_intermediaire.cle_correspondent():
                self.__cle_intermediaire = cle_intermediaire
            else:
                # Cleanup, le cert/cle ne correspondent pas
                remove(path_cle)
                remove(path_cert)
                remove(path_password)
        except FileNotFoundError:
            pass

    def get_csr(self) -> str:
        if self.__csr is None:
            instance_id = self.__configuration.instance_id
            self.__csr = generer_csr_intermediaire(instance_id)

        return self.__csr.get_pem_csr()

    def sauvegarder_certificat(self, info_cert: dict):
        cle_pem = self.__csr.get_pem_cle()
        password = self.__csr.password
        cert_ca = info_cert['ca']
        cert_pem = info_cert['intermediaire']

        path_certissuer = self.__configuration.path_certissuer

        if self.__validateur is not None:
            # Valider le certificat intermediaire. Doit correspondre au cert CA de la millegrille.
            self.__validateur.valider(cert_pem)
        else:
            enveloppe_ca = EnveloppeCertificat.from_pem(cert_ca)
            if enveloppe_ca.is_root_ca is False:
                raise Exception("Certificat CA n'est pas root")

            if self.__idmg is not None:
                if self.__idmg != enveloppe_ca.idmg:
                    raise Exception("Mismatch idmg avec systeme local et cert CA recu")
            else:
                # On n'a pas de lock pour la millegrille, on accepte le nouveau certificat
                path_ca = path.join(path_certissuer, 'millegrille.pem')
                with open(path_ca, 'w') as fichier:
                    fichier.write(cert_ca)

        path_cle = path.join(path_certissuer, 'key.pem')
        path_cert = path.join(path_certissuer, 'cert.pem')
        path_password = path.join(path_certissuer, 'password.txt')
        with open(path_cert, 'w') as fichier:
            fichier.write(cert_pem)
        with open(path_cle, 'w') as fichier:
            fichier.write(cle_pem)
        with open(path_password, 'w') as fichier:
            fichier.write(password)
