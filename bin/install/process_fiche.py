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
        millegrille = data['millegrille']
        with open(os.path.join(millegrilles_root, "etc", "millegrille.pem"), 'w') as f:
            f.write(millegrille)
        print("OK_CERT")

        parsed_contenu = json.loads(data['contenu'])

        # Get IDMG
        idmg = parsed_contenu.get('idmg')
        if not idmg:
             print("ERROR_IDMG")
             sys.exit(1)
        print(f"IDMG={idmg}")
        
        # Get remote instance info
        instances = parsed_contenu.get('instances', {})
        if not instances:
             print("ERROR_NO_INSTANCES")
             sys.exit(1)

        for instance_id, value in instances.items():
            if value['securite'] == '3.protege':
                remote_host = value['domaines'][0]
                amqps_port = value['ports']['amqps']
                https_mtls_port = value['ports']['https_mtls']
                break
        else:
            print("Instance 3.protege not found in the system card")
            sys.exit(1)

        with open(os.path.join(millegrilles_root, "etc", "fiche_env"), 'w') as f:
            f.write(f"MQ_HOSTNAME={remote_host}\n")
            f.write(f"MQ_PORT={amqps_port}\n")
            f.write(f"MTLS_PORT={https_mtls_port}\n")
            f.write(f"IDMG={idmg}\n")
        print("OK_ENV")
        
    except Exception as e:
        print(f"ERROR:{e}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: process_fiche.py <MILLEGRILLES_ROOT>")
        sys.exit(1)
    
    process_fiche(sys.argv[1])
