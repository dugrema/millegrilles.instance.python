#!/usr/bin/env python3
import argparse
import hashlib
import json
import tarfile
import sys
from pathlib import Path

def calculate_sha256(file_path: Path) -> str:
    """Calculates the SHA256 checksum of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def get_metadata_from_archive(archive_path: Path) -> dict:
    """Extracts metadata.json from a tar.gz archive."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            # Find the metadata.json file, allowing for optional ./ prefix
            metadata_member = None
            for member in tar.getmembers():
                if member.name.endswith("metadata.json"):
                    metadata_member = member
                    break
            
            if metadata_member is None:
                raise ValueError("metadata.json not found in archive")
                
            f = tar.extractfile(metadata_member)
            if f is None:
                raise ValueError("Could not extract metadata.json from archive")
            return json.load(f)
    except json.JSONDecodeError:
        raise ValueError("metadata.json is not valid JSON")
    except Exception as e:
        raise ValueError(f"Error reading archive: {e}")

def delete_module(catalogue_path: Path, module_name: str):
    """Removes a module from the catalogue."""
    if not catalogue_path.exists():
        raise FileNotFoundError(f"Catalogue file not found: {catalogue_path}")

    with open(catalogue_path, "r") as f:
        catalogue = json.load(f)

    if module_name not in catalogue:
        raise ValueError(f"Module '{module_name}' not found in catalogue")

    del catalogue[module_name]

    # Sort and write back
    sorted_catalogue = {k: catalogue[k] for k in sorted(catalogue.keys())}

    with open(catalogue_path, "w") as f:
        json.dump(sorted_catalogue, f, indent=2)

    print(f"Successfully deleted module: {module_name} from {catalogue_path}")


def main():
    parser = argparse.ArgumentParser(description="MilleGrilles Application Catalogue Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    update_parser = subparsers.add_parser("update", help="Update the application catalogue")
    update_parser.add_argument("catalogue_path", type=str, help="Path to the catalogue JSON file")
    update_parser.add_argument("--archive", type=str, required=True, help="Path to the .tar.gz archive")
    update_parser.add_argument("--baseurl", type=str, required=True, help="Base URL for the archive")

    delete_parser = subparsers.add_parser("delete", help="Delete a module from the application catalogue")
    delete_parser.add_argument("catalogue_path", type=str, help="Path to the catalogue JSON file")
    delete_parser.add_argument("--module", type=str, required=True, help="Name of the module to delete")

    args = parser.parse_args()

    if args.command == "update":
        catalogue_path = Path(args.catalogue_path)
        archive_path = Path(args.archive)
        base_url = args.baseurl

        try:
            update_catalogue(catalogue_path, archive_path, base_url)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
    elif args.command == "delete":
        catalogue_path = Path(args.catalogue_path)
        module_name = args.module

        try:
            delete_module(catalogue_path, module_name)
        except Exception as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)

if __name__ == "__main__":
    main()
