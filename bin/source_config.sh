# Utilitaire pour lire configuration vers bash
# Exemple pour un script :
#   VARS=`~/PycharmProjects/millegrilles.instance.python/bin/read_config.py`
#   source ~/PycharmProjects/millegrilles.instance.python/bin/source_config.sh

if [ -z "$VARS" ]; then
  echo "Passer VARS"
  exit 1
fi

while read -r line; do
  VARNAME=`echo "$line" | cut -d"=" -f1`
  VARVALUE=`echo "$line" | cut -d"=" -f2`
  declare $VARNAME=$VARVALUE
done <<< "$VARS"
