# MilleGrilles instance node manager

This project contains scripts, configuration and a python module that handles a MilleGrilles node.

## Code

The python project is under `millegrilles_instance`.

## Scripts

The main installation script is `install_v2.sh`. Other scripts are available under `bin/`. 

Configuration goes under `etc/`.

A patched version of os_crypto is in `lib/`, it contains a patch regarding the openssl version check.

## Project setup

The project has a few system dependencies that need to be set-up with sudo once per system using script `bin/setup_system.sh`.

A millegrille instance can be installed using `install_v2.sh`. The script has parameters that allow naming an instance and providing a custom root folder.


