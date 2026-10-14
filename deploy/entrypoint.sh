#!/bin/sh
# Démarrage du conteneur : le service tourne toujours en utilisateur « app ».
#
# Un disque persistant monté par l'hébergeur (Render : /var/data) appartient à
# root : l'utilisateur non privilégié ne pourrait pas y écrire la base SQLite.
# Lancé en root, ce script donne le dossier de données à « app », puis
# abandonne définitivement ses privilèges (su-exec) avant de lancer le serveur.
set -eu
data_dir="${PANDECTE_DATA_DIR:-/var/data}"
if [ "$(id -u)" = "0" ]; then
    mkdir -p "$data_dir"
    chown app:app "$data_dir"
    chmod 700 "$data_dir"
    exec su-exec app:app "$@"
fi
exec "$@"
