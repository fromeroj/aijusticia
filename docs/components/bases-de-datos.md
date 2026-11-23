# Componente: Bases de datos

**Una base canónica** (producción). La de archivo está congelada y su contenido
útil ya fue importado a la canónica (23-nov-2026, verificado por clave).

## DB PRODUCCIÓN — local en 162.35.113.166
- Postgres 16, `127.0.0.1:5432`, db/user `aijusticia` (password en
  `/opt/aijusticia/engine/.env`; expuesta por TCP sólo a 66.154.100.25 con scram).
- **500,868 documentos · ~19.5M chunks** (23-nov-2026). La única que sirve al chat.
- Schema: `documentos` (con `titulo_search` GENERATED), `documentos_chunks`
  (**sin columna `id`**; `texto_search` GENERATED; `articulo_num` puede ser NULL),
  `actores`, `bufetes`, `dossiers`, `citas`, `source_health`,
  `ingestion_watermarks`, `pending_jobs`, …
- Dos particularidades que rompen cosas si se olvidan:
  - `dossiers` tiene **FORCE ROW LEVEL SECURITY** → `pg_dump` sólo funciona como
    superuser (`sudo -u postgres`). Con el rol de la app el dump se trunca ahí.
  - `ingestion_watermarks` debe tener **PRIMARY KEY (fuente)** → sin ella ningún
    watermark se guarda y cada corrida nocturna re-rastrea todo (y muere al final).
- Respaldos: `data/ingestion/backup_db.sh` (cron 04:00 UTC): dump verificado,
  retención local de 3, réplica off-site al storage por rsync sobre SSH.

## DB ARCHIVO — 182.255.84.124 (hostname `aijusticia.mx`): CONGELADA
- Por qué dejó de servir (7-nov): su disco de 59GB se llenó al 100% (39GB de
  postgres + WAL + logs sin mantenimiento) → postgres sin espacio. El OS nunca se
  apagó; además su red externa estuvo inalcanzable unos días.
- **23-nov — comparación real contra producción** por `(fuente, dedup_key)`:
  - ANTES: **7,487 claves sólo en 182** — 5,944 gacetas estatales publicadas del
    27-oct al 7-nov (Durango, Baja California, Chiapas, Colima, Chihuahua,
    Guanajuato), 1,409 leyes de OrdenJuridico, 105 notas DOF y 29 copias vacías.
  - Importadas con `data/ingestion/importar_jsonl_documentos.py`: **7,446
    documentos y 833,896 chunks** (sin pisar nada: `ON CONFLICT DO NOTHING`).
  - DESPUÉS: quedan **41 claves sólo en 182**, todas prescindibles: 29 copias
    viejas de leyes con texto vacío, 11 gacetas con menos de 200 caracteres y 1
    nota DOF que ya está en producción con la misma fecha y título.
- ⚠️ **Corrección**: el 22-nov este documento afirmaba que 182 era subconjunto de
  producción "verificado". Sólo se había verificado para OrdenJuridico (15-oct);
  la afirmación general era falsa y el servidor estuvo a punto de darse por
  prescindible con 7,486 documentos únicos dentro.
- Las gacetas llegaron a 182 porque ese servidor todavía corría su scheduler de
  fuentes (`aijusticia-ingest.timer`), que producción nunca tuvo (ver
  `data-consumer.md`).
- Dumps de 182 en `tlamatini:/srv/archive/` (3 archivos). Sólo se comprobó que el
  flujo gzip es válido; **no** que `pg_dump` hubiera terminado (marca de cierre).
  Con el contenido útil ya en producción, ese archivo es redundante.
- Estado: encendido, postgres DETENIDO, timer de ingesta DETENIDO, ~3.5GB libres.
  **Ya se puede cancelar el VPS.**
- La Mac lee la canónica por túnel SSH (autossh `tunnel162`, 127.0.0.1:5434 → 162:5432).

## Storage — 148.135.106.227 (hostname `tlamatini`)
- `/srv/backups` (dumps off-site, llegan por rsync sobre SSH), `/srv/archive`,
  `/srv/corpus`. 1 vCPU / 933MB: sólo para volumen tolerante, nunca para datos de
  una aplicación (ver `office.md`).
- ⚠️ **80% usado (23-nov) y sin política de retención**: cada dump pesa 9.7GB.
  `backup_db.sh` deja de lanzar réplicas si quedan menos de 20GB libres, para no
  llenar el disco (así murió 182).
- 161.129.70.21: storage VIEJO, caído desde agosto; desmontado de 162.

## Reglas
- El chat NUNCA escribe; las cosechas escriben sólo por upsert idempotente.
- Un documento entra a la canónica por su clave original o no entra.
- Antes de dar un servidor por prescindible: comparar claves contra la canónica y
  guardar el resultado — no extrapolar una verificación parcial.
- `/corpus/status` (engine, caché 15 min, recalcula sin bloquear) es la vista pública.
