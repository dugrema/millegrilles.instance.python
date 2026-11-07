#!/usr/bin/env python3
import os
import pathlib
from typing import Optional

import sys
import argparse
from datetime import timedelta

from millegrilles_messages.certificats.Generes import ajouter_exchanges, ajouter_roles, EnveloppeCsr
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages import Constantes
from cryptography.x509.base import CertificateBuilder

def main():
    parser = argparse.ArgumentParser(description="Generate a node manager certificate using MilleGrilles library from an intermediate CA certificate.")
    parser.add_argument("--key", required=True, help="Path to the combined Intermediate CA PEM (key + cert)")
    # parser.add_argument("--millegrilles-root", required=False, help="MILLEGRILLES_ROOT directory")
    parser.add_argument("--password", required=False, help="Password for the CA private key")
    parser.add_argument("--days", type=int, default=93, help="Validity days for the node certificate")
    parser.add_argument("--public", action="store_true", help="Sign a 1.public certificate instead of 2.prive")

    args = parser.parse_args()

    # instance_id = args.instance_id
    days = args.days
    intermediate_ca_pem_path: str = args.key
    # if not intermediate_ca_pem_path:
    #     if args.millegrilles_root:
    #         millegrilles_root = pathlib.Path(args.millegrilles_root)
    #     else:
    #         millegrilles_root = pathlib.Path(os.environ["MILLEGRILLES_ROOT"])
    #     intermediate_ca_pem_path = millegrilles_root / "secrets/certissuer" / "signing_ca.pem"

    intermediate_ca_password = args.ca_password

    if not os.path.exists(intermediate_ca_pem_path):
        print(f"Error: CA PEM not found at {intermediate_ca_pem_path}")
        sys.exit(1)

    # 1. Load the CA
    intermediate_key = CleCertificat.from_files(intermediate_ca_pem_path, intermediate_ca_pem_path, password=intermediate_ca_password)
    instance_id = intermediate_key.enveloppe.subject_common_name

    # 2. Generate a CSR
    idmg = intermediate_key.enveloppe.idmg
    print(f"[INFO] Retrieved INSTANCE_ID {instance_id} and IDMG {idmg} from Signing CA")
    print("Paste the CSR produced by the installer of the satellite manager node and then press CTRL+D")
    csr_str = sys.stdin.read()
    if not csr_str:
        print("Error: No certificate request (CSR) provided.")
        sys.exit(1)

    # csr_genere = CleCsrGenere.build(cn=instance_id, idmg=idmg, type_genere=TypeGenere.ED25519)
    csr_genere = EnveloppeCsr.from_str(csr_str)

    # 3. Sign the CSR
    builder = CertificateBuilder()
    if args.public:
        # 1.public
        exchanges = [Constantes.SECURITE_PUBLIC]
    else:
        # 2.prive
        exchanges = [Constantes.SECURITE_PRIVE, Constantes.SECURITE_PUBLIC]
    builder = ajouter_exchanges(builder, exchanges)
    builder = ajouter_roles(builder, [Constantes.DOMAINE_INSTANCE, 'manager'])

    print(f"[INFO] Signing certificate for {instance_id} for {days} days...")
    enveloppe_generee = csr_genere.signer(intermediate_key, role='manager', builder=builder, duree=timedelta(days=days))

    # 4. Display the result
    node_cert_pems = enveloppe_generee.chaine_pem()
    print("Use this new certificate chain in the satellite manager node installation script\n\n")
    print("".join(node_cert_pems))
    print("\n")

if __name__ == "__main__":
    main()
