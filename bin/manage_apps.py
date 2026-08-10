#!/usr/bin/python3
import argparse
import hashlib
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from subprocess import CalledProcessError

import yaml
import time

from typing import Optional, Union

DEFAULT_CATALOGUE_URL = "https://libs.millegrilles.com/archives/stable.json"

def run_command(command, env=None, no_exit=False, capture_output=True) -> Union[str, int]:
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=capture_output, text=True, env=env)
        if capture_output:
            return result.stdout.strip()
        else:
            return result.returncode
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Command: {e.cmd}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        if no_exit:
            raise e
        sys.exit(1)

def download_file(url: str, dest_path: pathlib.Path):
    """Downloads a file from a URL to the specified destination."""
    try:
        with urllib.request.urlopen(url) as response, open(dest_path, 'wb') as out_file:
            shutil.copyfileobj(response, out_file)
    except Exception as e:
        print(f"Error downloading {url}: {e}")
        sys.exit(1)

def calculate_sha256(file_path: pathlib.Path) -> str:
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def copy_file(src: pathlib.Path, dest: pathlib.Path):
    """Copies a file from src to dest, preserving metadata."""
    shutil.copy2(src, dest)

def copy_dir(src: pathlib.Path, dest: pathlib.Path):
    """Copies a directory from src to dest, including its contents."""
    shutil.copytree(src, dest, dirs_exist_ok=True)

def remove_dir(path: pathlib.Path):
    """Removes a directory and its contents if it exists."""
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)

def reload_nginx(instance_name: str):
    print(f"Securite {os.environ.get('SECURITE')}")
    if os.environ.get('SECURITE') != '4.secure':
        print(f"Reloading {instance_name}-nginx...")
        run_command(f"systemctl --user reload {instance_name}-nginx")
    else:
        print("Secure environment, not reloading nginx")

def reload_compose_applications(instance_name: str, cert_required=True):
    # Need to generate certificates first to avoid reload issue with applications service
    if cert_required:
        print(f"Generating certificates using {instance_name}-certs_updater...")
        try:
            run_command(f"systemctl --user start {instance_name}-certs_updater", no_exit=True)
        except CalledProcessError:
            print("Exception trying to renew certs, switching to restart manager")
            run_command(f"systemctl --user restart {instance_name}-manager")
            time.sleep(10)

    print(f"Reloading {instance_name}-applications...")
    run_command(f"systemctl --user reload {instance_name}-applications")

# def restart_compose_applications(instance_name: str):
#     # Need to generate certificates first to avoid reload issue with applications service
#     print(f"Restarting {instance_name}-applications...")
#     run_command(f"systemctl --user restart {instance_name}-applications")

