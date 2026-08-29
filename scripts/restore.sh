#!/usr/bin/env bash
#
# Restore the game database from an archive written by scripts/backup.sh.
#
# This DROPS the collections it restores: the archive becomes the truth, and a
# document created after the backup is gone. That is what a restore means, and
# it is why the script says so and asks, unless CONFIRM_RESTORE=yes is set.
#
# Usage:
#     scripts/restore.sh <archive.gz>
set -euo pipefail

CONTAINER="${MONGO_CONTAINER:-realestate-mongo}"
DATABASE="${MONGODB_DB:-realestate}"
ARCHIVE="${1:-}"

if [ -z "$ARCHIVE" ]; then
  echo "usage: scripts/restore.sh <archive.gz>" >&2
  exit 1
fi

if [ ! -f "$ARCHIVE" ]; then
  echo "error: no such archive: $ARCHIVE" >&2
  exit 1
fi

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "error: container '$CONTAINER' is not running. Start the stack first." >&2
  exit 1
fi

if [ "${CONFIRM_RESTORE:-}" != "yes" ]; then
  echo "This replaces the '$DATABASE' database with the contents of $ARCHIVE."
  echo "Anything written since that archive will be lost."
  read -r -p "Type 'restore' to continue: " answer
  [ "$answer" = "restore" ] || { echo "aborted"; exit 1; }
fi

# --drop replaces each collection rather than merging into it, so a restore is
# a restore and not a union of two states.
docker exec -i "$CONTAINER" mongorestore \
  --archive \
  --gzip \
  --drop \
  --quiet < "$ARCHIVE"

echo "restored '$DATABASE' from $ARCHIVE"
