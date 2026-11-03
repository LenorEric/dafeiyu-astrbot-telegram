#!/usr/bin/env bash
# Consistent Telegram deployment backup. BASE is the full repository root.
set -euo pipefail
BASE="${1:-/opt/dafeiyu}"
cd "$BASE"
mkdir -p backups
chmod 700 backups
stamp=$(date +%Y%m%d_%H%M%S)
tmp="backups/.backup_${stamp}.tmp"
final="backups/dafeiyu_backup_${stamp}.tar.gz"
stopped=0
restore() {
  code=$?
  trap - EXIT INT TERM
  rm -f "$tmp"
  if [ "$stopped" = 1 ]; then
    if ! docker compose -f deploy/compose.yaml start astrbot; then
      echo 'ERROR: failed to restore AstrBot' >&2
      exit 1
    fi
    if [ "$(docker inspect -f '{{.State.Running}}' astrbot)" != true ]; then
      echo 'ERROR: AstrBot did not restart' >&2
      exit 1
    fi
  fi
  exit "$code"
}
trap restore EXIT
trap 'exit 130' INT TERM
running=$(docker inspect -f '{{.State.Running}}' astrbot)
if [ "$running" = true ]; then
  docker compose -f deploy/compose.yaml stop astrbot
  stopped=1
fi
# A failed stop aborts before copying mutable SQLite files.
umask 077
tar -czf "$tmp" deploy/data deploy/compose.yaml deploy/Dockerfile deploy/patches deploy/telegram plugin
mv "$tmp" "$final"
# Do not remove unrelated files or follow symlinks when retaining seven archives.
python3 - <<'PY'
from pathlib import Path
for path in sorted(Path('backups').glob('dafeiyu_backup_*.tar.gz'), reverse=True)[7:]:
    if path.is_file() and not path.is_symlink(): path.unlink()
PY
