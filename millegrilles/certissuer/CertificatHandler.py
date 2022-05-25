from millegrilles.certissuer.Configuration import ConfigurationWeb


def generer_csr():
    pass


class CertificatHandler:

    def __init__(self, configuration: ConfigurationWeb):
        self.__configuration = configuration

    def generer_certificat_instance(self, csr: str):
        raise NotImplementedError('todo')
