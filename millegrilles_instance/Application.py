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

from millegrilles_messages.docker.DockerHandler import DockerState, DockerHandler
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_instance.WebServer import WebServer
from millegrilles_instance.EtatInstance import EtatInstance
from millegrilles_instance.InstanceDocker import EtatDockerInstanceSync
from millegrilles_instance.EntretienInstance import get_module_execution


async def initialiser_application():
    logging.basicConfig()

    app = ApplicationInstance()

    args = parse()
    if args.verbose:
        logging.getLogger('millegrilles_messages').setLevel(logging.DEBUG)
        logging.getLogger('millegrilles_instance').setLevel(logging.DEBUG)
    else:
        logging.getLogger('millegrilles_messages').setLevel(logging.WARN)
        logging.getLogger('millegrilles_instance').setLevel(logging.WARN)

    app.charger_configuration(args)

    signal.signal(signal.SIGINT, app.exit_gracefully)
    signal.signal(signal.SIGTERM, app.exit_gracefully)
    # signal.signal(signal.SIGHUP, app.reload_configuration)

    await app.preparer_environnement()

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
        self.__entretien_event = None
        self.__configuration = ConfigurationInstance()
        self.__etat_instance = EtatInstance(self.__configuration)

        self.__web_server: Optional[WebServer] = None
        self.__docker_handler: Optional[DockerHandler] = None
        self.__docker_etat: Optional[EtatDockerInstanceSync] = None

        # Coroutine a executer pour l'entretien, depend du type d'instance (None = installation)
        self.__module_entretien = None

    def charger_configuration(self, args: argparse.Namespace):
        """
        Charge la configuration d'environnement (os.env, /var/opt/millegrilles/instance)
        :return:
        """
        self.__logger.info("Charger la configuration")
        self.__configuration.parse_config(args)

    async def preparer_environnement(self):
        """
        Examine environnement, preparer au besoin (folders, docker, ports, etc)
        :return:
        """
        self.__logger.info("Preparer l'environnement")
        self.__entretien_event = Event()
        self._stop_event = Event()

        makedirs(self.__configuration.path_secrets, 0o700, exist_ok=True)
        makedirs(self.__configuration.path_secrets_partages, 0o710, exist_ok=True)

        self.preparer_folder_configuration()
        await self.__etat_instance.reload_configuration()  # Genere les certificats sur premier acces

        self.__etat_instance.ajouter_listener(self.changer_etat_execution)

        self.__web_server = WebServer(self.__etat_instance)
        self.__web_server.setup()

        await self.demarrer_client_docker()  # Demarre si docker est actif

        await self.__etat_instance.reload_configuration()

    def preparer_folder_configuration(self):
        makedirs(self.__configuration.path_configuration, 0o750, exist_ok=True)

        # Verifier si on a les fichiers de base (instance_id.txt)
        path_instance_txt = path.join(self.__configuration.path_configuration, 'instance_id.txt')
        if path.exists(path_instance_txt) is False:
            uuid_instance = str(uuid4())
            with open(path_instance_txt, 'w') as fichier:
                fichier.write(uuid_instance)

    async def demarrer_client_docker(self):
        if self.__docker_handler is None:
            docker_state = DockerState()
            self.__etat_instance.set_docker_present(docker_state.docker_present())
            if docker_state.docker_present() is True:
                self.__docker_handler = DockerHandler(docker_state)
                self.__docker_handler.start()
                self.__docker_etat = EtatDockerInstanceSync(self.__etat_instance, self.__docker_handler)

    async def changer_etat_execution(self, etat_instance: EtatInstance):
        """
        Determine le type d'execution en cours (instance public, prive, protege, mode installation, etc)
        :param etat_instance:
        :return:
        """
        if self.__module_entretien is not None:
            # Interrompre module d'execution en cours
            await self.__module_entretien.fermer()
            self.__module_entretien = None

        self.__module_entretien = get_module_execution(etat_instance)
        if self.__module_entretien is not None:
            # Preparer le nouveau module d'entretien. Hook est dans self.entretien() pour run
            await self.__module_entretien.setup(etat_instance, self.__docker_etat)
            self.__entretien_event.set()  # Redemarre le module d'entretien

    def exit_gracefully(self, signum=None, frame=None):
        self.__logger.info("Fermer application, signal: %d" % signum)
        self.fermer()

    async def entretien(self):
        """
        Entretien du systeme. Invoque a intervalle regulier.
        :return:
        """
        self.__logger.debug("Debut coroutine d'entretien")

        while self._stop_event.is_set() is False:
            self.__logger.debug("Debut cycle d'entretien")

            # Entretien
            if self.__module_entretien is not None:
                # Execution du module d'entretien de l'instance
                await self.__module_entretien.run()
            try:
                # Attendre setup d'un module d'entretien
                self.__logger.debug("Fin cycle d'entretien")
                await self.__entretien_event.wait()
                self.__entretien_event.clear()
            except TimeoutError:
                pass

        self.__logger.debug("Fin coroutine d'entretien")

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

        if self.__docker_etat is not None:
            tasks.append(asyncio.create_task(self.__docker_etat.entretien(self._stop_event)))

        # Execution de la loop avec toutes les tasks
        await asyncio.tasks.wait(tasks, return_when=asyncio.tasks.FIRST_COMPLETED)


async def demarrer():
    logger = logging.getLogger(__name__)

    logger.info("Setup app")
    app = await initialiser_application()

    try:
        logger.info("Debut execution app")
        await app.executer()
    except KeyboardInterrupt:
        logger.info("Arret execution app via signal (KeyboardInterrupt), fin thread main")
    except:
        logger.exception("Exception durant execution app, fin thread main")
    finally:
        logger.info("Fin execution app")
        app.fermer()  # S'assurer de mettre le flag de stop_event


def main():
    """
    Methode d'execution de l'application
    :return:
    """
    asyncio.run(demarrer())


if __name__ == '__main__':
    main()
