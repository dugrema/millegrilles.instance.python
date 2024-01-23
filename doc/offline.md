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
mkdir -p ~/work/debs
cd ~/work/debs
tar -xf debs/ubuntu_20.04.3-desktop.amd64.202401221124.tar

sudo dpkg -i --auto-deconfigure 1-upgrade/*.deb

# Fix deps avec probleme durant upgrade (libpam)
sudo dpkg -i 1-upgrade/libpam*
sudo apt install --fix-broken

sudo dpkg -i 2-millegrilles/*.deb
</pre>

## Configurer le compte usager

Ajouter le compte courant aux groupes docker, syslog.

<pre>
sudo addgroup git
sudo addgroup pip

sudo adduser $USERNAME git
sudo adduser $USERNAME pip
sudo adduser $USERNAME docker
sudo adduser $USERNAME syslog
</pre>

**Redémarrer** pour que tous les changements prennent effet.

## Installer une nouvelle MilleGrille en mode offline

Extraire le code source (git bare) dans /var/lib/git
<pre>
sudo mkdir /var/lib/git
sudo chown :git /var/lib/git
sudo chmod 775 /var/lib/git
tar -C /var/lib -xf millegrilles/git/fs1_git.202401220958.tar.gz
</pre>

Extraire packages python dans /var/lib/pip
<pre>
sudo mkdir /var/lib/pip
sudo chown :pip /var/lib/pip
sudo chmod 775 /var/lib/pip
tar -C /var/lib -xf millegrilles/python/millegrilles.deps.python_202401220825.tar
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
git clone /var/lib/git/millegrilles.instance.python.git

cd ~/git/millegrilles.instance.python
cd etc
git clone /var/lib/git/millegrilles.catalogues
git rm catalogues
git mv millegrilles.catalogues catalogues
cd ..

#TODO : Fix install script sous compte mginstance pour path pip
export PIP_NO_INDEX=true
export PIP_FIND_LINKS=/var/lib/pip
export PIP_RETRIES=0
./install.sh
</pre>

Terminer l'installation - ces operations devraient être mise dans un script.

<pre>
sudo cp etc/daemon.json /etc/docker
sudo cp etc/logrotate.millegrilles.conf /etc/logrotate.d
sudo cp etc/01-millegrilles.conf /etc/rsyslog.d
# Editer etc/rsyslog.conf pour activer imtcp : sudo nano /etc/rsyslog.conf
sudo systemctl restart rsyslog
sudo systemctl restart docker
sudo systemctl enable mginstance
sudo systemctl start mginstance
</pre>

Configurer la nouvelle MilleGrille sous https://**NOM_HOST**

## Installer un environnement de developpement en mode offline

Compléter les étapes d'installation d'une nouvelle MilleGrille avant de procéder
a l'installation de l'environnement de développement.

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
