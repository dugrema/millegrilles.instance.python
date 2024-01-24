# Preparation d'une instance de backup offline

Pour une machine qui est connectee a internet. Idealement c'est une machine de build avec jenkins.

## Rust

rustup
cargo install cargo-local-registry


## Python

sudo apt install python3.10-venv
python3 -m venv venv_offline

. venv_offline/bin/activate
pip download -r .../requirements.txt -d offline/pip/