class AppManager:
    def __init__(self, root: str, html_dir: str, instance_name: str):
        self.root = pathlib.Path(root)
        self.instance_name = instance_name
        self.etc_dir = self.root / "etc"
        self.var_dir = self.root / "var"
        self.nginx_html_dir = pathlib.Path(html_dir)
        if not self.nginx_html_dir.exists():
            raise FileNotFoundError(f"{html_dir} not found")

        self.installed_apps_file = self.etc_dir / "installed_applications.json"
        self.nginx_apps_conf_dir = self.etc_dir / "nginx" / "applications"
        self.nginx_apps_html_dir = self.nginx_html_dir / "applications"
        self.compose_dir = self.etc_dir / "compose"
        self.compose_apps_yaml = self.compose_dir / "applications.yml"
        self.compose_apps_dir = self.compose_dir / "applications"

        # Ensure directories exist
        os.makedirs(self.nginx_apps_conf_dir, exist_ok=True)
        os.makedirs(self.compose_apps_dir, exist_ok=True)
        os.makedirs(self.nginx_apps_html_dir, exist_ok=True)

    def fetch_json(self, url):
        try:
            with urllib.request.urlopen(url) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            print(f"Error fetching JSON from {url}: {e}")
            sys.exit(1)

    def get_installed_apps(self):
        if self.installed_apps_file.exists():
            with open(self.installed_apps_file, 'r') as f:
                return json.load(f)
        return {}

    def save_installed_apps(self, apps):
        os.makedirs(self.installed_apps_file.parent, exist_ok=True)
        with open(self.installed_apps_file, 'w') as f:
            json.dump(apps, f, indent=2)

    def get_updates(self, catalogue_url: str):
        catalogue = self.fetch_json(catalogue_url)
        if not catalogue:
            return []

        installed_apps = self.get_installed_apps()
        updates = []

        def parse_version(v):
            try:
                return tuple(int(x) for x in str(v).split('.'))
            except (ValueError, AttributeError):
                return (0,)

        for name, installed_info in installed_apps.items():
            if name in catalogue:
                available_info = catalogue[name]
                installed_version = installed_info.get('version')
                available_version = available_info.get('version')

                if installed_version and available_version:
                    if parse_version(available_version) > parse_version(installed_version):
                        updates.append({
                            'name': name,
                            'current_version': installed_version,
                            'available_version': available_version,
                            'url': available_info.get('url'),
                            'sha256': available_info.get('sha256')
                        })
        return updates


    def install_from_package(self, pkg_url: str, expected_hash: Optional[str], noreload = False):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pkg_path = pathlib.Path(tmp_dir) / "package.tar.gz"
            print(f"Downloading {pkg_url}...")
            download_file(pkg_url, pkg_path)
            
            if expected_hash:
                print("Verifying hash...")
                actual_hash = calculate_sha256(pkg_path)
                if actual_hash != expected_hash:
                    print(f"Error: Hash mismatch! Expected {expected_hash}, got {actual_hash}")
                    sys.exit(1)
            
            extract_dir = pathlib.Path(tmp_dir) / "extracted"
            os.makedirs(extract_dir, exist_ok=True)
            print("Extracting package...")
            run_command(f"tar -xf {pkg_path} -C {extract_dir} --strip-components=1")
  
            # 1. Read metadata.json
            metadata_file = extract_dir / "metadata.json"
            if not metadata_file.exists():
                print("Error: metadata.json not found in package.")
                sys.exit(1)
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            name = metadata['name']
            version = metadata['version']
            app_path = metadata.get('path')
 
            print(f"Installing {name} (version: {version}, path: {app_path})...")
 
            # 2. Handle Nginx Config
            nginx_conf_dir = extract_dir / "nginx"
            if nginx_conf_dir.exists():
                for f in nginx_conf_dir.iterdir():
                    if f.is_file():
                        # Store with "[package name]__[config file name]", allows easy association to package for uninstallation.
                        dest_nginx_conf = self.nginx_apps_conf_dir / f"{name}__{f.name}"
                        print(f"Configuring Nginx, adding file: {dest_nginx_conf}")
                        copy_file(f, dest_nginx_conf)
 
            # 3. Handle Docker Compose
            docker_compose = extract_dir / "docker-compose.yml"
            compose_installed = False
            if docker_compose.exists():
                # Parse the file to ensure it is properly formatted
                with open(docker_compose) as f:
                    yaml_app_file = yaml.safe_load(f)

                # Pre-initialize the bind mounts, this avoids permission issues
                try:
                    for service_name, service_info in yaml_app_file['services'].items():
                        try:
                            for volume in service_info['volumes']:
                                mount_path = volume.split(":")[0]
                                if "MILLEGRILLES_ROOT" in mount_path:
                                    mount_path = mount_path.replace("${MILLEGRILLES_ROOT}", str(self.root))
                                elif "$" in mount_path:
                                    continue  # Skip, this could be mongo or filehost (already handled in install script)

                                # Replace variables using env as format
                                mount_path = mount_path.format(**os.environ)
                                mount_path_resolved = pathlib.Path(mount_path).resolve()

                                print(f"Creating mount {mount_path_resolved}")
                                mount_path_resolved.mkdir(parents=True, exist_ok=True)
                        except KeyError:
                            pass
                except KeyError:
                    pass

                dest_docker_compose = self.compose_apps_dir / f"{name}.yml"
                print(f"Configuring Docker Compose: {dest_docker_compose}")
                copy_file(docker_compose, dest_docker_compose)
                compose_installed = True
                # Add application file to applications.yml include list
                app_yaml_filepath = str(dest_docker_compose.relative_to(self.compose_dir))
                with open(self.compose_apps_yaml) as f:
                    yaml_app_file = yaml.safe_load(f)
                yaml_includes: list = yaml_app_file['include']
                if app_yaml_filepath not in yaml_includes:
                    # Append new app to list and overwrite app file
                    yaml_includes.append(app_yaml_filepath)
                    with open(self.compose_apps_yaml, 'w') as f:
                        yaml.safe_dump(yaml_app_file, f)
 
            # 4. Handle Application Files
            app_files_dir = extract_dir / "files"
            if app_path and app_files_dir.exists():
                dest_html_dir = self.nginx_apps_html_dir / app_path
                print(f"Deploying application files to {dest_html_dir}...")
                remove_dir(dest_html_dir)
                copy_dir(app_files_dir, dest_html_dir)
 
            # 5. Update local catalogue metadata for this app
            installed_apps = self.get_installed_apps()
            installed_apps[name] = metadata
            self.save_installed_apps(installed_apps)

            if not noreload:
                # 6. Reload middleware
                if app_path or nginx_conf_dir:
                    reload_nginx(self.instance_name)

                if compose_installed:
                    # Download all images required by applications.yml
                    self.download_images(name)
                    # Reload compose configuration
                    reload_compose_applications(self.instance_name, True)
 
            print("Installation complete.")

    def uninstall(self, name):
        installed_apps = self.get_installed_apps()
        if name not in installed_apps:
            print(f"Error: Application '{name}' is not installed.")
            sys.exit(1)

        print(f"Uninstalling {name}...")

        nginx_reload = False
        compose_reload = False

        # 1. Remove Nginx Config
        nginx_conf_prefix = self.nginx_apps_conf_dir
        print(f"Removing Nginx config files matching: {nginx_conf_prefix}/{name}__*")
        for nginx_conf in nginx_conf_prefix.glob(f"{name}__*"):
            if nginx_conf.is_file():
                print(f"Removing Nginx config file: {nginx_conf}")
                nginx_conf.unlink()
                nginx_reload = True

        # 2. Stop and remove the application containers
        # self.remove_app(name)  # Doesn't work, need individual container group names

        # 3. Remove Docker Compose configuration for application
        docker_compose = self.compose_apps_dir / f"{name}.yml"
        if docker_compose.exists():
            print(f"Removing Docker Compose file: {docker_compose}")
            os.remove(docker_compose)
            compose_reload = True

        # Remove application file from applications.yml include list
        app_yaml_filepath = str(docker_compose.relative_to(self.compose_dir))
        with open(self.compose_apps_yaml) as f:
            yaml_app_file = yaml.safe_load(f)
        yaml_includes: list = yaml_app_file['include']
        if app_yaml_filepath in yaml_includes:
            # Remove app from list and overwrite app file
            print(f"Removing Docker Compose file from applications.yaml: {app_yaml_filepath}")

            yaml_includes.remove(app_yaml_filepath)
            with open(self.compose_apps_yaml, 'w') as f:
                yaml.safe_dump(yaml_app_file, f)

            compose_reload = True

        # 4. Remove Application Files
        app_info = installed_apps[name]
        try:
            app_path: str = app_info['path']
        except KeyError:
            pass
        else:
            dest_nginx_files = self.nginx_apps_html_dir / app_path

            if dest_nginx_files.exists():
                print(f"Removing application files: {dest_nginx_files}")
                remove_dir(dest_nginx_files)

        # 5. Update local catalogue
        del installed_apps[name]
        self.save_installed_apps(installed_apps)
 
        # 6. Reload Nginx / Restart Appllications (later: remove app only, reload does not work)
        if nginx_reload:
            reload_nginx(self.instance_name)
        if compose_reload:
            reload_compose_applications(self.instance_name, False)
        print("Uninstallation complete.")

    def list_available(self, catalogue_url: str):
        print(f"Fetching available applications from {catalogue_url}...")
        catalogue = self.fetch_json(catalogue_url)
        
        if not catalogue:
            print("No applications available.")
            return

        print(f"{'Name':<20} {'Version':<10} {'Labels'}")
        print("-" * 80)
        for name, info in catalogue.items():
            labels = ", ".join(info.get('labels', {}).values())
            print(f"{name:<20} {info.get('version', 'N/A'):<10} {labels}")

    def list_installed(self):
        installed_apps = self.get_installed_apps()
        if not installed_apps:
            print("No applications installed.")
            return

        print(f"{'Name':<20} {'Version':<10} {'Path'}")
        print("-" * 50)
        for name, info in sorted(installed_apps.items()):
            print(f"{name:<20} {info.get('version', 'N/A'):<10} {info.get('url', 'N/A')}")

    def download_images(self, appname: str):
        print(f"Downloading docker images for applications...")
        run_command(f"docker compose -f {self.root / "etc/compose/applications.yml"} pull {appname}", capture_output=False)

    # def remove_app(self, appname: str):
    #     print(f"Downloading docker images for applications...")
    #     run_command(f"docker compose -f {self.root / "etc/compose/applications.yml"} rm -sf {appname}", capture_output=False)


