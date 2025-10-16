#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
for archive in "$ROOT"/vendor/images/*.tar; do
  [ -e "$archive" ] || continue
  docker load -i "$archive"
  echo "loaded $archive"
done

