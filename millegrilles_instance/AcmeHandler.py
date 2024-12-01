import asyncio
import logging

from docker.models.containers import Container
from os import path
from typing import Optional

from millegrilles_messages.docker.DockerHandler import CommandeDocker, DockerClient, DockerHandlerException


class CommandeAcmeIssue(CommandeDocker):
    """
    Permet de faire un issue pour recuperer un certificat SSL web
    """

    def __init__(self, domain: str, params: Optional[dict] = None):
        super().__init__()
        self.__domain = domain
        self.__params = params

        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.facteur_throttle = 0.1

    async def executer(self, docker_client: DockerClient):
        container = await asyncio.to_thread(trouver_acme, docker_client)
        try:
            exit_code, str_resultat = self.issue(container)
            await self._callback_asyncio({'code': exit_code, 'resultat': str_resultat})
        except Exception as e:
            self.__logger.exception("Erreur executer()")
            await self._callback_asyncio({'code': -1, 'resultat': str(e)})

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info

    def issue(self, container: Container):
        params = self.__params or dict()
        commande_str, environment = generer_issue_str(self.__domain, params)
        exit_code, bytes_resultat = container.exec_run(commande_str, environment=environment)
        str_resultat = bytes_resultat.decode('utf-8')
        return exit_code, str_resultat


class CommandeAcmeExtractCertificates(CommandeDocker):
    """
    Copie les certificats vers un volume local
    """

    def __init__(self, domain: str, extract_directory='/root'):
        super().__init__()
        self.__logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
        self.__domain = domain
        self.__directory = extract_directory
        self.facteur_throttle = 0.1

    async def executer(self, docker_client: DockerClient):
        container = await asyncio.to_thread(trouver_acme, docker_client)
        try:
            exit_code, str_resultat, key_pem, cert_pem = self.get_certificat(container)
            await self._callback_asyncio({'code': exit_code, 'resultat': str_resultat, 'key': key_pem, 'cert': cert_pem})
        except AcmeNonDisponibleException:
            await self._callback_asyncio({'code': -2})
        except Exception as e:
            self.__logger.exception("Erreur executer()")
            await self._callback_asyncio({'code': -1, 'resultat': str(e)})

    def get_certificat(self, container: Container):
        key_file_path = path.join(self.__directory, 'key.pem')
        cert_file_path = path.join(self.__directory, 'cert.pem')

        str_cmd = """ \
            acme.sh --install-cert -d %s \
            --key-file %s \
            --fullchain-file %s
        """ % (self.__domain, key_file_path, cert_file_path)

        exit_code, bytes_resultat = container.exec_run(str_cmd)
        str_resultat = bytes_resultat.decode('utf-8')

        if exit_code == 0:
            # Extraire certificats du directory
            exit_code, key_pem = container.exec_run('cat %s' % key_file_path)
            key_pem = key_pem.decode('utf-8')
            exit_code, cert_pem = container.exec_run('cat %s' % cert_file_path)
            cert_pem = cert_pem.decode('utf-8')
        else:
            self.__logger.error("Erreur CommandeAcmeExtractCertificates (code: %d)\n%s" % (exit_code, str_resultat))
            key_pem = None
            cert_pem = None

        return exit_code, str_resultat, key_pem, cert_pem

    async def get_resultat(self) -> dict:
        resultat = await self.attendre()
        info = resultat['args'][0]
        return info


def generer_issue_str(domain: str, params: dict) -> (str, dict):
    """
    Obtient un nouveau certificat web TLS avec LetsEncrypt
    """
    # Aller chercher le certificat SSL de LetsEncrypt
    mode_test = params.get('modeTest') or False
    force = params.get('force') or False
    mode_creation = params.get('modeCreation')

    params_environnement = dict()
    params_secrets = dict()

    methode = {
        'modeCreation': mode_creation,
        'params_environnement': params_environnement,
    }

    if mode_creation == 'dns_cloudns':
        subid = params['cloudns_subauthid']
        params_environnement["CLOUDNS_SUB_AUTH_ID"] = subid
        params_secrets["CLOUDNS_AUTH_PASSWORD"] = params['cloudns_password']
        commande_str = '--dns dns_cloudns'
    else:
        commande_str = '--webroot /usr/share/nginx/html'

    try:
        # Utiliser dnssleep, la detection de presence du record TXT marche rarement
        dnssleep = params['dnssleep']
        methode['dnssleep'] = dnssleep
        commande_str = commande_str + ' --dnssleep %s' % str(dnssleep)
    except KeyError:
        pass

    # Ajouter le domaine principal
    commande_str = commande_str + ' -d %s' % domain

    try:
        domaines_additionnels = params['domainesAdditionnels']
        commande_str = commande_str + ' -d ' + ' -d '.join(domaines_additionnels)
    except KeyError:
        pass

    if force is True:
        commande_str = '--force ' + commande_str

    if mode_test:
        commande_str = '--test ' + commande_str

    params_combines = dict(params_environnement)
    params_combines.update(params_secrets)
    params_combines = ['%s=%s' % item for item in params_combines.items()]

    commande_acme = "acme.sh --issue %s" % commande_str

    print('commande ACME : %s' % commande_acme)
    return commande_acme, params_combines


def trouver_acme(docker_client: DockerClient) -> Container:
    """
    Trouve un container ACME actif.
    :param docker_client:
    :return: Container acme
    """
    containers = docker_client.containers.list(filters={'label': 'acme=true'})
    if len(containers) == 0:
        raise AcmeNonDisponibleException("Container ACME introuvable")

    container = containers.pop()  # Prendre un containe ACME au hasard

    return container


class AcmeNonDisponibleException(DockerHandlerException):
    pass
