# Componente: Infra / Operación

## Servers (23-nov-2026)
| Server | Rol | Recursos / estado |
|---|---|---|
| **162.35.113.166** | PRODUCCIÓN: web + API + **postgres local (canónico)** + office (Nextcloud :8080) + crons | 197GB (98 libres), 11GB RAM, 3 vCPU |
| 192.227.167.147 | RackNerd: Caddy TLS (contenedor `caddy`) | 9GB (80%), 729MB RAM, swap casi lleno — no meter nada |
| 66.154.100.25 | auxiliar: cosechas pesadas → escriben directo a 162 | 30GB (7 libres), 2GB RAM |
| **148.135.106.227** | STORAGE `tlamatini`: `/srv/backups` (por rsync/SSH), `/srv/archive`, `/srv/corpus` | 197GB (55% usado; retención de 10 dumps), 1 vCPU, 933MB |
| 182.255.84.124 | server viejo (`aijusticia.mx`): congelado, contenido útil ya importado | 59GB (3.5 libres) |
| 161.129.70.21 | storage viejo | caído desde agosto |
| Mac Studio | cosechas con navegador, entrenamiento, `make bateria` | — |

## Crons en 162 — ver `infra/cron/README.md`
| UTC | Wrapper | Qué hace |
|---|---|---|
| 04:00 | `backup_cron.sh` → `backup_db.sh` | dump verificado + réplica off-site |
| 08:30 | `mantenimiento_nocturno.sh` | limpieza incremental + SJF |
| 17:30 | `dof_diario.sh` | DOF de ayer y hoy |

Todo paso corre bajo `systemd-run --scope -p MemoryMax=1500M -p MemorySwapMax=0`
con `timeout` y nice 19: si se desborda o se cuelga, muere solo.

## Monitoreo
- **CI monitor cada 30 min** (`.github/workflows/ci.yml`): `infra/salud.py` completo,
  por HTTP y por SSH — web, engine+LLM, corpus, frescura DOF, office, servicios,
  **kills por OOM (30h)**, resultado del mantenimiento nocturno, disco y carga de
  162, dump local, **réplica off-site**, disco del storage.
- **Alerta una vez por conjunto de fallos** (`infra/salud_ci.py`, memoria en la
  cache de Actions): repite a las 12h si persiste y de inmediato si cambia el
  conjunto. Un fallo que dura horas no genera decenas de correos.
- El gate del deploy usa la misma memoria: no vuelve a fallar por un fallo ya avisado.
- A mano: `make salud` (integral) · `make salud-full` (+ smoke del chat).

## Trampas conocidas (cada una costó una falla real)
- **`pgrep -f` / `pkill -f` sin corchetes**: el patrón aparece en la línea de
  comandos del propio shell (o del shell remoto por SSH) y se matchea a sí mismo.
  Falso positivo en guardas ("hay una réplica en vuelo" → 5 días sin replicar),
  falso "ok" en chequeos, y sesiones SSH suicidadándose. Siempre `[r]sync`.
- **`fetchall()` de textos largos**: la fase documentos de la limpieza cargaba un
  rango de tesis de golpe → 10.5GB → el kernel mató procesos con la máquina
  asfixiada (10, 22 y 23-nov, siempre ~11:00 UTC). Un documento a la vez.
- **Re-ingerir fuentes completas**: los ingesters deduplican sólo en memoria;
  cada corrida reescribe todos los chunks (~4.6M por noche) y pisa texto limpio.
- **NFS `hard`**: si el storage muere, todo proceso que toque el mount queda en
  D-state. `pkill` no los mata. Montar `soft` y no colgar de él datos de una app.
- **`comm` sobre archivos ordenados en máquinas distintas**: la collation cambia y
  el resultado es basura (211K falsos "sólo en 182"). Comparar con conjuntos.
- **`COPY … TO STDOUT` (formato texto) duplica las barras**: rompe un JSONL.
  Usar `WITH (FORMAT csv, QUOTE E'\x01', DELIMITER E'\x02')`.
- **`zcat` de macOS no es el de Linux**: las pruebas de un script de servidor se
  corren en el servidor (o contra su código desplegado), no contra una copia.
- **`rsync --partial` deja el archivo incompleto con el nombre final**: el nombre
  no prueba nada; comparar tamaño. Un dump de 9GB tarda de minutos a horas.
- **Discos sin vigilancia**: 182 murió con el disco al 100%; el storage va al 80%.
- `rsync` de macOS no soporta `--info=progress2`.
- No reescribir un script de bash mientras se ejecuta (lo lee por offset).

## Pendientes
- La retención del storage (10 dumps, `infra/storage/`) no verifica que lo que
  conserva esté completo; lo cubre el chequeo "réplica off-site" de `salud.py`.
- Caddy/RackNerd al 80% de disco y con swap casi lleno.
- Túnel autossh viejo de la Mac (`com.aijusticia.tunnel` → 66.154): vestigial.
- NFS sin cifrar entre 162 y el storage (propuesta: WireGuard).
- Aprobar deploys a mano (required reviewers en el environment `production`).
