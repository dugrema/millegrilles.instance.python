#!/usr/bin/env python3
import json
import os
import pathlib
import sys
import argparse
from datetime import timedelta

from cryptography.x509 import CertificateSigningRequestBuilder

from millegrilles_messages.certificats.Generes import CleCsrGenere, TypeGenere, ajouter_exchanges, ajouter_roles
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages import Constantes
from cryptography.x509.base import CertificateBuilder

from millegrilles_messages.messages.EnveloppeCertificat import EnveloppeCertificat


def load_dotenv(file: os.PathLike):
    with open(file) as f:
        config = {
            k.strip(): v.strip().strip('"')
            for line in f
            if line.strip() and not line.startswith("#")
            for k, v in [line.strip().split("=", 1)]
        }
    return config


def main():
    parser = argparse.ArgumentParser(description="Generate a node certificate using MilleGrilles library.")
    parser.add_argument("--millegrilles-root", required=False, help="MILLEGRILLES_ROOT directory")

    args = parser.parse_args()

    if args.millegrilles_root:
        millegrilles_root = pathlib.Path(args.millegrilles_root)
    else:
        millegrilles_root = pathlib.Path(os.environ["MILLEGRILLES_ROOT"])

    # Load parameters from config.env
    config_path = pathlib.Path(millegrilles_root) / "config.env"
    config = load_dotenv(config_path)

    instance_id = config['INSTANCE_ID']
    idmg = config['IDMG']

    # 1. Generate and print the CSR, wait for Certificate PEM
    csr_genere = CleCsrGenere.build(cn=instance_id, idmg=idmg, type_genere=TypeGenere.ED25519)

    print(f"Use this CSR to generate the node manager certificate\n{csr_genere.get_pem_csr()}\nPaste the new certificate here, press CTRL+D on a new line (ENTER) to submit.")

    pem_certificate = sys.stdin.read()
    if not pem_certificate:
        print("Error: No certificate provided.")
        sys.exit(1)

    # 2. Parse and verify
    cert = EnveloppeCertificat.from_pem(pem_certificate)
    if cert.idmg != idmg:
        print("Error: Invalid certificate IDMG.")
        sys.exit(1)
    if cert.subject_common_name != instance_id:
        print("Error: Invalid instance id.")
        sys.exit(1)

    # 3. Save the result
    node_pem_path = os.path.join(millegrilles_root, "secrets/manager.pem")
    os.makedirs(os.path.dirname(node_pem_path), exist_ok=True)

    with open(node_pem_path, 'w') as f:
        f.write(csr_genere.get_pem_cle())
        f.write("\n".join(cert.chaine_pem()))
        f.write("\n")

    print(f"[OK] Node certificate and key written to {node_pem_path}")

if __name__ == "__main__":
    main()
