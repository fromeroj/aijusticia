# Componente: Infra / Operación

## Servers (14-oct)
| Server | Rol | Recursos |
|---|---|---|
| **162.35.113.166** | PRODUCCIÓN: web+API+DB local+office (en migración)+crons | 235GB (161 libres), 11GB RAM, 3 vCPU |
| 66.154.100.25 | auxiliar: harvest OJ→182, limpieza archivo | 30GB (7.6 libres), 2GB RAM |
| 192.227.167.147 | RackNerd: Caddy TLS (contenedor `caddy`) | 9GB (**97% lleno** — no meter nada) |
| 182.255.84.124 | DB archivo/entrenamiento | 59GB (7.3 libres) |
| 161.129.70.21 | storage NFS (`/srv/corpus`) | ⚠️ **CAÍDO** desde ~ago-2026 |
| Mac Studio | cosechas con navegador, entrenamiento, piloto Nextcloud (en salida) | — |

## Crons en 162 (14-oct)
- `11:30 CDMX` — `dof_diario.sh` (ingesta DOF del día)
- `02:30 CDMX` — `mantenimiento_nocturno.sh` (limpieza + re-ingestas, nice 19)
- `04:00` — `backup_db.sh` (dump de la DB)
- `06:30` — `cron_diferencial.sh` ⚠️ legacy, duplicado del DOF diario — limpiar
- `@reboot` firstbootkvm (del proveedor — no tocar)

## Trampas conocidas
- **pkill por patrón**: el cmdline del ssh remoto contiene el patrón → suicida la sesión. Usar script subido (`/tmp/x.sh`) o brackets SIEMPRE, y nunca mezclar pkill + heredoc con el mismo texto.
- **NFS `hard`**: si el storage server muere, todo proceso que toque el mount queda en D-state para siempre (nos costó 20 procesos y un backfill). Si se remonta: opción `soft`.
- **rsync de macOS**: sin `--info=progress2` (rsync 2.6.9).
- Pkill no mata procesos D-state — hay que resolver el IO primero.

## Monitoreo
Pendiente: UptimeRobot (o similar) sobre `https://aijusticia.mx/health`.
Checklist manual en `DEPLOYMENT.md` §Verificar salud.
