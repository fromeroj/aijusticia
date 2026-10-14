# Componente: Bases de datos

**Dos bases, dos roles.** No se mezclan.

## DB PRODUCCIÓN — local en 162.35.113.166
- Postgres 16, `127.0.0.1:5432`, db/user `aijusticia` (password en `/opt/aijusticia/engine/.env`).
- 473,848 docs · 14.1M chunks · ~3.9B tokens. La única que sirve al chat.
- Schema: `documentos` (con `titulo_search` GENERATED), `documentos_chunks` (**sin columna `id`**; `texto_search` GENERATED; `articulo_num` backfilled), `actores`, `bufetes`, `dossiers`, `citas`, `source_health`, `harvest_scripts`, `ingestion_watermarks`, `pending_jobs`, …
- Backup: `backup_db.sh` diario 04:00 (cron en 162).
- ⚠️ Difiere del schema de 182 (ver abajo) — `limpieza_profunda.py` detecta y adapta.

## DB ARCHIVO / ENTRENAMIENTO — 182.255.84.124
- 411,495 docs. Recibe el harvest de OJ (66.154) y las ingesta del flujo histórico.
- Chunks **con** `id` bigserial; `texto_search` GENERATED; `articulo_num` backfilled (875K).
- Destino del export CPT: ❌ CORREGIDO — el export de Tlamatini debe salir de **162** (más completa y limpia). 182 queda como respaldo histórico del pipeline viejo.

## Storage server — 161.129.70.21 (⚠️ CAÍDO)
- Servía `/srv/corpus` por NFS a 162 (`/opt/aijusticia/corpus_downloads`, mount `hard`).
- Caído desde ~agosto 2026: provocó 20 procesos D-state (zombis del harvest lexmx) y la muerte silenciosa del DOF backfill.
- 14-oct: desmontado con `umount -f -l`, fstab limpiado, `corpus_downloads` recreado como disco local de 162 (161GB libres — suficiente).
- Cuando reviva: montar como storage de Nextcloud/Office (con opción `soft`, no `hard`).

## Reglas
- El chat NUNCA escribe al archivo; el harvest escribe SOLO vía batch_upsert.
- `corpus/status` (engine, cache 5 min) es la vista pública del estado.
