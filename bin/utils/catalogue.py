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

def update_catalogue(catalogue_path: Path, archive_path: Path, base_url: str):
    """Updates the catalogue JSON with information from the archive."""
    # 1. Extract information
    sha256 = calculate_sha256(archive_path)
    metadata = get_metadata_from_archive(archive_path)
    
    name = metadata.get("name")
    version = metadata.get("version")
    labels = metadata.get("labels")
    
    if not all([name, version, labels]):
        raise ValueError("Metadata must contain 'name', 'version', and 'labels'")
    
    # 2. Construct entry
    # Ensure base_url ends with a slash and archive name doesn't start with one
    archive_name = archive_path.name
    if not base_url.endswith('/'):
        base_url += '/'
    url = f"{base_url}{archive_name}"
    
    new_entry = {
        "labels": labels,
        "version": version,
        "url": url,
        "sha256": sha256
    }
    
    # 3. Update catalogue
    catalogue = {}
    if catalogue_path.exists():
        try:
            with open(catalogue_path, "r") as f:
                catalogue = json.load(f)
        except json.JSONDecodeError:
            print(f"Warning: {catalogue_path} is not a valid JSON file. Overwriting it.")
    
    catalogue[name] = new_entry
    
    # 4. Sort and write back
    # Python dictionaries are ordered by insertion order since 3.7. 
    # To sort by key, we create a new dict from sorted items.
    sorted_catalogue = {k: catalogue[k] for k in sorted(catalogue.keys())}
    
    with open(catalogue_path, "w") as f:
        json.dump(sorted_catalogue, f, indent=2)
    
    print(f"Successfully updated catalogue: {catalogue_path}")
    print(f"Added/Updated entry: {name} (version {version})")

def main():
    parser = argparse.ArgumentParser(description="MilleGrilles Application Catalogue Manager")
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    update_parser = subparsers.add_parser("update", help="Update the application catalogue")
    update_parser.add_argument("catalogue_path", type=str, help="Path to the catalogue JSON file")
    update_parser.add_argument("--archive", type=str, required=True, help="Path to the .tar.gz archive")
    update_parser.add_argument("--baseurl", type=str, required=True, help="Base URL for the archive")

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

if __name__ == "__main__":
    main()
