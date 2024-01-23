Pour developper avec PyCharm, copier les parametres suivants dans la section Environment Variables
de millegrilles.instance.python/millegrilles_instance/__main__.py.

TODO : rendre générique

---

WEB_APP_PATH=/home/mathieu/PycharmProjects/millegrilles.instance.python/dist/web


---

Modifications à nginx

Déterminer l'adresse IP locale (e.g. 172.17.0.1). Utiliser cette valeur
pour remplacer la configuration `SERVER` dans les étapes suivantes.

Le HOSTNAME est le nom que vous avez donné au serveur. Utiliser la commande
`hostname` dans un shell pour l'obtenir au besoin.

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
