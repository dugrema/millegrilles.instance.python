import asyncio
import base64
import json
import logging
import time

from typing import Union

from docker import DockerClient
from docker.errors import APIError, NotFound
from docker.models.containers import Container

from millegrilles_messages.docker.DockerHandler import CommandeDocker


class CommandeListeTopologie(CommandeDocker):

    def __init__(self, callback=None, aio=True):
        super().__init__(callback, aio)

        self.facteur_throttle = 0.25  # Utilise pour throttling, represente un cout relatif de la commande

    def executer(self, docker_client: DockerClient):
        info = docker_client.info()
        containers = parse_liste_containers(docker_client.containers.list(all=True))
        services = parse_list_service(docker_client.services.list())
        self.callback({'info': info, 'containers': containers, 'services': services})

    async def get_info(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


class CommandeExecuterScriptDansService(CommandeDocker):

    def __init__(self, nom_service: str, path_script: str):
        super().__init__(aio=True)
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)

        self.__nom_service = nom_service
        self.__path_script = path_script

        self.facteur_throttle = 2.0

    def executer(self, docker_client: DockerClient):
        containers = docker_client.containers.list(filters={"name": "^%s\\." % self.__nom_service})
        container = None
        for i in range(0, 5):
            try:
                container: Container = containers.pop()
                break
            except IndexError:
                # Container non-trouve, on attend avant de reessayer
                self.__logger.debug("Container de service %s non trouve, on attend 5 secondes" % self.__nom_service)
                try:
                    time.sleep(5)
                except asyncio.TimeoutError:
                    pass
                containers = docker_client.containers.list(filters={"name": self.__nom_service})

        if container is None:
            self.__logger.debug("Container de service %s non trouve, on abandonne" % self.__nom_service)
            return self.callback({'code': -1, 'output': 'Container %s introuvable' % self.__nom_service})

        self.__logger.debug("Container de service %s, on execute le script %s" % (self.__nom_service, self.__path_script))
        exit_code, output = container.exec_run(self.__path_script)
        self.__logger.debug("Resultat execution %s = %s" % (self.__path_script, exit_code))
        self.callback({'code': exit_code, 'output': output})

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


class CommandeGetServicesBackup(CommandeDocker):
    """
    Retourne la liste de tous les services avec un label "backup_scripts"
    """

    def __init__(self):
        super().__init__(aio=True)
        self.facteur_throttle = 0.25

    def executer(self, docker_client: DockerClient):
        liste_services = docker_client.services.list(filters={"label": "backup_scripts"})
        services = parse_list_service(liste_services)
        self.callback(services)

    async def get_services(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


def parse_list_service(services: list) -> dict:
    # Mapper services et etat
    dict_services = dict()
    for service in services:
        attrs = service.attrs
        spec = attrs['Spec']
        info_service = {
            'creation_service': service.attrs['CreatedAt'],
            'maj_service': service.attrs['UpdatedAt'],
        }
        labels = spec.get('Labels')
        if labels:
            info_service['labels'] = labels
        mode = spec.get('Mode')
        if mode:
            replicated = mode.get('Replicated')
            if replicated:
                replicas = replicated.get('Replicas')
                if replicas:
                    info_service['replicas'] = replicas

        tasks = [task for task in service.tasks() if task['DesiredState'] == 'running']
        if len(tasks) > 0:
            task = tasks[-1]
            info_service['etat'] = task['Status']['State']
            info_service['message_tache'] = task['Status']['Message']

        dict_services[service.name] = info_service

    return dict_services


def parse_liste_containers(containers: list) -> dict:
    # Mapper services et etat
    dict_containers = dict()
    for container in containers:
        attrs = container.attrs
        info_container = {
            'creation': attrs['Created'],
            'restart_count': attrs['RestartCount'],
        }

        state = attrs['State']
        info_container['etat'] = state['Status']
        info_container['running'] = state['Running']
        info_container['dead'] = state['Dead']
        info_container['finished_at'] = state['FinishedAt']

        info_container['labels'] = attrs['Config']['Labels']

        dict_containers[attrs['Name']] = info_container

    return dict_containers
