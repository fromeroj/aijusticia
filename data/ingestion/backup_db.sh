#!/bin/bash
# Backup diario de la DB de producción (162) — cron 04:00 UTC.
# pg_dump como superuser postgres (peer auth): un rol con FORCE ROW LEVEL
# SECURITY (dossiers) rompía pg_dump del rol app → dumps truncados.
# Retención local 3 días + réplica off-site SSH al storage.
DEST=/opt/aijusticia/backups
mkdir -p "$DEST"
FECHA=$(date +%Y%m%d_%H%M)
DUMP="$DEST/aijusticia_$FECHA.sql.gz"

sudo -u postgres pg_dump aijusticia | gzip > "$DUMP"

# el dump DEBE contener la tabla dossiers (el error de RLS la cortaba)
if ! gzip -t "$DUMP" 2>/dev/null || ! zgrep -q "COPY public.dossiers" "$DUMP" 2>/dev/null; then
  echo "ERROR: dump incompleto o sin dossiers — $DUMP" >&2
  rm -f "$DUMP"
  exit 1
fi

# retención local 3 días
ls -t "$DEST"/aijusticia_*.sql.gz | tail -n +4 | xargs -r rm --
echo "$(date -u +%FT%TZ) dump OK ($(du -h "$DUMP" | cut -f1))"

# réplica off-site por SSH — desatachada (9GB tarda horas; no bloquear el cron)
setsid nohup rsync -az --timeout=600 --partial \
  "$DUMP" root@148.135.106.227:/srv/backups/ \
  >> /var/log/aijusticia_offsite.log 2>&1 < /dev/null &
echo "$(date -u +%FT%TZ) off-site rsync lanzado"
