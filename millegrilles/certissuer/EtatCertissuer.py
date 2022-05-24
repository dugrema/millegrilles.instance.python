import logging

from typing import Optional

from millegrilles.certificats.CertificatsMillegrille import generer_csr_intermediaire
from millegrilles.certificats.Generes import CleCsrGenere
from millegrilles.certissuer.Configuration import ConfigurationCertissuer


class EtatCertissuer:

    def __init__(self, configuration: ConfigurationCertissuer):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration
        self.__csr: Optional[CleCsrGenere] = None

    def get_csr(self) -> str:
        if self.__csr is None:
            instance_id = self.__configuration.instance_id
            self.__csr = generer_csr_intermediaire(instance_id)

        return self.__csr.get_pem_csr()
