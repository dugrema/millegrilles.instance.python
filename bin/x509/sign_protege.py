#!/usr/bin/env python3
import os
import sys
import argparse
from datetime import timedelta

from millegrilles_messages.certificats.Generes import CleCsrGenere, TypeGenere, ajouter_exchanges, ajouter_roles
from millegrilles_messages.messages.CleCertificat import CleCertificat
from millegrilles_messages.messages import Constantes
from cryptography.x509.base import CertificateBuilder

def main():
    parser = argparse.ArgumentParser(description="Generate a node certificate using MilleGrilles library.")
    parser.add_argument("--millegrilles-root", required=True, help="MILLEGRILLES_ROOT directory")
    parser.add_argument("--instance-id", required=True, help="INSTANCE_ID")
    parser.add_argument("--ca-pem", required=True, help="Path to the combined CA PEM (key + cert)")
    parser.add_argument("--ca-password", required=False, help="Password for the CA private key")
    parser.add_argument("--days", type=int, default=31, help="Validity days for the node certificate")
    parser.add_argument("--instanceid", required=False, type=str, help="INSTANCE_ID to use")

    args = parser.parse_args()

    instance_id = args.instance_id or os.environ['INSTANCE_ID']

    millegrilles_root = args.millegrilles_root
    # instance_id = args.instance_id
    days = args.days
    ca_pem_path = args.ca_pem
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

    # 2. Generate a CSR
    idmg = cle_ca.enveloppe.idmg
    print(f"[INFO] Retrieved INSTANCE_ID {instance_id} and IDMG {idmg} from Signing CA")

    csr_genere = CleCsrGenere.build(cn=instance_id, idmg=idmg, type_genere=TypeGenere.ED25519)

    # 3. Sign the CSR
    builder = CertificateBuilder()
    exchanges = [Constantes.SECURITE_PROTEGE, Constantes.SECURITE_PRIVE, Constantes.SECURITE_PUBLIC]
    builder = ajouter_exchanges(builder, exchanges)
    builder = ajouter_roles(builder, [Constantes.DOMAINE_INSTANCE, 'manager'])

    print(f"[INFO] Signing certificate for {instance_id} for {days} days...")
    cle_node_genere = csr_genere.signer(cle_ca, role='manager', builder=builder, duree=timedelta(days=days))

    # 4. Save the result
    node_pem_path = os.path.join(millegrilles_root, "secrets/manager.pem")
    os.makedirs(os.path.dirname(node_pem_path), exist_ok=True)

    node_key_pem = cle_node_genere.get_pem_cle()
    node_cert_pems = cle_node_genere.get_pem_certificat()

    with open(node_pem_path, 'w') as f:
        f.write(node_key_pem)
        f.write("".join(node_cert_pems))
        f.write("\n")

    print(f"[OK] Node certificate and key written to {node_pem_path}")

if __name__ == "__main__":
    main()
