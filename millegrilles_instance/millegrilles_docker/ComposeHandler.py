import asyncio
import logging
import yaml
import pathlib
import json
from typing import Optional, List, Dict, Any
import docker

from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.millegrilles_docker.ParseConfiguration import ConfigurationService
from millegrilles_instance.MaintenanceApplicationService import ServiceStatus

LOGGER = logging.getLogger(__name__)

class ComposeHandler:
    """
    Handles the orchestration of modules using docker-compose concept.
    Since docker-compose CLI might not be available, this handler will
    use the Docker SDK to achieve the same result: grouping containers
    into modules with shared networks and lifecycle management.
    """

    def __init__(self, context: InstanceContext, docker_client: Any):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context
        self.__docker = docker_client

    async def deploy_module(self, module_name: str, services_configs: List[ConfigurationService]):
        """
        Deploys a module (a set of services) using docker-compose logic.
        """
        self.__logger.info(f"Deploying module: {module_name}")
        
        # 1. Ensure module-specific network exists
        network_name = f"millegrilles_{module_name}_net"
        try:
            await asyncio.to_thread(self.__docker.networks.create, network_name, driver="bridge", labels={"com.millegrilles.module": module_name})
        except docker.errors.APIError as e:
            if e.status_code != 409: # Already exists
                raise e
        
        # 2. Deploy each service in the module
        deployed_containers = []
        for config_service in services_configs:
            container = await self.__deploy_service(module_name, network_name, config_service)
            if container:
                deployed_containers.append(container)
        
        return deployed_containers

    async def deploy_module_from_files(self, module_name: str, config_files: List[pathlib.Path]) -> List[Any]:
        """
        Deploys a module by reading configuration files.
        """
        self.__logger.info(f"Deploying module from files: {module_name}")
        services_configs = []
        for cf in config_files:
            with open(cf, 'r') as f:
                conf_dict = json.load(f)
            cs = ConfigurationService(self.__context, conf_dict)
            cs.parse()
            services_configs.append(cs)
        
        return await self.deploy_module(module_name, services_configs)

    async def __deploy_service(self, module_name: str, network_name: str, config_service: ConfigurationService) -> Optional[Any]:
        self.__logger.debug(f"Deploying service {config_service.configuration['name']} in module {module_name}")
        
        container_name = f"{module_name}_{config_service.configuration['name']}"
        
        # Check if already running
        try:
            existing = await asyncio.to_thread(self.__docker.containers.get, container_name)
            if existing.status == 'running':
                self.__logger.info(f"Service {container_name} is already running.")
                return existing
            else:
                await asyncio.to_thread(existing.remove, force=True)
        except docker.errors.NotFound:
            pass
        
        # Prepare configuration
        config_parsed = config_service.generer_docker_config()
        
        # Prepare env
        env = config_parsed.get('env', [])
        
        # Prepare mounts
        mounts = []
        for m in config_parsed.get('mounts', []):
            mounts.append(m) # In a real implementation, we'd convert docker.types.Mount to dict if needed
        
        # Prepare secrets
        # For simplicity, we assume secrets are already created in Docker as requested
        secret_refs = []
        if config_parsed.get('secrets'):
            for s in config_parsed['secrets']:
                secret_refs.append(s)
        
        # Prepare networks
        network_name = f"millegrilles_{module_name}_net"
        
        # Prepare labels
        labels = config_parsed.get('labels', {})
        labels['com.millegrilles.module'] = module_name
        labels['com.millegrilles.service'] = config_service.configuration['name']
        
        restart_policy_name = config_parsed.get('restart_policy', {}).get('name', 'no')
        restart_policy = {"Name": restart_policy_name} if restart_policy_name != 'no' else None

        try:
            container = await asyncio.to_thread(
                self.__docker.containers.run,
                config_parsed['image'],
                command=config_parsed.get('args'),
                name=container_name,
                environment=env,
                mounts=mounts,
                network=network_name,
                labels=labels,
                detach=True,
                restart_policy=restart_policy
            )
            self.__logger.info(f"Container {container_name} started.")
            return container
        except Exception as e:
            self.__logger.exception(f"Failed to start container {container_name}: {e}")
            return None

    async def stop_module(self, module_name: str):
        """
        Stops and removes all containers in a module.
        """
        self.__logger.info(f"Stopping module: {module_name}")
        network_name = f"millegrilles_{module_name}_net"
        
        # Find containers with this module label
        containers = await asyncio.to_thread(
            self.__docker.containers.list, 
            filters={"label": f"com.millegrilles.module={module_name}"},
            all=True
        )
        
        for container in containers:
            try:
                await asyncio.to_thread(container.stop)
                await asyncio.to_thread(container.remove)
            except Exception as e:
                self.__logger.error(f"Error stopping/removing container {container.name}: {e}")
        
        # Remove network
        try:
            network = await asyncio.to_thread(self.__docker.networks.get, network_name)
            await asyncio.to_thread(network.remove)
        except docker.errors.NotFound:
            pass
        except Exception as e:
            self.__logger.error(f"Error removing network {network_name}: {e}")

    async def restart_module(self, module_name: str):
        """
        Restarts all containers in a module.
        """
        containers = await asyncio.to_thread(
            self.__docker.containers.list, 
            filters={"label": f"com.millegrilles.module={module_name}"}
        )
        for container in containers:
            await asyncio.to_thread(container.restart)
        self.__logger.info(f"Module {module_name} restarted.")

    async def pause_module(self, module_name: str):
        containers = await asyncio.to_thread(
            self.__docker.containers.list, 
            filters={"label": f"com.millegrilles.module={module_name}"}
        )
        for container in containers:
            await asyncio.to_thread(container.pause)

    async def resume_module(self, module_name: str):
        containers = await asyncio.to_thread(
            self.__docker.containers.list, 
            filters={"label": f"com.millegrilles.module={module_name}"}
        )
        for container in containers:
            await asyncio.to_thread(container.unpause)

    async def remove_module(self, module_name: str):
        await self.stop_module(module_name)
