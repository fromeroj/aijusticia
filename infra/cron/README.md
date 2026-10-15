# Crons de producción (162)

| Hora (CDMX) | Script en 162 | Fuente en repo | Qué hace |
|---|---|---|---|
| 02:30 | `/opt/aijusticia/mantenimiento_nocturno.sh` | `infra/cron/mantenimiento_nocturno.sh` | limpieza profunda + re-ingestas (nice 19) |
| 04:00 | `/opt/aijusticia/backup_cron.sh` | `infra/cron/backup_cron.sh` | pg_dump diario, retención 14 días |
| 11:30 | `/opt/aijusticia/dof_diario.sh` | `infra/cron/dof_diario.sh` | ingesta DOF del día |

Instalar: copiar los 3 a `/opt/aijusticia/` y el crontab de
`docs/components/infra.md`. Verificación: `make salud` (revisa frescura DOF,
edad del backup y carga).
