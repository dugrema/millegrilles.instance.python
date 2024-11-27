import logging
import pathlib

from typing import Optional

from millegrilles_instance.Context import InstanceContext

LOGGER = logging.getLogger(__name__)


def ajouter_fichier_configuration(context: InstanceContext, path_nginx_modules: pathlib.Path, nom_fichier: str,
                                  contenu: str, params: Optional[dict] = None) -> bool:
    if params is None:
        params = dict()
    else:
        params = params.copy()

    configuration = context.configuration
    params.update({
        'nodename': context.hostname,
        'hostname': context.hostname,
        'instance_url': 'https://%s:2443' % context.hostname,
        'certissuer_url': 'http://%s:2080' % context.hostname,
        'midcompte_url': 'https://midcompte:2444',
        'MQ_HOST': configuration.mq_hostname,
    })

    path_destination = pathlib.Path(path_nginx_modules, nom_fichier)
    try:
        contenu = contenu.format(**params)
    except (KeyError, ValueError):
        LOGGER.exception("Erreur configuration fichier %s\n%s\n" % (nom_fichier, contenu))
        return False

    changement_detecte = False
    try:
        with open(path_destination, 'r') as fichier_existant:
            contenu_existant = fichier_existant.read()
            if contenu_existant != contenu:
                LOGGER.debug("ajouter_fichier_configuration Detecte changement fichier config\nOriginal\n%s\n-------\nNouveau\n%s" % (contenu_existant, contenu))
                changement_detecte = True
    except FileNotFoundError:
        changement_detecte = True

    if changement_detecte:
        with open(path_destination, 'w') as fichier_output:
            fichier_output.write(contenu)

    return changement_detecte
