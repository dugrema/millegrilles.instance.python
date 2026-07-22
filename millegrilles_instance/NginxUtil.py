import json
from typing import Union

from millegrilles_instance.Configuration import ConfigurationInstance


def publish_to_nginx(configuration: ConfigurationInstance, path_fichier: str, contenu: Union[str, bytes, dict]):
    """
    Publishes a single static file to the nginx server.
    """
    path_nginx_fichier = configuration.path_millegrilles / "var/nginx/html" / path_fichier

    if isinstance(contenu, str):
        contenu = contenu.encode('utf-8')
    elif isinstance(contenu, dict):
        contenu = json.dumps(contenu).encode('utf-8')

    with open(path_nginx_fichier, 'wb') as output:
        output.write(contenu)
