import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.request

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

def restart_nginx(root):
    instance_name = os.environ.get("INSTANCE_NAME")
    if not instance_name:
        print("Warning: INSTANCE_NAME not set, skipping nginx restart.")
        return

    print(f"Restarting {instance_name}-nginx...")
    run_command(f"systemctl --user restart {instance_name}-nginx")

class AppManager:
    def __init__(self, root):
        self.root = os.path.abspath(root)
        self.etc_dir = os.path.join(self.root, "etc")
        self.var_dir = os.path.join(self.root, "var")
        self.installed_apps_file = os.path.join(self.etc_dir, "installed_applications.json")
        
        self.nginx_apps_dir = os.path.join(self.etc_dir, "nginx", "applications")
        self.compose_apps_dir = os.path.join(self.etc_dir, "compose", "applications")
        self.html_apps_dir = os.path.join(self.var_dir, "nginx", "html", "applications")
        
        # Ensure directories exist
        os.makedirs(self.nginx_apps_dir, exist_ok=True)
        os.makedirs(self.compose_apps_dir, exist_ok=True)
        os.makedirs(self.html_apps_dir, exist_ok=True)

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

    def install_from_package(self, pkg_url, expected_hash):
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
            run_command(f"tar -xzf {pkg_path} -C {extract_dir} --strip-components=1")
 
            # 1. Read metadata.json
            metadata_file = os.path.join(extract_dir, "metadata.json")
            if not os.path.exists(metadata_file):
                print("Error: metadata.json not found in package.")
                sys.exit(1)
            
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)
            
            name = metadata['name']
            version = metadata['version']
            app_path = metadata['path']
            labels = metadata.get('labels', {})
            
            print(f"Installing {name} (version: {version}, path: {app_path})...")
 
            # 2. Handle Nginx Config
            nginx_conf = os.path.join(extract_dir, "nginx.conf")
            if os.path.exists(nginx_conf):
                dest_nginx_conf = os.path.join(self.nginx_apps_dir, f"{name}.conf")
                print(f"Configuring Nginx: {dest_nginx_conf}")
                run_command(f"cp {nginx_conf} {dest_nginx_conf}")
 
            # 3. Handle Docker Compose
            docker_compose = os.path.join(extract_dir, "docker-compose.yml")
            if os.path.exists(docker_compose):
                dest_docker_compose = os.path.join(self.compose_apps_dir, f"{name}.yml")
                print(f"Configuring Docker Compose: {dest_docker_compose}")
                run_command(f"cp {docker_compose} {dest_docker_compose}")
 
            # 4. Handle Application Files
            app_files_dir = os.path.join(extract_dir, "files")
            if os.path.exists(app_files_dir):
                dest_html_dir = os.path.join(self.html_apps_dir, app_path)
                print(f"Deploying application files to {dest_html_dir}...")
                if os.path.exists(dest_html_dir):
                    run_command(f"rm -rf {dest_html_dir}")
                os.makedirs(dest_html_dir, exist_ok=True)
                run_command(f"cp -r {app_files_dir}/. {dest_html_dir}/")
 
            # 5. Update local catalogue
            installed_apps = self.get_installed_apps()
            installed_apps[name] = {
                "labels": labels,
                "version": version,
                "url": f"/applications/{app_path}"
            }
            self.save_installed_apps(installed_apps)
 
            # 6. Restart Nginx
            restart_nginx(self.root)
            print("Installation complete.")


    def uninstall(self, name, root_path):
        root = os.path.abspath(root_path)
        manager = AppManager(root)

        installed_apps = manager.get_installed_apps()
        if name not in installed_apps:
            print(f"Error: Application '{name}' is not installed.")
            sys.exit(1)

        app_info = installed_apps[name]
        app_url = app_info['url']
        app_path = app_url.replace("/applications/", "")

        print(f"Uninstalling {name}...")

        # 1. Remove Nginx Config
        nginx_conf = os.path.join(manager.nginx_apps_dir, f"{name}.conf")
        if os.path.exists(nginx_conf):
            print(f"Removing Nginx config: {nginx_conf}")
            os.remove(nginx_conf)

        # 2. Remove Docker Compose
        docker_compose = os.path.join(manager.compose_apps_dir, f"{name}.yml")
        if os.path.exists(docker_compose):
            print(f"Removing Docker Compose file: {docker_compose}")
            os.remove(docker_compose)

        # 3. Remove Application Files
        dest_html_dir = os.path.join(manager.html_apps_dir, app_path)
        if os.path.exists(dest_html_dir):
            print(f"Removing application files: {dest_html_dir}")
            run_command(f"rm -rf {dest_html_dir}")

        # 4. Update local catalogue
        del installed_apps[name]
        manager.save_installed_apps(installed_apps)

        # 5. Restart Nginx
        restart_nginx(root)
        print("Uninstallation complete.")

    def list_available(self, catalogue_url=None):
        if not catalogue_url:
            catalogue_url = "https://libs.millegrilles.com/archives/stable.json"
        print(f"Fetching available applications from {catalogue_url}...")
        catalogue = self.fetch_json(catalogue_url)
        
        if not catalogue:
            print("No applications available.")
            return

        print(f"{'Name':<20} {'Version':<10} {'Labels'}")
        print("-" * 50)
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
    install_parser.add_argument("--catalogue_url", help="Remote catalogue URL")
    install_parser.add_argument("--hash", help="SHA256 hash for verification")
    install_parser.add_argument("--root", help="MILLEGRILLES_ROOT directory")

    # uninstall command
    uninstall_parser = subparsers.add_parser("uninstall")
    uninstall_parser.add_argument("--name", required=True, help="Application name to uninstall")
    uninstall_parser.add_argument("--root", required=True, help="MILLEGRILLES_ROOT directory")

    # list command
    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--env", choices=['dev', 'test', 'stable'], default='stable', help="Environment (default: stable)")
    list_parser.add_argument("--catalogue_url", help="Remote catalogue URL")

    # list-installed command
    list_installed_parser = subparsers.add_parser("list-installed")
    list_installed_parser.add_argument("--root", required=True, help="MILLEGRILLES_ROOT directory")

    args = parser.parse_args()
    root = getattr(args, 'root', None)
    if not root:
        root = os.environ.get("MILLEGRILLES_ROOT", ".")

    manager = AppManager(root)

    if args.command == "install":
        if args.name:
            cat_url = args.catalogue_url if args.catalogue_url else f"https://localhost/catalogue/{args.env}.json"
            print(f"Resolving {args.name} from {cat_url}...")
            catalogue = manager.fetch_json(cat_url)
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
