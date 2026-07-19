import argparse
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import urllib.request
import yaml
from typing import Optional

DEFAULT_CATALOGUE_URL = "https://libs.millegrilles.com/archives/stable.json"

def run_command(command, env=None):
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True, env=env)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error executing command: {e}")
        print(f"Command: {e.cmd}")
        print(f"Stdout: {e.stdout}")
        print(f"Stderr: {e.stderr}")
        sys.exit(1)

def reload_nginx(instance_name: str):
    print(f"Reloading {instance_name}-nginx...")
    run_command(f"systemctl --user reload {instance_name}-nginx")

def reload_compose_applications(instance_name: str):
    print(f"Reloading {instance_name}-applications...")
    run_command(f"systemctl --user reload {instance_name}-applications")
    print(f"Generating certificates using {instance_name}-certs_updater...")
    run_command(f"systemctl --user start {instance_name}-certs_updater")

class AppManager:
    def __init__(self, root: str, instance_name: str):
        self.root = pathlib.Path(root)
        self.instance_name = instance_name
        self.etc_dir = self.root / "etc"
        self.var_dir = self.root / "var"

        self.installed_apps_file = self.etc_dir / "installed_applications.json"
        self.nginx_apps_conf_dir = self.etc_dir / "nginx" / "applications"
        self.nginx_apps_html_dir = self.var_dir / "nginx" / "html" / "applications"
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

        if os.path.exists(self.installed_apps_file):
            with open(self.installed_apps_file, 'r') as f:
                return json.load(f)
        return {}

    def save_installed_apps(self, apps):
        os.makedirs(os.path.dirname(self.installed_apps_file), exist_ok=True)
        with open(self.installed_apps_file, 'w') as f:
            json.dump(apps, f, indent=2)

    def install_from_package(self, pkg_url: str, expected_hash: Optional[str]):
        with tempfile.TemporaryDirectory() as tmp_dir:
            pkg_path = os.path.join(tmp_dir, "package.tar.gz")
            print(f"Downloading {pkg_url}...")
            run_command(f"curl -sL {pkg_url} -o {pkg_path}")
            
            if expected_hash:
                print("Verifying hash...")
                actual_hash = run_command(f"sha256sum {pkg_path} | awk '{{print $1}}'")
                if actual_hash != expected_hash:
                    print(f"Error: Hash mismatch! Expected {expected_hash}, got {actual_hash}")
                    sys.exit(1)
            
            extract_dir = os.path.join(tmp_dir, "extracted")
            os.makedirs(extract_dir, exist_ok=True)
            print("Extracting package...")
            run_command(f"tar -xf {pkg_path} -C {extract_dir} --strip-components=1")
 
            # 1. Read metadata.json
            metadata_file = os.path.join(extract_dir, "metadata.json")
            if not os.path.exists(metadata_file):
                print("Error: metadata.json not found in package.")
                sys.exit(1)
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            name = metadata['name']
            version = metadata['version']
            app_path = metadata.get('path')

            print(f"Installing {name} (version: {version}, path: {app_path})...")
 
            # 2. Handle Nginx Config
            nginx_conf = os.path.join(extract_dir, "nginx.conf")
            if os.path.exists(nginx_conf):
                dest_nginx_conf = os.path.join(self.nginx_apps_conf_dir, f"{name}.conf")
                print(f"Configuring Nginx: {dest_nginx_conf}")
                run_command(f"cp {nginx_conf} {dest_nginx_conf}")
 
            # 3. Handle Docker Compose
            docker_compose = os.path.join(extract_dir, "docker-compose.yml")
            if os.path.exists(docker_compose):
                dest_docker_compose = self.compose_apps_dir / f"{name}.yml"
                print(f"Configuring Docker Compose: {dest_docker_compose}")
                run_command(f"cp {docker_compose} {dest_docker_compose}")
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
            app_files_dir = os.path.join(extract_dir, "files")
            if app_path and os.path.exists(app_files_dir):
                dest_html_dir = os.path.join(self.nginx_apps_html_dir, app_path)
                print(f"Deploying application files to {dest_html_dir}...")
                if os.path.exists(dest_html_dir):
                    run_command(f"rm -rf {dest_html_dir}")
                os.makedirs(dest_html_dir, exist_ok=True)
                run_command(f"cp -r {app_files_dir}/. {dest_html_dir}/")

            # 5. Update local catalogue metadata for this app
            installed_apps = self.get_installed_apps()
            installed_apps[name] = metadata
            self.save_installed_apps(installed_apps)
 
            # 6. Reload middleware
            if app_path or nginx_conf:
                reload_nginx(self.instance_name)
            if docker_compose:
                reload_compose_applications(self.instance_name)

            print("Installation complete.")


    def uninstall(self, name, root_path):
        installed_apps = self.get_installed_apps()
        if name not in installed_apps:
            print(f"Error: Application '{name}' is not installed.")
            sys.exit(1)

        app_info = installed_apps[name]
        app_url = app_info['url']
        app_path = app_url.replace("/applications/", "")

        print(f"Uninstalling {name}...")

        # 1. Remove Nginx Config
        nginx_conf = os.path.join(self.nginx_apps_conf_dir, f"{name}.conf")
        if os.path.exists(nginx_conf):
            print(f"Removing Nginx config: {nginx_conf}")
            os.remove(nginx_conf)

        # 2. Remove Docker Compose
        docker_compose = os.path.join(self.compose_apps_dir, f"{name}.yml")
        if os.path.exists(docker_compose):
            print(f"Removing Docker Compose file: {docker_compose}")
            os.remove(docker_compose)

        # 3. Remove Application Files
        dest_html_dir = os.path.join(self.nginx_apps_html_dir, app_path)
        if os.path.exists(dest_html_dir):
            print(f"Removing application files: {dest_html_dir}")
            run_command(f"rm -rf {dest_html_dir}")

        # 4. Update local catalogue
        del installed_apps[name]
        self.save_installed_apps(installed_apps)

        # 5. Restart Nginx
        reload_nginx()
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
        for name, info in installed_apps.items():
            print(f"{name:<20} {info.get('version', 'N/A'):<10} {info.get('url', 'N/A')}")

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

    # uninstall command
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--name", required=True, help="Application name to uninstall")
    uninstall_parser.add_argument("--root", required=True, help="MILLEGRILLES_ROOT directory")

    # list command
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--env", choices=['dev', 'test', 'stable'], default='stable', help="Environment (default: stable)")
    list_parser.add_argument("--catalogue_url", help="Remote catalogue URL", default=DEFAULT_CATALOGUE_URL)

    # list-installed command
    list_installed_parser = subparsers.add_parser("list-installed")
    list_installed_parser.add_argument("--root", required=True, help="MILLEGRILLES_ROOT directory")

    args = parser.parse_args()
    root = getattr(args, 'root', None)
    if not root:
        try:
            root = os.environ["MILLEGRILLES_ROOT"]
        except KeyError:
            print("Env variable MILLEGRILLES_ROOT must be set.")
            sys.exit(1)

    manager = AppManager(root, instance_name)

    if args.command == "install":
        if args.name:
            print(f"Resolving {args.name} from {args.catalogue_url}...")
            catalogue = manager.fetch_json(args.catalogue_url)
            if args.name not in catalogue:
                print(f"Error: Application '{args.name}' not found in catalogue.")
                sys.exit(1)
            
            app_data = catalogue[args.name]
            if args.version and app_data.get('version') != args.version:
                print(f"Error: Version mismatch. Requested: {args.version}, Catalogue has: {app_data.get('version')}")
                sys.exit(1)
            
            manager.install_from_package(app_data['url'], app_data.get('sha256'))
        else:
            manager.install_from_package(args.url, args.hash)

    elif args.command == "uninstall":
        manager.uninstall(args.name, args.root)

    elif args.command == "list":
        manager.list_available(args.catalogue_url)

    elif args.command == "list-installed":
        manager.list_installed()

if __name__ == "__main__":
    main()
