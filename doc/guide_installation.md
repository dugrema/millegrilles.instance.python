# Guide d'installation de MilleGrilles

Étapes pour l'installation normale avec accès à internet: 

1. git clone https://github.com/dugrema/millegrilles.instance.python.git
2. cd millegrilles.instance.python
3. ./install.sh
4. sudo systemctl enable mginstance
5. sudo systemctl start mginstance
6. Ouvrir le navigateur vers : https://HOSTNAME  (remplacer `HOSTNAME` par le nom de votre serveur)

Voir le guide d'installation offline pour plus d'informations.

## Créer une nouvelle MilleGrille

TODO

## Créer le compte propriétaire

TODO

## Compléter l'installation du système avec CoudDoeil

Une MilleGrille fonctionnelle a besoin au minimum des éléments suivants. Ils ne
sont pas installés automatiquement parce qu'il y a plusieurs topologie disponibles
pour augmenter la sécurité. 

La topologie la plus simple est celle avec une seule instance (3.protege). 
L'instance 3.protege est requise et il peut y en avoir 1 seule par MilleGrille.

Aller dans CoupDoeil et installer les applications suivantes sous l'instance 3.protege.

Cliquez sur le bouton Configurer, puis allez sous Applications. Choisir chaque application
et cliquez sur Installer.

* maitredescles
* fichiers
* backup

Votre MilleGrille est maintenant complète. 

# Première application - Collections

Pour installer l'application collections, il faut aussi installer ses dépendances.

Installer les applications suivantes en ordre :

* grosfichiers_backend
* media_1cpu  (ou media pour utiliser 4 CPU)
* stream
* collections

Retournez sur le portail. L'application collections devrait faire partie de la liste.
