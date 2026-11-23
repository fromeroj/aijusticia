# Componente: Data Consumer (cosecha, ingesta, limpieza)

**Qué es**: todo lo que llena y mantiene limpias las bases de datos.
**Vive en**: repo `data/` (harvesters/, ingestion/, quality/, prep/).
**Corre en**: 162 (DOF diario y ventana nocturna, por cron), 66.154 (cosechas pesadas, a mano), Mac (cosechas con navegador).

## Piezas
- `harvesters/` — uno por fuente: `harvest_ordenjuridico.py` (32 estados),
  `recupera_oj.py` / `redescarga_oj.py` (recuperación de rechazos y de leyes
  perdidas), `_edomex`, `_bc`, `_chiapas`, `_coahuila`, `_sivepj`, `_nl`,
  `_lexmx`, `_ejecutorias`, `browser/`.
- `ingestion/` — `ingest_all.py` (adapters DOF/SJF/LeyesBiblio, con watermark),
  `ingest_sentencias.py`, `ingest_unam_tesis.py`,
  `importar_jsonl_documentos.py` (trae filas de otra DB sin pisar nada),
  `refrescar_leyesbiblio.py`, `backup_db.sh`, `cron_diferencial.sh` (histórico).
- `quality/` — `limpieza_profunda.py` (incremental por defecto; `--completo`
  reanudable; memoria acotada), `rellenar_articulo_num.py` (número de artículo de
  los chunks de leyes; incremental + `--completo`), `fix_titulos_oj.py`.
- `prep/` — `prep_cpt_completo.py`, `build_harness_mx.py` (export para Tlamatini).

## Qué corre solo (crons de 162 — ver `infra/cron/`)

| Job | Cuándo | Qué hace |
|---|---|---|
| `dof_diario.sh` | 17:30 UTC | DOF de ayer y hoy (con watermark) |
| `mantenimiento_nocturno.sh` | 08:30 UTC | limpieza incremental (barrido completo los domingos) + SJF del día + número de artículo de leyes nuevas |
| `backup_cron.sh` | 04:00 UTC | dump verificado + réplica off-site |

Todo paso nocturno corre con tope de memoria (1.5GB), plazo y nice 19.

## Qué NO corre solo — y por qué (estado al 23-nov-2026)

| Fuente | Documentos | Último ingreso | Situación |
|---|---|---|---|
| DOF | 161,975 | diario | ✅ al día (no publica en puentes oficiales) |
| SJF | 150,509 | diario | ✅ al día con su feed |
| UNAM-Tesis | 17,616 | 11-nov | ✅ completa (el archivo tenía 17,619 con texto; no ~43K) |
| SentenciasCDMX | 42,947 | — | ✅ completa (SIVEPJ era duplicado puro) |
| OrdenJuridico (32 estados) | 29,261 | 23-nov | ✅ + 1,409 recuperadas de 182; quedan ~1,657 escaneadas sin texto (requieren OCR) |
| **GacetaEstatal (31 estados)** | 21,056 | **7-nov** | ❌ **sin cosecha en producción.** Lo que hay del 27-oct al 7-nov llegó por 182 |
| **LeyesBiblio** | 18 leyes canónicas | **15-oct** | ❌ **sin refresco automático** — se corre a mano |
| LexMX | 317 | agosto | ⚠️ manual |

**Gacetas.** El scheduler de fuentes —systemd `aijusticia-ingest.timer` que corre
`python -m ai_justicia.ingestion.scheduler` sobre las filas de `source_health`
(adaptadores `generico` / `playwright` por entidad)— **sólo existía en el server
viejo (182) y nunca se instaló en 162**. Además, 21 de las 31 fuentes de gaceta
llevan `degraded`/`unknown` desde el 27-ago (nunca funcionaron); sólo Baja
California y Durango terminaban limpias, y Chiapas, Chihuahua y Colima con 3
fallos seguidos. Restaurar la cosecha es un trabajo pendiente, no un switch.

**Leyes federales.** El `cron_diferencial.sh` viejo refrescaba a diario ~19 leyes
clave de diputados.gob.mx. Se quitó de 162 el 14-oct por considerarlo duplicado
del DOF; su parte DOF/SJF sí estaba cubierta, **el refresco de leyes no**. Desde
entonces la LFT y demás textos consolidados sólo se actualizan cuando alguien
corre `refrescar_leyesbiblio.py` a mano.

## Reglas (cada una salió de una falla real)
- Escribe sólo por upsert idempotente (`(fuente, dedup_key)`).
- **Nunca re-ingerir una fuente completa con los ingesters actuales**: deduplican
  sólo en memoria y reescriben todos los chunks (Nov 2026: ~4.6 millones de filas
  borradas y reinsertadas cada noche, pisando texto limpio con texto crudo).
- **Nunca `fetchall()` de textos largos**: un documento a la vez (las tesis UNAM
  miden 261K caracteres en promedio y hasta 3MB).
- Un trabajo nocturno sin tope de memoria acaba corriendo en horario laboral.
- Bytes NUL en JSONL de origen: sanear `\x00` antes de insertar.
- `pgrep`/`pkill -f` por SSH: el patrón siempre con corchetes (`[r]sync`), o se
  matchea a sí mismo y da un falso positivo.
- Exportar filas a JSONL: `COPY … TO STDOUT WITH (FORMAT csv, QUOTE E'\x01',
  DELIMITER E'\x02')`; el formato texto duplica las barras invertidas y rompe el JSON.
- Cosechas con WAF: curl_cffi `impersonate="chrome"`; con reCAPTCHA: CDP/extensión.
- Trabajos pesados: ventana nocturna de 162, 66 o la Mac.

## Pendientes
- **Las leyes estatales están mal troceadas.** Medición 23-nov (muestra de 1 de
  cada 97 leyes de OrdenJuridico): sólo el **5%** tiene ≥80% de sus chunks
  abriendo artículo; el **~75%** tiene menos del 30%. Causa: `chunk_documento`
  (`corpus/store.py`) sólo parte por `^Artículo\s+\d+` distinguiendo
  mayúsculas, y muchas leyes van en MAYÚSCULAS ("ARTÍCULO 1o.-") o con acentos
  rotos por la extracción ("ART�CULO"). Esas leyes se parten en ventanas de
  1,200 caracteres con artículos cortados entre chunks. Arreglo: patrón
  tolerante (`(?i)`, ordinales `1o/°/º`) en el troceador y re-trocear ~29K
  leyes (~2M chunks) en la ventana nocturna. Mientras tanto
  `rellenar_articulo_num.py` numera lo que sí abre con artículo.
- `articulo_num`: hasta el 23-nov era NULL en TODO documento con id ≥ 3,140,351
  (9.2M de chunks: ninguna ley estatal lo tenía). Barrido completo agendado
  para la noche del 23→24-nov.
- Instalar/reescribir el scheduler de gacetas en producción (ver arriba).
- Refresco semanal automático de leyes federales.
- Coahuila: la API lista pero el PDF da 403 (bloqueado de su lado).
- Nuevo León y Jalisco: sentencias a medias, requieren navegador.
- 7 códigos de `LEYES_CLAVE` dan 404 en diputados.gob.mx.
- OCR de ~1,657 leyes estatales escaneadas.
