# Backup / restore scripts

This directory contains scripts that can be used to backup and restore the mongo database. Make sure you ran the `. bin/activate.sh` command to load the environment before running.

## Restore Maitre des cles

To restore the maitre des cles, especially if you're moving it to a new instance_id, use these commands

1. Stop maitre des cles
2. Run the mongo shell (bin/mongo_shell.sh)
   1. db['MaitreDesCles/configuration'].drop()
   2. db['MaitreDesCles/cles'].drop()
   3. db['MaitreDesCles/CA/cles'].updateMany({}, { $set: { non_dechiffrable: true } })
3. Restart maitre des cles
4. in CoupD'Oeil, under Key Management, run the process. You need the master key for this.
