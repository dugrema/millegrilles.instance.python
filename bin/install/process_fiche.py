import json
import sys
import os

def process_fiche(millegrilles_root):
    try:
        fiche_path = os.path.join(millegrilles_root, "etc", "fiche.json")
        if not os.path.exists(fiche_path):
            print(f"ERROR: {fiche_path} not found.")
            sys.exit(1)

        with open(fiche_path, 'r') as f:
            data = json.load(f)
        
        # Get millegrille certificate
        millegrille = data['contenu']['millegrille']
        ca_list = millegrille.get('ca', [])
        if ca_list:
            with open(os.path.join(millegrilles_root, "etc", "millegrille.pem"), 'w') as f:
                for cert in ca_list:
                    f.write(cert.strip() + "\n")
            print("OK_CERT")
        else:
            print("ERROR_CERT")
            sys.exit(1)
        
        # Get IDMG
        idmg = millegrille.get('idmg')
        if not idmg:
             print("ERROR_IDMG")
             sys.exit(1)
        print(f"IDMG={idmg}")
        
        # Get remote instance info
        instances = millegrille.get('instances', {})
        if not instances:
             print("ERROR_NO_INSTANCES")
             sys.exit(1)
             
        first_instance_id = next(iter(instances))
        instance_info = instances[first_instance_id]
        
        remote_host = instance_info.get('domaines', ["localhost"])[0]
        amqps_port = instance_info.get('ports', {}).get('amqps', 5673)
        https_mtls_port = instance_info.get('ports', {}).get('https_mtls', 443)
        
        with open(os.path.join(millegrilles_root, "etc", "fiche_env"), 'w') as f:
            f.write(f"MQ_HOSTNAME={remote_host}\n")
            f.write(f"MQ_PORT={amqps_port}\n")
            f.write(f"PORT_HTTPS_MTLS={https_mtls_port}\n")
        print("OK_ENV")
        
    except Exception as e:
        print(f"ERROR:{e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: process_fiche.py <MILLEGRILLES_ROOT>")
        sys.exit(1)
    
    process_fiche(sys.argv[1])
