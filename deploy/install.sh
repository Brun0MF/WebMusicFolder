#!/usr/bin/env sh
# Load the image and start WebMusicFolder. Run it next to webmusicfolder.tar.gz.
# Settings come from ./.env (created on first run); edit it and run this script again.
set -eu
cd "$(dirname "$0")"

if [ ! -f .env ]; then
    printf 'Choose a password for the web interface: '
    read -r password
    {
        echo "WMF_PASSWORD=$password"
        echo "# Folder with your music on this server (absolute path)."
        echo "WMF_MUSIC_HOST=$(pwd)/music"
        echo "PUID=$(id -u)"
        echo "PGID=$(id -g)"
        echo "TZ=UTC"
    } > .env
    chmod 600 .env
fi

docker load -i webmusicfolder.tar.gz
# Prefer the compose plugin, fall back to the standalone binary.
if docker compose version >/dev/null 2>&1; then
    docker compose up -d
else
    docker-compose up -d
fi

echo "WebMusicFolder is running on port ${WMF_PORT_HOST:-8080}. Open http://<this-server>:8080"
