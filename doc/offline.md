# Guide MilleGrilles offline

Instructions pour installer un environnement de developpement MilleGrilles
qui fonctionne en mode offline.

## Installer Ubuntu

Pour installer un environnement de développement, choisir une version desktop de Ubuntu.
Pour une instance de MilleGrille sans développement logiciel, la version serveur est appropriée. 

Utiliser un disque ou clé USB pour installer une version desktop de Ubuntu.
Compléter l'installation de Ubuntu avant de poursuivre.

## Mettre à jour le système

Installer les packages pour upgrade a plus recent
<pre>
cd debs/1-upgrade
dpkg -i libpam-modules_1.4.0-11ubuntu2.4_amd64.deb libreoffice-core_1%3a7.3.7-0ubuntu0.22.04.4_amd64.deb
sudo dpkg -i *.deb
sudo apt install --fix-broken
cd debs/2-millegrilles
sudo dpkg -i *.deb
</pre>

## Configurer le compte usager

Ajouter le compte courant aux groupes docker, syslog.

<pre>
sudo adduser $USERNAME docker
sudo adduser $USERNAME syslog
</pre>

**Redémarrer** pour que tous les changements prennent effet.

## Installer une nouvelle MilleGrille en mode offline

Extraire le code source dans ~/gitbare
<pre>
cd ~
tar -xf millegrilles/git/fs1_git.202401220958.tar.gz
mv git gitbare
</pre>

Installer les images docker
<pre>
docker image load -i millegrilles/docker/millegrilles.catalogues.x86_64.202401210744.tar
docker image load -i millegrilles/docker/millegrilles.middleware.x86_64.202401210738.tar
</pre>

Installer l'environnement MilleGrille

Le repertoire /var/opt/millegrille va être préparé avec toute la configuration requise.

Faire un clone du module millegrilles.instance.python.

<pre>
mkdir git
cd git
git clone ~/gitbare/millegrilles.instance.python.git

cd ~/git/millegrilles.instance.python
cd etc
git clone ~/gitbare/millegrilles.catalogues
git rm catalogues
git mv millegrilles.catalogues catalogues


</pre>

## Installer un environnement de developpement en mode offline

Compléter les étapes d'installation d'une nouvelle MilleGrille avant de procéder
a l'installation de l'environnement de développement.

Extraire packages python
<pre>
mkdir ~/pip
cd ~/pip
tar -xf millegrilles/python/millegrilles.deps.python_202401220825.tar
</pre>

Copier rust et packages
<pre>
mkdir ~/rust/local-registry
cd ~/rust/local-registry
tar -xf millegrilles/rust/rust-registry.202401211840.tar

mkdir -p ~/work/rust
cd ~/work/rust
tar -xf millegrilles/rust/rust-1.75.0-x86_64-unknown-linux-gnu.tar.gz
cd rust-1.75.0-x86_64-unknown-linux-gnu
sudo ./install.sh

cd ~
mkdir .cargo
# Copier config avec info local-registry
</pre>

Contenu .cargo/config
<pre>
    [source.crates-io]
    registry = 'sparse+https://index.crates.io/'
    replace-with = 'local-registry'

    [source.local-registry]
    local-registry = '/home/.../rust/local-registry'
</pre>
