#!/usr/bin/python3
import json
import lzma
import logging
import argparse
import tarfile
import tempfile

from os import listdir, path, mkdir, unlink
from base64 import b64encode

from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages.FormatteurMessages import SignateurTransactionSimple, FormatteurMessageMilleGrilles


class Generateur:

    def __init__(self, args):
        self._args = args

        # Charger signateur de transaction
        PATH_CA = '/var/opt/millegrilles/configuration/pki.millegrille.cert'
        PATH_CORE_CERT = '/var/opt/millegrilles/secrets/pki.core.cert'
        PATH_CORE_CLE = '/var/opt/millegrilles/secrets/pki.core.cle'

        with open(PATH_CA, 'r') as fichier:
            self.__cert_millegrille = fichier.read()

        self.__repertoire_catalogues = path.abspath('../etc/catalogues')

        clecert = CleCertificat.from_files(PATH_CORE_CLE, PATH_CORE_CERT)
        enveloppe = clecert.enveloppe
        idmg = enveloppe.idmg

        signateur = SignateurTransactionSimple(clecert)
        self._formatteur = FormatteurMessageMilleGrilles(idmg, signateur)

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

    def generer_catalogue_applications(self):
        """
        Genere les fichiers de configuration d'application et le fichier de catalogue d'applications
        :return:
        """
        path_catalogues = path.join(self._args.path or self.__repertoire_catalogues)

        path_archives_application = path_catalogues
        try:
            mkdir(path_archives_application)
        except FileExistsError:
            pass

        catalogue_apps = dict()
        fpconfig, path_config_temp = tempfile.mkstemp()
        for rep, config in IterateurApplications(path_catalogues):
            nom_application = config['nom']
            self.__logger.debug("Repertoire : %s" % rep)
            catalogue_apps[nom_application] = {
                'version': config['version']
            }

            # Verifier si on doit creer une archive tar pour cette application
            # Tous les fichiers sauf docker.json sont inclus et sauvegarde sous une archive tar.xz
            # dans l'entree de catalogue
            fichier_app = [f for f in listdir(rep) if f not in ['docker.json']]
            if len(fichier_app) > 0:
                with tarfile.open(path_config_temp, 'w:xz') as fichier:
                    # Faire liste de tous les fichiers de configuration de l'application
                    # (exclure docker.json - genere separement)
                    for filename in fichier_app:
                        file_path = path.join(rep, filename)
                        fichier.add(file_path, arcname=filename)

                # Lire fichier .tar, convertir en base64
                with open(path_config_temp, 'rb') as fichier:
                    contenu_tar_b64 = b64encode(fichier.read())

                config['scripts'] = contenu_tar_b64.decode('utf-8')

            # Preparer archive .json.xz avec le fichier de configuration signe et les scripts
            config = self.signer(config, 'CoreCatalogues', 'catalogueApplication')
            path_archive_application = path.join(path_archives_application, nom_application + '.json.xz')
            with lzma.open(path_archive_application, 'wt') as output:
                json.dump(config, output)

        unlink(path_config_temp)  # Cleanup fichier temporaire

        # catalogue = {
        #     'applications': catalogue_apps
        # }
        # catalogue = self.signer(catalogue, 'CoreCatalogues', 'catalogueApplications')
        #
        # # Exporter fichier de catalogue
        # path_output = path.join(path_catalogues, 'generes', 'catalogue.applications.json.xz')
        # with lzma.open(path_output, 'wt') as output:
        #     json.dump(catalogue, output)

    def signer(self, contenu: dict, domaine_action: str, action: str = None):
        message_signe, uuid_enveloppe = self._formatteur.signer_message(
            contenu, domaine_action, ajouter_chaine_certs=True, action=action)

        # Ajouter certificat _millegrille
        message_signe['_millegrille'] = self.__cert_millegrille

        return message_signe

    def generer(self):
        self.generer_catalogue_applications()


class IterateurApplications:

    def __init__(self, path_catalogue='.'):
        self.__path_catalogue = path_catalogue
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self.__liste = None
        self.__termine = False

    def __iter__(self):
        liste = listdir(self.__path_catalogue)
        self.__iter = liste.__iter__()
        return self

    def __next__(self):
        nom_item = self.__iter.__next__()
        path_item = path.join(self.__path_catalogue, nom_item)

        while not path.isdir(path_item):
            nom_item = self.__iter.__next__()
            path_item = path.join(self.__path_catalogue, nom_item)

        # Charger fichier docker.json
        with open(path.join(path_item, 'docker.json'), 'r') as fichier:
            config = json.load(fichier)

        return path_item, config


# ----- MAIN -----
def parse_commands():
    parser = argparse.ArgumentParser(description="Generer un catalogue")

    parser.add_argument(
        '--debug', action="store_true", required=False,
        help="Active le logging maximal"
    )
    parser.add_argument(
        '--path', type=str, required=False,
        help="Path des fichiers de catalogue"
    )
    args = parser.parse_args()
    return args


def main():
    logging.basicConfig()
    logging.getLogger('millegrilles').setLevel(logging.INFO)
    logging.getLogger('__main__').setLevel(logging.INFO)

    args = parse_commands()
    if args.debug:
        logging.getLogger('millegrilles').setLevel(logging.DEBUG)
        logging.getLogger('__main__').setLevel(logging.DEBUG)

    generateur = Generateur(args)
    generateur.generer()


if __name__ == '__main__':
    main()
