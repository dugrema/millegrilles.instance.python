#!/bin/sh

FICHIER_ACL=/home/redis/redis.acl

# Recuperer mot de passe pour les comptes client redis
PASSWD=`cat /run/secrets/passwd.redis.txt`

# Liste des comptes clients (tous le meme mot de passe)
COMPTES="client_rust client_nodejs"

# Creer le fichier ACL avec comptes clients redis
echo "# Auto-generated ACL" > $FICHIER_ACL
for CLIENT in $COMPTES; do
    echo "user $CLIENT on +@all -DEBUG ~* >$PASSWD" >> $FICHIER_ACL
done

echo "Fichier $FICHIER_ACL genere pour comptes redis"
