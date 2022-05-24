import logging

from os import path
from typing import Optional

from millegrilles.instance.Certificats import preparer_certificats_web
from millegrilles.instance.Configuration import ConfigurationInstance


class EtatInstance:

    def __init__(self, configuration: ConfigurationInstance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__configuration = configuration

        self.__instance_id: Optional[str] = None
        self.__niveau_securite: Optional[str] = None
        self.__idmg: Optional[str] = None

    def reload_configuration(self):
        self.__logger.info("Reload configuration sur disque ou dans docker")

        # Generer les certificats web self-signed au besoin
        path_cert_web, path_cle_web = preparer_certificats_web(self.__configuration.path_secrets)
        self.__configuration.path_certificat_web = path_cert_web
        self.__configuration.path_cle_web = path_cle_web

        path_instance_txt = path.join(self.__configuration.path_configuration, 'instance_id.txt')
        with open(path_instance_txt, 'r') as fichier:
            uuid_instance = fichier.read().strip()
        self.__logger.info("Instance id : %s", uuid_instance)
        self.__instance_id = uuid_instance

        try:
            path_securite_txt = path.join(self.__configuration.path_configuration, 'securite.txt')
            with open(path_securite_txt, 'r') as fichier:
                niveau_securite = fichier.read().strip()
            self.__logger.info("Securite : %s", niveau_securite)
            self.__niveau_securite = niveau_securite
        except FileNotFoundError:
            pass

        try:
            idmg_txt = path.join(self.__configuration.path_configuration, 'idmg.txt')
            with open(idmg_txt, 'r') as fichier:
                idmg_str = fichier.read().strip()
            self.__logger.info("IDMG : %s", idmg_str)
            self.__idmg = idmg_str
        except FileNotFoundError:
            pass

    @property
    def instance_id(self):
        return self.__instance_id

    @property
    def niveau_securite(self):
        return self.__niveau_securite

    @property
    def idmg(self):
        return self.__idmg

    @property
    def certissuer_url(self):
        return self.__configuration.certissuer_url
