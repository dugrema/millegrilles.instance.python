# Guide MilleGrilles offline

Instructions pour installer un environnement de developpement MilleGrilles
qui fonctionne en mode offline.

## Installer Ubuntu

Pour installer un environnement de développement, choisir une version desktop de Ubuntu.
Pour une instance de MilleGrille sans développement logiciel, la version serveur est appropriée. 

Utiliser un disque ou clé USB pour installer une version desktop de Ubuntu.
Compléter l'installation de Ubuntu avant de poursuivre.

## Mettre à jour le système

export PATH_BACKUP=/media/...

Installer les packages pour upgrade a plus recent
<pre>
mkdir -p ~/work/debs
cd ~/work/debs
tar -C ~/work/debs -xf ${PATH BACKUP}/debs/ubuntu_20.04.3-desktop.amd64.*.tar

sudo dpkg -i --auto-deconfigure ~/work/debs/1-upgrade/*.deb

# Fix deps avec probleme durant upgrade (libpam)
sudo dpkg -i ~/work/debs/1-upgrade/libpam*
sudo apt install --fix-broken

sudo dpkg -i ~/work/debs/2-millegrilles/*.deb
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
sudo mkdir -p /var/lib/git
sudo chown :git /var/lib/git
sudo chmod 775 /var/lib/git
tar -C /var/lib -xf ${PATH BACKUP}/millegrilles/git/fs1_git.*.tar.gz
</pre>

Extraire packages python dans /var/lib/pip
<pre>
sudo mkdir -p /var/lib/pip
sudo chown :pip /var/lib/pip
sudo chmod 775 /var/lib/pip
tar -C /var/lib -xf ${PATH BACKUP}/millegrilles/python/millegrilles.deps.python_202401220825.tar
</pre>

Installer les images docker
<pre>
docker image load -i ${PATH BACKUP}/millegrilles/docker/millegrilles.catalogues.x86_64.202401210744.tar
docker image load -i ${PATH BACKUP}/millegrilles/docker/millegrilles.middleware.x86_64.202401210738.tar
</pre>

Installer l'environnement MilleGrille

Le repertoire /var/opt/millegrille va être préparé avec toute la configuration requise.

Faire un clone du module millegrilles.instance.python.

<pre>
mkdir git
cd git
# Aller chercher les fichiers d'installation - choisir une branch au besoin
git clone --branch master /var/lib/git/millegrilles.instance.python.git

# Aller chercher les fichiers de catalogues - choisir une branch au besoin
cd ~/git/millegrilles.instance.python
cd etc
git clone --branch master /var/lib/git/millegrilles.catalogues
git rm catalogues
mv millegrilles.catalogues catalogues
cd ..

# Parametres pour empecher pip de se connecter au reseau
export PIP_NO_INDEX=true
export PIP_FIND_LINKS=/var/lib/pip
export PIP_RETRIES=0

# Installer l'instance
./install.sh
</pre>

Demarrer l'instance.

<pre>
sudo systemctl enable mginstance
sudo systemctl start mginstance
</pre>

Configurer la nouvelle MilleGrille sous https://**NOM_HOST**

## Installer un environnement de developpement en mode offline

Compléter les étapes d'installation d'une nouvelle MilleGrille avant de procéder
a l'installation de l'environnement de développement.

Les IDE utilisés pour le développement peuvent être installés avec les snaps sous $PATH_BACKUP/snaps.

<pre>
cd $PATH_BACKUP/snaps
./install.sh

sudo chown -R $USER /var/opt/millegrilles
</pre>

**Python**

Python est le language de plusieurs applications serveur et utilitaires.

Les packages pip utilises par Python ont deja été installés sous /var/lib/pip durant
l'installation de la MilleGrille.

Installation de l'environnement de développement Python.

* IDE : PyCharm Community (snap)
* Path de développement : $HOME/PycharmProjects

Configurer les projets git sous PyCharm.

Extraire le projet de git (peut être fait dans un shell, puis menu File/Open dans PyCharm)
1. Ouvrir PyCharm à partir du menu d'applications Ubuntu.
2. Choisir Get from CVS (ou Git / Clone dans le menu si PyCharm était déjà configuré).
3. Remplir URL : /var/lib/git/`NOM PROJET`  (e.g. millegrilles.instance.python.git)
4. Choisir Trust Project
5. Si demandé, créer l'environnement virtuel avec python3.10 ou plus récent. Cliquer sur OK.

Pour installer les dépendances de chaque projet Python :

1. Ouvrir un shell
2. Aller sous $HOME/PycharmProjects/millegrilles.instance.python
3. . venv/bin/activate
5. pip install --no-index --find-links /var/lib/pip -r `PATH PROJET`/requirements.txt 

Voir le document /doc/env.dev.md sous chaque projet pour obtenir les paramètres de configuration supplémentaires.

**Rust**

Rust est le language de programmation de plusieurs applications serveur.

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

Chaque projet Rust a une dependance vers millegrilles_common_rust. Le checkout du submodule ne fonctionnera pas.
Faire un checkout local a la place. Exemple pour millegrilles_core :

<pre>
cd ~/RustroverProjects
git checkout /var/lib/git/millegrilles_core.git
cd millegrilles_core
rm -r millegrilles_common_rust
git clone /var/lib/git/millegrilles_common_rust.git
</pre>

TODO :

* Erreur dans RustRover : cannot attach stdlib sources automatically

**NodeJS**

NodeJS est requis par la partie client React des applications web.

