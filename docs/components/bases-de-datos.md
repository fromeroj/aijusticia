# Componente: Bases de datos

**Dos bases, dos roles.** No se mezclan.

## DB PRODUCCIÓN — local en 162.35.113.166
- Postgres 16, `127.0.0.1:5432`, db/user `aijusticia` (password en `/opt/aijusticia/engine/.env`).
- 473,848 docs · 14.1M chunks · ~3.9B tokens. La única que sirve al chat.
- Schema: `documentos` (con `titulo_search` GENERATED), `documentos_chunks` (**sin columna `id`**; `texto_search` GENERATED; `articulo_num` backfilled), `actores`, `bufetes`, `dossiers`, `citas`, `source_health`, `harvest_scripts`, `ingestion_watermarks`, `pending_jobs`, …
- Backup: `backup_db.sh` diario 04:00 (cron en 162).
- ⚠️ Difiere del schema de 182 (ver abajo) — `limpieza_profunda.py` detecta y adapta.

## DB ARCHIVO — 182.255.84.124: ❌ MUERTA (suspendida ~15-oct-2026)
- Perdió ~1,184 leyes OOXML recuperadas que se habían subido ahí (los archivos
  fuente sobreviven en 66; re-recovery en curso hacia 162).
- **Una sola DB canónica desde el 29-oct**: producción (162). El harvest de 66
  escribe DIRECTO a 162 (postgres expuesto solo a 66.154.100.25 con scram;
  password rotada). El .env de la Mac debe usar túnel SSH a 162 (pendiente).

## Storage server — 161.129.70.21 (⚠️ CAÍDO)
- Servía `/srv/corpus` por NFS a 162 (`/opt/aijusticia/corpus_downloads`, mount `hard`).
- Caído desde ~agosto 2026: provocó 20 procesos D-state (zombis del harvest lexmx) y la muerte silenciosa del DOF backfill.
- 14-oct: desmontado con `umount -f -l`, fstab limpiado, `corpus_downloads` recreado como disco local de 162 (161GB libres — suficiente).
- Cuando reviva: montar como storage de Nextcloud/Office (con opción `soft`, no `hard`).

## Reglas
- El chat NUNCA escribe al archivo; el harvest escribe SOLO vía batch_upsert.
- `corpus/status` (engine, cache 5 min) es la vista pública del estado.
