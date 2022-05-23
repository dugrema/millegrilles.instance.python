# Main script d'application pour une instance MilleGrilles
# L'application gere les secrets, certificats et site web de configuration (port 8080).
import argparse
import asyncio
import logging
import signal

from asyncio import Event
from asyncio.exceptions import TimeoutError
from os import path, makedirs
from typing import Optional
from uuid import uuid4

from millegrilles.instance.Configuration import ConfigurationInstance
from millegrilles.instance.Certificats import preparer_certificats_web
from millegrilles.instance.DockerState import DockerState
from millegrilles.instance.DockerHandler import DockerHandler
from millegrilles.instance.WebServer import WebServer


def initialiser_application():
    logging.basicConfig()

    app = ApplicationInstance()

    args = parse()
    if args.verbose:
        logging.getLogger('millegrilles').setLevel(logging.DEBUG)
    else:
        logging.getLogger('millegrilles').setLevel(logging.WARN)

    app.charger_configuration(args)

    signal.signal(signal.SIGINT, app.exit_gracefully)
    signal.signal(signal.SIGTERM, app.exit_gracefully)
    signal.signal(signal.SIGHUP, app.reload_configuration)

    app.preparer_environnement()

    return app


def parse():
    logger = logging.getLogger(__name__ + '.parse')
    parser = argparse.ArgumentParser(description="Demarrer l'application d'instance MilleGrilles")

    parser.add_argument(
        '--verbose', action="store_true", required=False,
        help="Active le logging maximal"
    )

    args = parser.parse_args()
    if args.verbose:
        logger.setLevel(logging.DEBUG)

    logger.debug("args : %s" % args)

    return args


class ApplicationInstance:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__loop = None
        self._stop_event = None  # Evenement d'arret global de l'application
        self.__configuration = ConfigurationInstance()

        self.__web_server: Optional[WebServer] = None
        self.__docker_handler: Optional[DockerHandler] = None

        self.__instance_id: Optional[str] = None
        self.__niveau_securite: Optional[str] = None
        self.__idmg: Optional[str] = None

    def charger_configuration(self, args: argparse.Namespace):
        """
        Charge la configuration d'environnement (os.env, /var/opt/millegrilles/instance)
        :return:
        """
        self.__logger.info("Charger la configuration")
        self.__configuration.parse_config(args)

    def preparer_environnement(self):
        """
        Examine environnement, preparer au besoin (folders, docker, ports, etc)
        :return:
        """
        self.__logger.info("Preparer l'environnement")
        makedirs(self.__configuration.path_nginx_configuration, 0o750, exist_ok=True)
        makedirs(self.__configuration.path_secrets, 0o700, exist_ok=True)
        makedirs(self.__configuration.path_secrets_partages, 0o710, exist_ok=True)

        self.preparer_folder_configuration()
        self.reload_configuration()

        self.__web_server = WebServer(self)
        self.__web_server.setup()

        docker_state = DockerState()
        if docker_state.docker_actif() is True:
            self.__logger.info("Docker est actif")
            self.__docker_handler = DockerHandler(docker_state)

    def preparer_folder_configuration(self):
        makedirs(self.__configuration.path_configuration, 0o750, exist_ok=True)

        # Verifier si on a les fichiers de base (instance_id.txt)
        path_instance_txt = path.join(self.__configuration.path_configuration, 'instance_id.txt')
        if path.exists(path_instance_txt) is False:
            uuid_instance = str(uuid4())
            with open(path_instance_txt, 'w') as fichier:
                fichier.write(uuid_instance)

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

    def exit_gracefully(self, signum=None, frame=None):
        self.__logger.info("Fermer application, signal: %d" % signum)
        self.fermer()

    async def entretien(self):
        """
        Entretien du systeme. Invoque a intervalle regulier.
        :return:
        """
        self.__logger.debug("Debut cycle d'entretien")

        while not self._stop_event.is_set():
            # Entretien

            try:
                # Attente 30 secondes entre entretien
                await asyncio.wait_for(self._stop_event.wait(), 30)
            except TimeoutError:
                pass

        self.__logger.debug("Fin cycle d'entretien")

    def fermer(self):
        if self.__loop is not None:
            self.__loop.call_soon_threadsafe(self._stop_event.set)

    async def executer(self):
        """
        Boucle d'execution principale
        :return:
        """
        self.__loop = asyncio.get_event_loop()
        self._stop_event = Event()

        tasks = [
            asyncio.create_task(self.entretien()),
            asyncio.create_task(self.__web_server.run(self._stop_event))
        ]

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)


def main():
    """
    Methode d'execution de l'application
    :return:
    """
    app = initialiser_application()
    logger = logging.getLogger(__name__)

    try:
        logger.info("Debut execution app")
        asyncio.run(app.executer())
        logger.info("Fin execution app")
    except KeyboardInterrupt:
        logger.info("Arret execution app via signal (KeyboardInterrupt), fin thread main")
    except:
        logger.exception("Exception durant execution app, fin thread main")
    finally:
        app.fermer()  # S'assurer de mettre le flag de stop_event


if __name__ == '__main__':
    main()
