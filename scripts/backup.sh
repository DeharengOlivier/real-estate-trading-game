#!/usr/bin/env bash
#
# Dump the game database to a timestamped archive.
#
# The seeded market can always be rebuilt by re-running the seed. What cannot
# is everything a player did afterwards: accounts, portfolios, holdings and
# trades. That is what this exists for.
#
# Usage:
#     scripts/backup.sh [destination-directory]     # default: ./backups
#
# The archive it writes is the input to scripts/restore.sh. A backup nobody has
# ever restored is a belief, not a backup: see the drill in the README.
set -euo pipefail

CONTAINER="${MONGO_CONTAINER:-realestate-mongo}"
DATABASE="${MONGODB_DB:-realestate}"
DESTINATION="${1:-./backups}"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "error: container '$CONTAINER' is not running. Start the stack first." >&2
  exit 1
fi

mkdir -p "$DESTINATION"
stamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive="$DESTINATION/${DATABASE}-${stamp}.archive.gz"

# --archive writes a single stream rather than a directory of BSON files, so
# the result is one file to copy and one file to hand back to mongorestore.
docker exec "$CONTAINER" mongodump \
  --db "$DATABASE" \
  --archive \
  --gzip \
  --quiet > "$archive"

size="$(wc -c < "$archive" | tr -d ' ')"
if [ "$size" -lt 1024 ]; then
  echo "error: archive is $size bytes, which is too small to be a real dump." >&2
  rm -f "$archive"
  exit 1
fi

echo "$archive"
