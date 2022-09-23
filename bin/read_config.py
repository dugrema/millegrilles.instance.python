#!/bin/env python3
import json


def load_config():
    with(open('/var/opt/millegrilles/configuration/config.json', 'r')) as fichier:
        return json.load(fichier)


def main():
    config = load_config()
    for (key, value) in config.items():
        if isinstance(value, str):
            key = key.upper()
            print("%s=%s" % (key, value))
    exit(0)


if __name__ == '__main__':
    main()
