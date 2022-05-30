import os

import logging

from os import path, makedirs


class EntretienCatalogues:

    def __init__(self, etat_instance):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__etat_instance = etat_instance

        self.__entretien_initial_complete = False
        self.__repertoire_catalogues_pret = False

    async def entretien(self):
        self.__logger.debug("entretien catalogues debut")

        try:
            if self.__entretien_initial_complete is False:
                await self.preparer_catalogues()

        except Exception as e:
            self.__logger.exception("Erreur entretien catalogues")

        self.__logger.debug("entretien catalogues fin")

    async def preparer_catalogues(self):
        self.__logger.info("Preparer catalogues")
        self.verifier_repertoire_configuration()
        self.__entretien_initial_complete = True
        self.__logger.info("Catalogues prets")

    def verifier_repertoire_configuration(self):
        path_catalogues = self.__etat_instance.configuration.path_catalogues
        makedirs(path_catalogues, 0o755, exist_ok=True)

        # Verifier existance de la configuration de modules nginx
        self.copier_catalogues()

    def copier_catalogues(self):
        path_catalogues = self.__etat_instance.configuration.path_catalogues

        # Faire liste des fichiers de catalogues (source)
        repertoire_src_catalogues = path.abspath('../etc/catalogues')

        for fichier in os.listdir(repertoire_src_catalogues):
            # Verifier si le fichier existe dans la destination
            path_destination = path.join(path_catalogues, fichier)
            if path.exists(path_destination) is False:
                self.__logger.info("Copier fichier catalogue %s" % fichier)
                path_source = path.join(repertoire_src_catalogues, fichier)
                with open(path_source, 'rb') as fichier_source:
                    with open(path_destination, 'wb') as fichier_destination:
                        fichier_destination.write(fichier_source.read())
