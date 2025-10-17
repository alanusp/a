#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
mkdir -p "$ROOT/vendor/images"
IMAGES=$(docker compose -f "$ROOT/docker-compose.yml" config --images | sort -u)
for image in $IMAGES; do
  SAFE_NAME=$(echo "$image" | tr '/:' '__')
  TARGET="$ROOT/vendor/images/${SAFE_NAME}.tar"
  docker pull "$image" >/dev/null 2>&1 || true
  docker save "$image" -o "$TARGET"
  echo "saved $image to $TARGET"
done

