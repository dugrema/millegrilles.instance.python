# Main script d'application pour une instance MilleGrilles
# L'application gere les secrets, certificats et site web de configuration (port 8080).
import asyncio
import logging
from millegrilles_instance import initialiser_application


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
