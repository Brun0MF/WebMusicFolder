#!/usr/bin/env bash
# Build the image and write a ready to copy bundle to dist/:
#   webmusicfolder.tar     the image, for NAS "import image" screens
#   webmusicfolder.tar.gz  the same, compressed (docker load)
#   docker-compose.yml       runs the loaded image
#   install.sh               loads the image and starts the container
# Optional: PLATFORM=linux/arm64 scripts/export_image.sh (needs docker buildx).
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="webmusicfolder:latest"
OUT="dist"
mkdir -p "$OUT"

if [ -n "${PLATFORM:-}" ]; then
    docker buildx build --platform "$PLATFORM" --load -t "$IMAGE" .
else
    docker build -t "$IMAGE" .
fi

# Plain .tar for NAS web UIs (import image), .tar.gz for docker load on a shell.
docker save -o "$OUT/webmusicfolder.tar" "$IMAGE"
gzip -kf "$OUT/webmusicfolder.tar"
chmod 0644 "$OUT"/webmusicfolder.tar "$OUT"/webmusicfolder.tar.gz
cp deploy/docker-compose.yml deploy/install.sh deploy/NAS_GUIDE.md "$OUT/"
chmod 0755 "$OUT/install.sh"

echo
echo "Image ready: $OUT/webmusicfolder.tar ($(du -h "$OUT/webmusicfolder.tar" | cut -f1))."
echo "NAS web UI: import that .tar as an image, see deploy/NAS_GUIDE.md."
echo "With a shell: copy $OUT/ to the server and run ./install.sh"
