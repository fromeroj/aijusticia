#!/bin/bash
# DOF diario — 11:30 CDMX / 17:30 UTC, vía cron. Ingesta las notas de ayer y hoy.
# Con tope de memoria y plazo (mismo mecanismo que mantenimiento_nocturno.sh).
# Ojo: el DOF no publica en puentes oficiales; "0 nuevos" no es un error.
set -u
cd /opt/aijusticia/engine
LOG=/var/log/aijusticia_dof.log
echo "$(date -u +%FT%TZ) inicio DOF diario" >> "$LOG"
if timeout 60m systemd-run --scope --quiet -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19 \
     .venv/bin/python scripts/ingestion/ingest_all.py --fuentes DOF >> "$LOG" 2>&1; then
  echo "$(date -u +%FT%TZ) ok: DOF diario" >> "$LOG"
else
  echo "$(date -u +%FT%TZ) FALLO rc=$?: DOF diario" >> "$LOG"
fi
