#!/bin/bash
# Backup diario de la DB de producción (162) — cron 04:00 UTC.
#
#   backup_db.sh                      dump + verificación + réplica off-site
#   backup_db.sh replicar <dump.sql.gz>  sólo réplica off-site de un dump existente
#   backup_db.sh verificar <dump.sql.gz> sólo validar un dump existente
#
# Reglas que codifica este script (cada una salió de una falla real):
#  1. pg_dump como superuser postgres: `dossiers` tiene FORCE ROW LEVEL SECURITY
#     y el rol de la app no puede volcarla (oct-nov 2026: semanas de dumps truncados).
#  2. Verificar el dump en UNA pasada (verificar()): gzip íntegro + contiene dossiers + termina
#     con "database dump complete". Un dump inválido se borra y se sale con error
#     ANTES de rotar (rotar teniendo sólo un dump inválido = quedarse sin respaldo).
#  3. Réplica off-site DESATACHADA y con reintentos: 9GB tardan de minutos a horas
#     según el enlace; nunca bloquea el cron ni muere con la sesión.
#  4. Guarda anti-solapamiento con corchetes ([r]sync): un `pgrep -f` cuyo patrón
#     aparece literal en otra línea de comandos se matchea a sí mismo (19-23 nov
#     2026: la guarda se veía a sí misma por SSH y 5 días no se replicó nada).
#  5. Nunca llenar el storage: sin margen suficiente no se lanza y se avisa.
set -u

DEST=/opt/aijusticia/backups
STORAGE=root@148.135.106.227
STORAGE_DIR=/srv/backups
MIN_LIBRE_MB=20000            # un dump pesa ~9.7GB; debajo de esto no se lanza
LOG_OFFSITE=/var/log/aijusticia_offsite.log

log() { echo "$(date -u +%FT%TZ) $*"; }

verificar() {  # verificar <dump.sql.gz> → 0 sólo si es un dump completo y sano
  local dump="$1" rc
  # Una pasada y TRES condiciones, las tres obligatorias:
  #   gzip íntegro (gzip -cd falla si falta el trailer o hay corrupción),
  #   trae dossiers (la tabla que el RLS truncaba),
  #   cierra como cierra pg_dump.
  # pipefail es indispensable: gzip -cd entrega todo el contenido y sólo falla
  # al final; mirando sólo el estado de awk, un gzip sin trailer pasaba.
  #
  # El cierre se valida contra el pie REAL de pg_dump (visto con od, no supuesto):
  #     --\n-- PostgreSQL database dump complete\n--\n\n\unrestrict <token>\n\n
  # El "\unrestrict <token>" existe desde los minor de ago-2025 (16.10+) y es
  # la última línea. Una versión anterior de este chequeo exigía que la última
  # línea fuera la marca de cierre y rechazaba todos los dumps buenos.
  set -o pipefail
  LC_ALL=C gzip -cd "$dump" 2>/dev/null | awk '
      /^COPY public\.dossiers \(/ { d = 1 }
      /^-- PostgreSQL database dump complete/ { c = 1; next }
      c == 1 {
          if ($0 ~ /^[ \t]*$/ || $0 ~ /^--[ \t]*$/) next
          if ($0 ~ /^\\unrestrict [A-Za-z0-9+\/=_-]+$/ && !u) { u = 1; next }
          c = 2
      }
      END { exit !(d && c == 1) }'
  rc=$?
  set +o pipefail
  return "$rc"
}

replicar() {  # replicar <dump>
  local dump="$1" nombre; nombre=$(basename "$dump")
  # ¿hay una réplica en vuelo? El patrón lleva corchetes para que el pgrep no
  # encuentre su propio texto ni el de este script.
  if pgrep -f '[r]sync .*aijusticia_[0-9_]+\.sql\.gz .*148\.135\.106\.227:/srv/backups' > /dev/null; then
    log "réplica previa aún en vuelo — no lanzo otra ($nombre)"
    return 0
  fi
  local libre
  libre=$(ssh -o ConnectTimeout=20 -o BatchMode=yes "$STORAGE" \
            "df -Pm $STORAGE_DIR | awk 'NR==2{print \$4}'" 2>/dev/null)
  if ! [[ "$libre" =~ ^[0-9]+$ ]]; then
    log "AVISO: el storage no respondió al consultar espacio — no se lanzó la réplica de $nombre" >&2
    return 1
  fi
  if [ "$libre" -lt "$MIN_LIBRE_MB" ]; then
    log "AVISO: storage con ${libre}MB libres (<${MIN_LIBRE_MB}MB) — no se lanzó la réplica de $nombre. Definir retención en /srv/backups." >&2
    return 1
  fi
  setsid nohup bash -c '
    f="$1"; dst="$2"; dir="$3"
    start_epoch=$(date +%s); max_seg=21600
    for i in 1 2 3 4 5 6; do
      if rsync -a --partial --append-verify --timeout=600 -e "ssh -o ConnectTimeout=30 -o ServerAliveInterval=30 -o ServerAliveCountMax=20" "$f" "$dst:$dir/"; then
        echo "$(date -u +%FT%TZ) off-site OK $(basename "$f") (intento $i)"; exit 0
      fi
      rc=$?
      echo "$(date -u +%FT%TZ) off-site reintento $i rc=$rc $(basename "$f")"
      if [ $(( $(date +%s) - start_epoch )) -ge $max_seg ]; then
        echo "$(date -u +%FT%TZ) off-site ABANDON (6h limit) $(basename "$f")"
        break
      fi
      sleep 120
    done
    echo "$(date -u +%FT%TZ) off-site FALLO definitivo $(basename "$f")"
  ' _ "$dump" "$STORAGE" "$STORAGE_DIR" >> "$LOG_OFFSITE" 2>&1 < /dev/null &
  log "réplica off-site lanzada (desatachada): $nombre"
}

case "${1:-}" in
  verificar)   # sólo validar un dump existente (pruebas / diagnóstico)
    [ -n "${2:-}" ] && [ -f "${2:-}" ] || { echo "uso: $0 verificar <dump.sql.gz>" >&2; exit 2; }
    verificar "$2"; exit $? ;;
  replicar)    # sólo réplica off-site de un dump existente
    [ -n "${2:-}" ] && [ -f "${2:-}" ] || { echo "uso: $0 replicar <dump.sql.gz>" >&2; exit 2; }
    replicar "$2"; exit $? ;;
esac

mkdir -p "$DEST"
FECHA=$(date +%Y%m%d_%H%M)
DUMP="$DEST/aijusticia_$FECHA.sql.gz"

sudo -u postgres pg_dump aijusticia | gzip > "$DUMP"
RC=("${PIPESTATUS[@]}")
if [ "${RC[0]}" -ne 0 ] || [ "${RC[1]}" -ne 0 ]; then
  log "ERROR: pg_dump/gzip falló (rc=${RC[*]}) — se descarta $(basename "$DUMP")" >&2
  rm -f "$DUMP"
  exit 1
fi

if ! verificar "$DUMP"; then
  log "ERROR: dump inválido (incompleto, corrupto o sin dossiers) — se descarta $(basename "$DUMP")" >&2
  rm -f "$DUMP"
  exit 1
fi

# retención local: 3 dumps (sólo se rota habiendo un dump válido nuevo)
ls -t "$DEST"/aijusticia_*.sql.gz 2>/dev/null | tail -n +4 | xargs -r rm --
log "dump OK $(basename "$DUMP") ($(du -h "$DUMP" | cut -f1))"

replicar "$DUMP"
