#!/bin/bash
# Backup diario de la DB de producción (162) — corre por cron a las 04:00 UTC.
# Retiene 14 días. Salud: infra/salud.py revisa la edad del último dump.
set -euo pipefail
DEST=/opt/aijusticia/backups
mkdir -p "$DEST"
FECHA=$(date +%Y%m%d_%H%M)
PGPASSWORD=$(grep -E '^PG_PASSWORD=' /opt/aijusticia/engine/.env | cut -d= -f2-)

docker exec -e PGPASSWORD="$PGPASSWORD" $(docker ps -qf name=postgres | head -1) \
  true 2>/dev/null && CONTENEDOR=$(docker ps -qf name=postgres | head -1)

if [ -z "${CONTENEDOR:-}" ]; then
  # postgres corre en el host, no en docker
  PGPASSWORD="$PGPASSWORD" pg_dump -h 127.0.0.1 -U aijusticia -d aijusticia \
    | gzip > "$DEST/aijusticia_$FECHA.sql.gz"
else
  echo "ERROR: postgres detectado en docker $CONTENEDOR — ajustar backup_db.sh" >&2
  exit 1
fi

# copia off-site al storage server (148.135.106.227) — best-effort
if mountpoint -q /mnt/backups_offsite; then
  cp -f "$DEST/aijusticia_$FECHA.sql.gz" /mnt/backups_offsite/ || echo "aviso: copia off-site falló" >&2
fi

# retención 14 días
ls -t "$DEST"/aijusticia_*.sql.gz | tail -n +15 | xargs -r rm --
echo "$(date -u +%FT%TZ) backup aijusticia_$FECHA.sql.gz ($(du -h $DEST/aijusticia_$FECHA.sql.gz | cut -f1))"
