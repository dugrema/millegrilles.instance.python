#!/bin/env bash
source /var/opt/millegrilles/venv/bin/activate
# export PYTHONPATH="${PYTHONPATH}:/var/opt/millegrilles/python"
python3 -m millegrilles_instance $@