def main():

    try:
        instance_name = os.environ["INSTANCE_NAME"]
    except KeyError:
        print("Env variable INSTANCE_NAME must be set.")
        sys.exit(1)

    parser = argparse.ArgumentParser(description="MilleGrilles Application Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # install command
    install_parser = subparsers.add_parser("install")
    # Mutually exclusive group: --name or --url
    group = install_parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--name", help="Application name")
    group.add_argument("--url", help="Application download URL")
    
    install_parser.add_argument("--version", help="Application version")
    install_parser.add_argument("--env", choices=['dev', 'test', 'stable'], default='stable', help="Environment (default: stable)")
    install_parser.add_argument("--catalogue_url", help="Remote catalogue URL", default=DEFAULT_CATALOGUE_URL)
    install_parser.add_argument("--hash", help="SHA256 hash for verification")
    install_parser.add_argument("--root", help="MILLEGRILLES_ROOT directory")
    install_parser.add_argument("--noreload", action="store_true", help="Do not reload the systemd services (nginx, applications)")

    # uninstall command
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--name", required=True, help="Application name to uninstall")
    uninstall_parser.add_argument("--root", required=False, help="MILLEGRILLES_ROOT directory")

    # list command
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--env", choices=['dev', 'test', 'stable'], default='stable', help="Environment (default: stable)")
    list_parser.add_argument("--catalogue_url", help="Remote catalogue URL", default=DEFAULT_CATALOGUE_URL)

    # list-installed command
    list_installed_parser = subparsers.add_parser("list-installed")
    list_installed_parser.add_argument("--root", required=False, help="MILLEGRILLES_ROOT directory")

    # update command
    update_parser = subparsers.add_parser("update")
    update_parser.add_argument("-i", "--install", action="store_true", help="Install updates automatically")
    update_parser.add_argument("--env", choices=['dev', 'test', 'stable'], default='stable', help="Environment (default: stable)")
    update_parser.add_argument("--catalogue_url", help="Remote catalogue URL", default=DEFAULT_CATALOGUE_URL)
    update_parser.add_argument("--root", required=False, help="MILLEGRILLES_ROOT directory")

    args = parser.parse_args()
    root = getattr(args, 'root', None)
    if not root:
        try:
            root = os.environ["MILLEGRILLES_ROOT"]
        except KeyError:
            print("Env variable MILLEGRILLES_ROOT must be set.")
            sys.exit(1)

    html_dir = os.environ["MOUNT_NGINX_HTML"]

    manager = AppManager(root, html_dir, instance_name)

    if args.command == "install":
        if args.name:
            catalogue_url = args.catalogue_url
            if args.env != 'stable':
                catalogue_url = catalogue_url.replace('stable.json', f"{args.env}.json")
            print(f"Resolving {args.name} from {catalogue_url}...")
            catalogue = manager.fetch_json(catalogue_url)
            if args.name not in catalogue:
                print(f"Error: Application '{args.name}' not found in catalogue.")
                sys.exit(1)
            
            app_data = catalogue[args.name]
            if args.version and app_data.get('version') != args.version:
                print(f"Error: Version mismatch. Requested: {args.version}, Catalogue has: {app_data.get('version')}")
                sys.exit(1)
            
            manager.install_from_package(app_data['url'], app_data.get('sha256'), noreload=args.noreload)
        else:
            manager.install_from_package(args.url, args.hash, noreload=args.noreload)

    elif args.command == "uninstall":
        manager.uninstall(args.name)

    elif args.command == "list":
        catalogue_url = args.catalogue_url
        if args.env != 'stable':
            catalogue_url = catalogue_url.replace('stable.json', f"{args.env}.json")
        manager.list_available(catalogue_url)

    elif args.command == "list-installed":
        manager.list_installed()

    elif args.command == "update":
        catalogue_url = args.catalogue_url
        if args.env != 'stable':
            catalogue_url = catalogue_url.replace('stable.json', f"{args.env}.json")
        
        updates = manager.get_updates(catalogue_url)
        
        if not updates:
            print("All applications are up to date.")
        else:
            print(f"{'Name':<20} {'Current':<10} {'Available':<10}")
            print("-" * 40)
            for u in updates:
                print(f"{u['name']:<20} {u['current_version']:<10} {u['available_version']:<10}")

            if args.install:
                for u in updates:
                    print(f"\nUpdating {u['name']} from {u['current_version']} to {u['available_version']}...")
                    manager.install_from_package(u['url'], u['sha256'])
                print("\nAll updates completed.")


if __name__ == "__main__":
    main()
