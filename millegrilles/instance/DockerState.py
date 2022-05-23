import json
import docker
import logging

from typing import Optional


class DockerState:

    def __init__(self):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        path_socket = '/run/docker.sock'
        self.__docker = docker.DockerClient('unix://' + path_socket)
        self.__logger.info("Docker socket a connecte %s" % path_socket)

        self.__docker_actif: Optional[bool] = None

    def docker_present(self):
        version_docker = self.__docker.version()
        self.__logger.debug("Version docker : %s" % json.dumps(version_docker, indent=2))
        return True

    def swarm_present(self):
        info_docker = self.__docker.info()
        try:
            swarm_config = info_docker['Swarm']
            self.__logger.info("Information swarm docker %s" % json.dumps(swarm_config, indent=2))
            return swarm_config['Nodes'] > 0
        except KeyError:
            self.__logger.info("Swarm docker n'est pas configure")
            return False

    def docker_actif(self):
        if self.__docker_actif is None:
            try:
                present = self.docker_present()
                swarm = self.swarm_present()
                if present is True and swarm is True:
                    self.__docker_actif = True
                else:
                    self.__docker_actif = False
            except Exception:
                self.__logger.exception("Erreur verification etat docker")
                self.__docker_actif = False

        return self.__docker_actif

    @property
    def docker(self):
        return self.__docker


def main():
    logging.basicConfig()
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    logging.getLogger('millegrilles').setLevel(logging.DEBUG)

    try:
        state = DockerState()
        docker_present = state.docker_present()
        logger.debug("Docker present : %s" % docker_present)
        swarm_present = state.swarm_present()
        logger.debug("Swarm present : %s" % swarm_present)

        actif = state.docker_actif()
        logger.debug("Docker actif? %s" % actif)

    except Exception:
        logger.exception("Docker absent (non configure/pret)")


if __name__ == '__main__':
    main()
