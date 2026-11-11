#!/usr/bin/env bash
# Dump the spend ledger database to a file, and keep the newest 30 dumps.
#
#   scripts/backup-ledger.sh [backup directory]
#
# The directory defaults to $ARENA_BACKUP_DIR, else ~/aigameversus-backups, and
# must be outside the repository: a dump holds every match stored with the
# ledger. The ledger runs in the container $LEDGER_CONTAINER (default
# aigv-ledger), see docs/COSTS.md. Restore with
#   docker exec -i aigv-ledger pg_restore -U arena -d arena --clean < FILE
set -euo pipefail

container=${LEDGER_CONTAINER:-aigv-ledger}
dir=${1:-${ARENA_BACKUP_DIR:-$HOME/aigameversus-backups}}
keep=30

mkdir -p "$dir"
dir=$(cd "$dir" && pwd)
repo=$(cd "$(dirname "$0")/.." && pwd)
case "$dir/" in
  "$repo"/*) echo "backup-ledger: $dir is inside the repository; choose a directory outside" >&2; exit 2 ;;
esac

file="$dir/ledger-$(date -u +%Y%m%dT%H%M%SZ).dump"
docker exec "$container" pg_dump -U arena -d arena --format=custom > "$file.part"
mv "$file.part" "$file"
echo "backup-ledger: wrote $file ($(wc -c < "$file") bytes)"

ls -1 "$dir"/ledger-*.dump | sort -r | tail -n +$((keep + 1)) | while read -r old; do
  rm -- "$old"
done
