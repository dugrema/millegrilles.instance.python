# Main script d'application pour une instance MilleGrilles
# L'application gere les secrets, certificats et site web de configuration (port 8080).
import argparse
import asyncio
import logging
import signal

from asyncio import Event
from asyncio.exceptions import TimeoutError


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
    signal.signal(signal.SIGHUP, app.reload)

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

    def charger_configuration(self, args: argparse.Namespace):
        """
        Charge la configuration (os.env, /var/opt/millegrilles/instance)
        :return:
        """
        self.__logger.info("Charger la configuration")

    def preparer_environnement(self):
        """
        Examine environnement, preparer au besoin (folders, docker, ports, etc)
        :return:
        """
        self.__logger.info("Preparer l'environnement")

    async def reload(self):
        self.__logger.info("Reload configuration")

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
