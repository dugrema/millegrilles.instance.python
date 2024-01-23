Pour developper avec PyCharm, copier les parametres suivants dans la section Environment Variables
de millegrilles.instance.python/millegrilles_instance/__main__.py.

Note : Utiliser le guide d'installation d'une MilleGrille pour préparer 
l'environnement initial. L'environnement de développement opère à
partir d'une MilleGrille fonctionnelle.

## Préparer le système au mode développement

1. Ouvrir un shell
2. sudo systemctl disable mginstance
3. sudo systemctl stop mginstance
4. sudo chown -R $USER /var/opt/millegrilles

## Dépendances additionnelles

Python

Installer ces projets sous Pycharm au besoin. S'assurer de rebâtir et déployer ces dépendances au besoin.

* millegrilles.messages.python

## Démarrer la version de développement de mginstance

1. Dans Pycharm, naviguer sous millegrilles.instance.python/millegrilles_instance
2. Right click sur __main__.py, choisir Run '__main__'.
3. Aller dans le menu Run / Edit Configurations.
4. Ajouter les paramètre de configuration suivants :

TODO : rendre générique
<pre>
WEB_APP_PATH=/home/mathieu/PycharmProjects/millegrilles.instance.python/dist/web
</pre>

---

Démarrer (Run) l'instance. 

## Modifications à nginx

Le `HOSTNAME` est le nom que vous avez donné au serveur. Utiliser la commande
`hostname` dans un shell pour l'obtenir au besoin. Utiliser ce hostname pour remplacer la
valeur `SERVER`. 

Note : en mode offline, remplacer `SERVER` par l'adresse IP locale (e.g. 172.17.0.1).

* nano /var/opt/millegrilles/nginx/modules/installation.proxypass
* Mettre un commentaire sur set $upstream_millegrilles (ligne 1)
* Retirer commentaire de la ligne 2, ajuster le nom du `SERVER`.
* Sauvegarder
* Sauvegarder
* Redémarrer nginx : docker service update --force nginx

Tester la page web d'installation avec : https://`HOSTNAME`/installation


---
TODO Reutiliser
* nano /var/opt/millegrilles/nginx/modules/installation.location
* Aller dans la section /millegrilles
* Mettre en commentaire le include avec millegrilles.proxypass
* Retirer # des lignes suivantes (set et proxy_pass)
* Modifier le SERVER.
