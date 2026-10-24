#!/bin/sh
# Runs as root only long enough to prepare /data, then drops to PUID:PGID.
set -eu

PUID="${PUID:-0}"
PGID="${PGID:-0}"
DATA="${WMF_DATA_DIR:-/data}"

if [ "$(id -u)" = "0" ]; then
    mkdir -p "$DATA"
    chown "$PUID:$PGID" "$DATA"
fi

# No password given (import and run on a NAS): create one on first start and keep it
# in the data folder, so it survives restarts and can be read from the container logs.
if [ -z "${WMF_PASSWORD:-}" ]; then
    PW_FILE="$DATA/initial_password.txt"
    if [ ! -s "$PW_FILE" ]; then
        (umask 077 && head -c 24 /dev/urandom | base64 | tr -d '/+=\n' | head -c 16 > "$PW_FILE")
        chown "$PUID:$PGID" "$PW_FILE" 2>/dev/null || true
    fi
    WMF_PASSWORD="$(cat "$PW_FILE")"
    export WMF_PASSWORD
    echo "=================================================="
    echo "WMF_PASSWORD was not set. Login password: $WMF_PASSWORD"
    echo "(stored in $PW_FILE; set WMF_PASSWORD to choose your own)"
    echo "=================================================="
fi

if [ "$(id -u)" = "0" ]; then
    exec setpriv --reuid="$PUID" --regid="$PGID" --clear-groups "$@"
fi

exec "$@"
