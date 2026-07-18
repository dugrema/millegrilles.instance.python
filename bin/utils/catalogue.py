import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

def calculate_sha256(file_path):
    """Calculates the SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)
        return sha256_hash.hexdigest()
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error calculating hash: {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Maintain the application catalogue.")
    parser.add_argument("appname", help="Name of the application")
    parser.add_argument("version", help="Version of the application")
    parser.add_argument("file_path", help="Path to the application package file")
    parser.add_argument(
        "--catalogue_url", 
        default="etc/catalogue/applicationCatalogue.json",
        help="Path to the catalogue JSON file (default: etc/catalogue/applicationCatalogue.json)"
    )

    args = parser.parse_args()

    # Resolve catalogue path
    catalogue_path = Path(args.catalogue_url).resolve()

    # Load existing catalogue
    if catalogue_path.exists():
        try:
            with open(catalogue_path, 'r') as f:
                catalogue = json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Failed to parse JSON in {catalogue_path}. Is it valid?")
            sys.exit(1)
    else:
        print(f"Catalogue not found at {catalogue_path}. A new one will be created.")
        catalogue = {}

    # Calculate hash of the provided file
    sha256_hash = calculate_sha256(args.file_path)
    
    # Prepare URL (using file:// protocol for local files to ensure compatibility with curl)
    abs_file_path = Path(args.file_path).resolve()
    app_url = f"https://libs.millegrilles.com/archives/{args.appname}/{abs_file_path.name}"

    # Update or create entry
    if args.appname in catalogue:
        print(f"Updating existing entry for '{args.appname}'...")
        catalogue[args.appname].update({
            "version": args.version,
            "url": app_url,
            "sha256": sha256_hash
        })
    else:
        print(f"Creating new entry for '{args.appname}'...")
        catalogue[args.appname] = {
            "labels": {
                "en": args.appname
            },
            "version": args.version,
            "url": app_url,
            "sha256": sha256_hash
        }

    # Save the updated catalogue
    try:
        catalogue_path.parent.mkdir(parents=True, exist_ok=True)
        with open(catalogue_path, 'w') as f:
            json.dump(catalogue, f, indent=2)
        
        print(f"Successfully updated catalogue: {catalogue_path}")
        print(f"---")
        print(f"App:     {args.appname}")
        print(f"Version: {args.version}")
        print(f"Hash:    {sha256_hash}")
        print(f"URL:     {app_url}")
    except Exception as e:
        print(f"Error writing catalogue: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
