import asyncio
import logging
import pathlib
import yaml
import json
from typing import Optional, List, Any
from millegrilles_instance.Context import InstanceContext
from millegrilles_instance.millegrilles_docker.ParseConfiguration import ConfigurationService

LOGGER = logging.getLogger(__name__)

class ComposeHandler:
    """
    Handles the orchestration of modules using docker-compose.
    """
    def __init__(self, context: InstanceContext):
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__context = context

    async def _run_compose(self, working_dir: pathlib.Path, args: list[str]) -> str:
        cmd = ["docker", "compose"] + args
        process = await asyncio.create_subprocess_exec(
            *cmd,
            cwd=str(working_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            err_msg = stderr.decode().strip()
            raise Exception(f"Docker Compose error in {working_dir}: {err_msg}")
            
        return stdout.decode().strip()

    def __get_compose_dict(self, config: dict) -> dict:
        """
        Converts the dictionary from ConfigurationService.generer_docker_config() 
        to a dictionary suitable for a node-prive.yml file.
        """
        compose_service = {
            'image': config['image'],
            'container_name': config.get('name'),
        }
        
        if 'hostname' in config:
            compose_service['hostname'] = config['hostname']
        
        if 'args' in config:
            compose_service['command'] = config['args']
            
        if 'env' in config:
            compose_service['environment'] = config['env']
            
        if 'labels' in config:
            compose_service['labels'] = config['labels']
        
        if 'container_labels' in config:
            if 'labels' not in compose_service:
                compose_service['labels'] = {}
            compose_service['labels'].update(config['container_labels'])

        if 'mounts' in config:
            volumes = []
            for m in config['mounts']:
                mode = ":ro" if m.read_only else ""
                if m.type == 'bind':
                    volumes.append(f"{m.source}:{m.target}{mode}")
                elif m.type == 'volume':
                    volumes.append(f"{m.source}:{m.target}{mode}")
            if volumes:
                compose_service['volumes'] = volumes

        if 'restart_policy' in config:
            policy = config['restart_policy']
            if policy.name != 'no':
                compose_service['restart'] = policy.name

        return compose_service

    async def deploy_module(self, module_name: str, services_configs: List[ConfigurationService]) -> List[Any]:
        """
        Deploys a module using docker compose from the given module name.
        """
        self.__logger.info(f"Deploying module: {module_name}")
        
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        compose_dir.mkdir(parents=True, exist_ok=True)
        compose_file = compose_dir / "node-prive.yml"

        compose_data = {
            'services': {}
        }

        for cs in services_configs:
            config_dict = cs.generer_docker_config()
            compose_data['services'][cs.configuration['name']] = self.__get_compose_dict(config_dict)

        network_name = f"millegrilles_{module_name}_net"
        compose_data['networks'] = {
            network_name: {
                'driver': 'bridge',
                'labels': {'com.millegrilles.module': module_name}
            }
        }
        
        for service_name in compose_data['services']:
            if 'networks' not in compose_data['services'][service_name]:
                compose_data['services'][service_name]['networks'] = [network_name]
            elif isinstance(compose_data['services'][service_name]['networks'], str):
                compose_data['services'][service_name]['networks'] = [network_name, compose_data['services'][service_name]['networks']]
            else:
                compose_data['services'][service_name]['networks'].append(network_name)

        with open(compose_file, 'w') as f:
            yaml.dump(compose_data, f, default_flow_style=False)

        await self._run_compose(compose_dir, ["up", "-d"])
        return []

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

    async def stop_module(self, module_name: str):
        """
        Stops the module.
        """
        self.__logger.info(f"Stopping module: {module_name}")
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        if compose_dir.exists():
            await self._run_compose(compose_dir, ["stop"])

    async def restart_module(self, module_name: str):
        """
        Restarts the module.
        """
        self.__logger.info(f"Restarting module: {module_name}")
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        if compose_dir.exists():
            await self._run_compose(compose_dir, ["restart"])

    async def pause_module(self, module_name: str):
        self.__logger.info(f"Pausing module: {module_name}")
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        if compose_dir.exists():
            await self._run_compose(compose_dir, ["pause"])

    async def resume_module(self, module_name: str):
        self.__logger.info(f"Resuming module: {module_name}")
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        if compose_dir.exists():
            await self._run_compose(compose_dir, ["unpause"])

    async def remove_module(self, module_name: str):
        self.__logger.info(f"Removing module: {module_name}")
        compose_dir = self.__context.configuration.path_millegrilles / "etc" / "docker" / "compose" / module_name
        if compose_dir.exists():
            await self._run_compose(compose_dir, ["down"])
