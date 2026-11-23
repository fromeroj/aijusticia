#!/bin/bash
# Backup diario de la DB — 04:00 UTC / 22:00 CDMX, vía cron.
# Con tope de memoria y plazo. La réplica off-site la lanza backup_db.sh
# desatachada y sigue corriendo cuando este wrapper termina.
set -u
cd /opt/aijusticia/engine
LOG=/var/log/aijusticia_backup.log
echo "$(date -u +%FT%TZ) inicio backup" >> "$LOG"
if timeout 150m systemd-run --scope --quiet -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19 \
     bash scripts/ingestion/backup_db.sh >> "$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) ok: backup" >> "$LOG"
else
  echo "$(date -u +%FT%TZ) FALLO rc=$?: backup" >> "$LOG"
fi
