#!/bin/sh

PYTHON_BIN=/usr/bin/python3.10

sudo setcap 'cap_net_bind_service=+ep' $PYTHON_BIN
