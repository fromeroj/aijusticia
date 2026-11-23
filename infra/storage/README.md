# Scripts que viven en el storage (`tlamatini`, 148.135.106.227)

Copias exactas de lo instalado en el servidor, versionadas para que el repo
sea la verdad (no hay despliegue automático a este server: se copian a mano).

| Archivo del repo | Destino en el server | Qué hace |
|---|---|---|
| `backups_retention.sh` | `/usr/local/bin/backups_retention.sh` | conserva los 10 dumps completos más recientes de `/srv/backups` |
| `cron.d-backups-retention` | `/etc/cron.d/backups-retention` | la corre a diario a las 06:30 UTC |

Decisión del dueño (23-nov-2026): **10 dumps basta** (el script se instaló
con 7 y se subió a 10 ese mismo día).

Cómo decide el script: ordena `aijusticia_*.sql.gz` por fecha, conserva los
primerios `KEEP` y borra el resto, sin tocar los modificados en las últimas
2 horas (pueden ser una réplica en curso). Log: `/var/log/backups_retention.log`.

Límites conocidos: no verifica que los dumps que conserva estén completos, y
una réplica fallida cuenta como uno de los N hasta que llegue el siguiente.
Lo cubre el chequeo "réplica off-site" de `infra/salud.py`.

Para probar cambios en este script, NO ejecutarlo contra el servidor con
variables de entorno: ignora `DIR` y `LOG` (fija `/srv/backups`). Copiarlo a un
directorio temporal, editar ahí las rutas y recién probar.
