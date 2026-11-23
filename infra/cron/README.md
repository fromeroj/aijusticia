# Crons de producción (162)

Los tres wrappers siguen la misma regla: **cada paso corre con tope de memoria
(1.5GB, sin swap), plazo máximo y baja prioridad**. Si un paso se desborda o se
cuelga muere solo; la producción no se entera. (Lección del 10-23 nov 2026.)

| UTC | CDMX | Script en 162 | Qué hace |
|---|---|---|---|
| 04:00 | 22:00 | `/opt/aijusticia/backup_cron.sh` → `backup_db.sh` | pg_dump verificado + retención local de 3 dumps + réplica off-site desatachada al storage |
| 08:30 | 02:30 | `/opt/aijusticia/mantenimiento_nocturno.sh` | limpieza incremental del corpus (barrido completo los domingos) + SJF del día |
| 17:30 | 11:30 | `/opt/aijusticia/dof_diario.sh` | ingesta del DOF de ayer y hoy |

Las fuentes de este directorio se copian tal cual a `/opt/aijusticia/`.
Los scripts que invocan viven en `data/` (en el server: `/opt/aijusticia/data`,
con `engine/scripts` como symlink de compatibilidad).

## Lo que estos crons NO hacen (a propósito)

- **No re-ingieren fuentes terminadas** (SIVEPJ, UNAM-Tesis, OJ). Re-ingerir una
  fuente completa con los ingesters actuales reescribe todos sus chunks y pisa
  texto ya limpio con texto crudo. Si una fuente terminada recibe datos nuevos,
  se corre a mano y acotada:
  ```bash
  cd /opt/aijusticia/engine
  systemd-run --scope -p MemoryMax=1500M -p MemorySwapMax=0 nice -n 19 \
    timeout 120m .venv/bin/python scripts/ingestion/<ingester> ...
  ```
- **No cosechan gacetas estatales**: el scheduler de fuentes
  (`aijusticia-ingest.timer` + `python -m ai_justicia.ingestion.scheduler`)
  existía en el server viejo (182) y nunca se instaló en 162. Ver
  `docs/components/data-consumer.md`.

## Verificación

`make salud` (o `python3 infra/salud.py`): frescura del DOF, edad del backup
local y del off-site, OOM kills recientes, disco y carga.
