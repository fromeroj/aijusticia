#!/bin/bash
# Mantenimiento nocturno de PRODUCCIÓN (162) — 02:30 CDMX / 08:30 UTC, vía cron.
#
# Cada paso corre con TOPE DE MEMORIA y TIEMPO LÍMITE: si un paso se desborda o
# se cuelga, muere solo y la producción no se entera.
#
# Lecciones que dan forma a este archivo (nov 2026 — todo salió de fallas reales):
#  - La fase "documentos" de la limpieza cargaba de golpe un rango de tesis UNAM
#    y llegaba a 10.5GB: el kernel mató procesos con la máquina asfixiada.
#  - Los pasos "reanudar SIVEPJ/UNAM" volvían a ingerir fuentes ya completas:
#    ~4.6 millones de chunks borrados y reinsertados CADA noche, además de
#    pisar el texto ya limpio con texto crudo. NADA de re-ingestas de fuentes
#    completas: se corren a mano si la fuente cambia.
#  - Lo que corre de noche sin tope ni plazo acaba corriendo a las 11:00 UTC.
#
# Si una fuente TERMINADA recibe datos nuevos, se re-ingiere a mano y acotada:
#   systemd-run --scope -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19 \
#     timeout 120m .venv/bin/python scripts/ingestion/<ingester> ...
set -u
cd /opt/aijusticia/engine
PY=.venv/bin/python
LOG=/var/log/aijusticia_mantenimiento.log

# Tope por paso: 1.5GB de RAM, sin swap, baja prioridad.
CAP=(systemd-run --scope --quiet -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19)

run() {  # run <minutos máx> <log> <comando...>
  local mins="$1" log="$2"; shift 2
  echo "$(date -u +%FT%TZ) inicio (máx ${mins} min): $*" >> "$log"
  local rc=0
  timeout "${mins}m" "${CAP[@]}" "$@" >> "$log" 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    echo "$(date -u +%FT%TZ) ok: $*" >> "$log"
  else
    echo "$(date -u +%FT%TZ) FALLO rc=$rc: $*" >> "$log"
  fi
  return "$rc"
}

echo "$(date -u +%FT%TZ) ===== mantenimiento nocturno =====" >> "$LOG"

# 1) Limpieza del corpus. Cada noche: incremental (sólo lo actualizado en 48h).
#    Los domingos: barrido completo reanudable de toda la tabla.
if [ "$(date +%u)" = "7" ]; then
  run 360 "$LOG" $PY scripts/quality/limpieza_profunda.py --completo
else
  run 180 "$LOG" $PY scripts/quality/limpieza_profunda.py
fi

# 2) SJF del día (con watermark: segundos si no hay nada nuevo)
run 30 /var/log/aijusticia_sjf.log $PY scripts/ingestion/ingest_all.py --fuentes SJF

# 3) Número de artículo de los chunks de leyes nuevas (lo usa el localizador
#    "artículo N" de la recuperación). Incremental, segundos.
run 30 "$LOG" $PY scripts/quality/rellenar_articulo_num.py

# 4) Barrido completo de UNA VEZ sobre todas las leyes, si existe la marca.
#    Reanudable: si no alcanza a terminar, sigue la noche siguiente.
MARCA=/opt/aijusticia/.estado_limpieza/articulos_full_pendiente
if [ -e "$MARCA" ]; then
  if run 150 "$LOG" $PY scripts/quality/rellenar_articulo_num.py --completo; then
    rm -f "$MARCA"
    echo "$(date -u +%FT%TZ) barrido completo de articulo_num terminado" >> "$LOG"
  fi
fi

echo "$(date -u +%FT%TZ) ===== fin del mantenimiento =====" >> "$LOG"
