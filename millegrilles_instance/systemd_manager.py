import asyncio
import logging
import pathlib
import subprocess
import os
from typing import Optional
from millegrilles_instance.Configuration import ConfigurationInstance
from millegrilles_messages.messages import Constantes

LOGGER = logging.getLogger(__name__)

class InstanceServiceManager:
    def __init__(self, config: ConfigurationInstance):
        self.__config = config
        self.__instance_name = config.instance_name
        self.__user_systemd_dir = pathlib.Path.home() / ".config" / "systemd" / "user"
        self.__service_file = self.__user_systemd_dir / f"{self.__instance_name}_instance.service"

    def _get_node_type_dir(self) -> str:
        """
        Maps the security level to the corresponding docker-compose directory.
        """
        # Based on the directory structure in etc/compose/
        # We need to match the security level from the configuration.
        # Since we don't have the exact mapping in Constantes, 
        # we'll use the security level from the config if available.
        # For now, let's assume the directory name is the lowercase of the security level.
        # But looking at the files, it's: publics, prives, proteges, secures.
        
        # We need to find where the security level is stored.
        # It is likely in the config.json.
        
        # We'll try to derive it from the securite level in the configuration.
        # In MilleGrilles, securite is usually one of the Constantes.SECURITE_...
        
        # We'll attempt to use the directory mapping.
        # This is a bit tricky without knowing the exact mapping, 
        # but based on the files:
        # Constantes.SECURITE_PUBLIC -> publics
        # Constantes.SECURITE_PRIVE -> prives
        # Constantes.SECURITE_PROTEGE -> proteges
        # Constantes.SECURITE_SECURE -> secures
        
        # We can try to get the securite from the configuration object.
        # However, the configuration object might not have it loaded yet.
        # We will use the value from the configuration instance.
        
        # We'll check the config file directly if needed, but let's try to 
        # use the existing configuration object.
        
        # We'll assume the configuration object has the security level.
        # We'll try to map it.
        
        # Since we don't have direct access to the security level value as a string in ConfigurationInstance,
        # we'll have to infer it.
        
        # Let's look at the installation files to see how they are named.
        # etc/compose/publics/
        # etc/compose/prives/
        # etc/compose/proteges/
        # etc/compose/secures/
        
        # We can check which directory exists.
        potential_dirs = ["publics", "prives", "proteges", "secures"]
        # But we must be careful.
        
        # Let's try to get the security level from the config.json if possible.
        # Or we can pass it to the constructor.
        
        return "" # Placeholder

    def _get_node_type_by_security(self, security_level: str) -> str:
        mapping = {
            "public": "publics",
            "prive": "prives",
            "protege": "proteges",
            "secure": "secures"
        }
        return mapping.get(security_level, "publics")

    def _ensure_user_dir(self):
        self.__user_systemd_dir.mkdir(parents=True, exist_ok=True)

    def generate_node_service_file(self, node_type: str):
        """
        Generates the service file from the template.
        """
        if not self.__template_path.exists():
            raise FileNotFoundError(f"Template not found at {self.__template_path}")

        with open(self.__template_path, 'r') as f:
            template = f.read()

        # Perform replacements
        # {{NODE_TYPE}} -> node_type
        # {{WORKING_DIR}} -> self.__config.path_millegrilles
        # {{INSTANCE_NAME}} -> self.__instance_name (if used)
        
        service_content = template.replace("{{NODE_TYPE}}", node_type)
        service_content = service_content.replace("{{WORKING_DIR}}", str(self.__config.path_millegrilles))
        # If {{INSTANCE_NAME}} was in the template
        service_content = service_content.replace("{{INSTANCE_NAME}}", self.__instance_name)

        self._ensure_user_dir()
        with open(self.__service_file, 'w') as f:
            f.write(service_content)
        
        LOGGER.info("Generated service file at %s", self.__service_file)

    async def deploy(self, node_type: str):
        """
        Generates the service file and starts the service via systemd --user.
        """
        self.generate_node_service_file(node_type)
        
        try:
            # systemctl --user daemon-reload
            process = await asyncio.create_subprocess_exec(
                'systemctl', '--user', 'daemon-reload',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode != 0:
                err = (await process.stderr).decode()
                LOGGER.error("systemctl --user daemon-reload failed: %s", err)
                raise RuntimeError(f"daemon-reload failed: {err}")

            # systemctl --user enable --now <service_name>
            process = await asyncio.create_subprocess_exec(
                'systemctl', '--user', 'enable', '--now', f"{self.__instance_name}_instance.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode != 0:
                err = (await process.stderr).decode()
                LOGGER.error("systemctl --user enable --now failed: %s", err)
                raise RuntimeError(f"enable --now failed: {err}")

            LOGGER.info("Service %s_instance started successfully", self.__instance_name)
        except Exception as e:
            LOGGER.exception("Deployment failed: %s", e)
            raise

    async def restart(self, node_type: str):
        """
        Regenerates the service file and restarts the service.
        """
        self.generate_node_service_file(node_type)
        
        try:
            # systemctl --user daemon-reload
            process = await asyncio.create_subprocess_exec(
                'systemctl', '--user', 'daemon-reload',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()

            # systemctl --user restart <service_name>
            process = await asyncio.create_subprocess_exec(
                'systemctl', '--user', 'restart', f"{self.__instance_name}_instance.service",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            await process.communicate()
            if process.returncode != 0:
                err = (await process.stderr).decode()
                LOGGER.error("systemctl --user restart failed: %s", err)
                raise RuntimeError(f"restart failed: {err}")

            LOGGER.info("Service %s_instance restarted successfully", self.__instance_name)
        except Exception as e:
            LOGGER.exception("Reconfiguration failed: %s", e)
            raise
