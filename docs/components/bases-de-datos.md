# Componente: Bases de datos

**Dos bases, dos roles.** No se mezclan.

## DB PRODUCCIÓN — local en 162.35.113.166
- Postgres 16, `127.0.0.1:5432`, db/user `aijusticia` (password en `/opt/aijusticia/engine/.env`).
- 473,848 docs · 14.1M chunks · ~3.9B tokens. La única que sirve al chat.
- Schema: `documentos` (con `titulo_search` GENERATED), `documentos_chunks` (**sin columna `id`**; `texto_search` GENERATED; `articulo_num` backfilled), `actores`, `bufetes`, `dossiers`, `citas`, `source_health`, `harvest_scripts`, `ingestion_watermarks`, `pending_jobs`, …
- Backup: `backup_db.sh` diario 04:00 (cron en 162).
- ⚠️ Difiere del schema de 182 (ver abajo) — `limpieza_profunda.py` detecta y adapta.

## DB ARCHIVO — 182.255.84.124 (hostname `aijusticia.mx`): CONGELADA 23-nov-2026
- Por qué dejó de servir (~7-nov): su disco de 59GB se llenó al 100% (39GB de
  postgres + WAL + logs sin mantenimiento) → postgres sin espacio → sin
  conexiones. El OS nunca se apagó (uptime continuo); además la red externa
  estuvo muerta unos días (se recuperó sola).
- **Archivo preservado** en el storage `tlamatini:/srv/archive/` (23-nov):
  dump completo íntegro de 5.6GB (con chunks) + 2 copias sin-chunks de 2.5GB.
  430,388 documentos — contenido ⊂ producción (verificado superset).
- Estado final: postgres DETENIDO, disco con 11GB libres tras limpieza de
  journals/logs. Listo para cancelar el VPS o mantener como fósil.
- **Una sola DB canónica desde el 29-oct**: producción (162). El harvest de 66
  escribe DIRECTO a 162 (postgres expuesto solo a 66.154.100.25 con scram).
- La Mac lee la canónica vía túnel SSH local (autossh `tunnel162`, puerto
  local 5434 → 162:5432) — cerrada la última dependencia de 182.

## Storage server — 161.129.70.21 (⚠️ CAÍDO)
- Servía `/srv/corpus` por NFS a 162 (`/opt/aijusticia/corpus_downloads`, mount `hard`).
- Caído desde ~agosto 2026: provocó 20 procesos D-state (zombis del harvest lexmx) y la muerte silenciosa del DOF backfill.
- 14-oct: desmontado con `umount -f -l`, fstab limpiado, `corpus_downloads` recreado como disco local de 162 (161GB libres — suficiente).
- Cuando reviva: montar como storage de Nextcloud/Office (con opción `soft`, no `hard`).

## Reglas
- El chat NUNCA escribe al archivo; el harvest escribe SOLO vía batch_upsert.
- `corpus/status` (engine, cache 5 min) es la vista pública del estado.
