#!/bin/sh

sudo setcap 'cap_net_bind_service=+ep' ../venv/usr/bin/python3.9
