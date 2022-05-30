import base64
import json
import logging

from typing import Union

from docker import DockerClient
from docker.errors import APIError, NotFound

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
