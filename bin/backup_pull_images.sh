#!/bin/bash

PATH_LISTING=/var/lib/jenkins/workspace/millegrilles.catalogues@2/output
FILES=(`ls $PATH_LISTING`)

ROOT_WORK=~/work

echo $FILES

rm $ROOT_WORK/images.txt || true

# Combiner toutes les images des fichiers
for FILE in "${FILES[@]}"; do
   echo Listing fichier $FILE
   IMGS=(`cat $PATH_LISTING/$FILE`)
   for IMAGE in "${IMGS[@]}"; do
      echo "$IMAGE" >> $ROOT_WORK/images.txt
   done
done

# Retirer les doublons
sort -u $ROOT_WORK/images.txt -o $ROOT_WORK/images_uniques.txt

IMAGES=(`cat $ROOT_WORK/images_uniques.txt`)

for IMG in "${IMAGES[@]}"; do
  echo "docker pull $IMG"
  docker pull $IMG
done
