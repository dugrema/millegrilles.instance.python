#!/usr/bin/env python3
import os
import pathlib
import sys
import argparse
from datetime import timedelta

from millegrilles_messages.certificats.Generes import ajouter_exchanges, ajouter_roles, EnveloppeCsr
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages import Constantes
from cryptography.x509.base import CertificateBuilder

def main():
    parser = argparse.ArgumentParser(description="Generate a node certificate using MilleGrilles library.")
    parser.add_argument("--millegrilles-root", required=False, help="MILLEGRILLES_ROOT directory")
    parser.add_argument("--ca-pem", required=False, help="Path to the combined CA PEM (key + cert)")
    parser.add_argument("--ca-password", required=False, help="Password for the CA private key")
    parser.add_argument("--days", type=int, default=93, help="Validity days for the node certificate")
    parser.add_argument("--public", action="store_true", help="Sign a 1.public certificate instead of 2.prive")

    args = parser.parse_args()

    if args.millegrilles_root:
        millegrilles_root = pathlib.Path(args.millegrilles_root)
    else:
        millegrilles_root = pathlib.Path(os.environ["MILLEGRILLES_ROOT"])

    # instance_id = args.instance_id
    days = args.days
    ca_pem_path = args.ca_pem
    if not ca_pem_path:
        ca_pem_path = millegrilles_root / "secrets/certissuer" / "signing_ca.pem"
    ca_password = args.ca_password

    if not os.path.exists(ca_pem_path):
        print(f"Error: CA PEM not found at {ca_pem_path}")
        sys.exit(1)

    # 1. Load the CA
    with open(ca_pem_path, 'r') as f:
        ca_pem_content = f.read()
    
    import re
    key_match = re.search(r'-----BEGIN\s+PRIVATE\s+KEY-----.*?-----END\s+PRIVATE\s+KEY-----', ca_pem_content, re.DOTALL)
    cert_match = re.search(r'-----BEGIN\s+CERTIFICATE-----.*?-----END\s+CERTIFICATE-----', ca_pem_content, re.DOTALL)
    
    if not key_match or not cert_match:
        print("Error: Could not find both Key and Certificate in the CA PEM")
        sys.exit(1)
        
    ca_key_pem = key_match.group(0)
    ca_cert_pem = cert_match.group(0)

    cle_ca = CleCertificat.from_pems(ca_key_pem, ca_cert_pem, password=ca_password)
    instance_id = cle_ca.enveloppe.subject_common_name

    # 2. Generate a CSR
    idmg = cle_ca.enveloppe.idmg
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
    enveloppe_generee = csr_genere.signer(cle_ca, role='manager', builder=builder, duree=timedelta(days=days))

    # 4. Save the result
    node_pem_path = os.path.join(millegrilles_root, "secrets/manager.pem")
    os.makedirs(os.path.dirname(node_pem_path), exist_ok=True)

    # node_key_pem = cle_node_genere.get_pem_cle()
    node_cert_pems = enveloppe_generee.chaine_pem()
    print("Use this new certificate chain in the satellite manager node installation script\n\n")
    print("".join(node_cert_pems))
    print("\n")

if __name__ == "__main__":
    main()
