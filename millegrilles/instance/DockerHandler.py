from millegrilles.instance.DockerState import DockerState

class DockerHandler:

    def __init__(self, docker_state: DockerState):
        self.__docker = docker_state.docker

