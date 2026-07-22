import subprocess
import sys

from millegrilles.lib import logging

LOGGER = logging.getLogger(__name__)

def reload_nginx(instance_name: str):
    LOGGER.info(f"Reloading {instance_name}-nginx...")
    run_command(f"systemctl --user reload {instance_name}-nginx")

def reload_middleware(instance_name: str):
    LOGGER.info(f"Reloading {instance_name}-middleware...")
    run_command(f"systemctl --user reload {instance_name}-middleware")

def reload_compose_applications(instance_name: str, update_certs=True):
    # Need to generate certificates first to avoid reload issue with applications service
    if update_certs:
        LOGGER.info(f"Generating certificates using {instance_name}-certs_updater...")
        run_command(f"systemctl --user start {instance_name}-certs_updater")
    LOGGER.info(f"Reloading {instance_name}-applications...")
    run_command(f"systemctl --user reload {instance_name}-applications")

def restart_compose_applications(instance_name: str):
    # Need to generate certificates first to avoid reload issue with applications service
    LOGGER.info(f"Restarting {instance_name}-applications...")
    run_command(f"systemctl --user restart {instance_name}-applications")

def run_command(command, env=None):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, env=env)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        LOGGER.error(f"Error executing command: {e}")
        LOGGER.info(f"Command: {e.cmd}")
        LOGGER.info(f"Stdout: {e.stdout}")
        LOGGER.info(f"Stderr: {e.stderr}")
        sys.exit(1)
