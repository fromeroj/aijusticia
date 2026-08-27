# Corpus AI Justicia — Sistema de Ingesta

Catálogo de todas las fuentes del corpus, cómo se cosechan, su estado y la
estrategia de **recolección diferencial** (traer solo lo nuevo).

El registro máquina está en la tabla `harvest_scripts` (PostgreSQL, DB
`aijusticia`): cada fuente tiene el código del script versionado, su watermark
en `estado` jsonb, y la estrategia incremental en `diferencial`.

---

## Arquitectura de ingesta

```
PORTAL ORIGEN → harvester (script) → JSONL (corpus_downloads/) → ingestor → documentos + chunks
```

- **JSONL intermedio**: cada harvester escribe `{titulo, tipo, texto, url, ...}` —
  auditorable antes de ingerir; re-ingesta idempotente por `dedup_key`.
- **dedup_key**: `md5(fuente-interna|titulo|texto[:100])` con constraint único
  `(fuente, dedup_key)` → re-corridas no duplican.
- **Chunks**: 1,200 chars, sin solapamiento. El chunker del servicio de ingesta
  del sistema corre en paralelo: los ingestores usan `ON CONFLICT DO NOTHING`.
- **Dos ejecutores**: server-tmux (accesible desde el server) y mac-local
  (geo-bloqueos mexicanos: CDMX, Veracruz, SIVEPJ, Justia).

## Fuentes — estado 2026-08-27

| Fuente (DB) | Contenido | Docs | Tokens | Método | Diferencial |
|---|---|---|---|---|---|
| SJF | Jurisprudencia + tesis aisladas (epígrafes) | 149,995 | ~22M | API interna scjn | watermark registro |
| DOF | Notas 1999-2026 (backfill 5 años completo; 1999-2021 en curso) | 18.5K+ | ~90M+ | scraping-http index_111 | fecha diaria |
| GacetaEstatal | Leyes vigentes 32 estados (varios harvesters) | ~10K | ~85M | portal por estado | versión/reforma |
| GacetaCDMX | Gaceta Oficial 2014-2026 completa | 2,193 | 122.5M | wayback CDX | CDX from=fecha |
| SentenciasCDMX | SIVEPJ universo completo | 28,146 | ~34M | playwright + URLs firmadas | trimestres recientes |
| SentenciasEdomex | PJEdomex API (en curso) | ~197K proyectados | 0.6-1.6B proy | api-rest elástica | year reciente + estado.json |
| BJV | Libros IIJ-UNAM (en curso) | 5,680 total | ~1.4B proy | OAI-PMH | from=datestamp |
| SCJN-Libros | Cuadernillos jurisprudencia (OCR Vision) | 445 | 114K | ocr | on-demand |
| CDMX-Doctrina | Libros doctrina CDMX (OCR en curso) | 12 | ~1M | ocr | on-demand |
| LeyesBiblio | Leyes federales + reglamentos diputados | 777 | ~38M | playwright | hash listado |
| JustiaEstatal | Estados débiles (Sonora 200, Colima 140) | 340 | ~8M | playwright | slugs nuevos |
| LawInstruct (SFT) | Instrucciones jurídicas EN — NO va a documentos | 269,577 reg | — | HF api | estático |

## Estrategias de diferencial por fuente

### DOF (`dof_backfill99b.py`, server-tmux)
`listar_desde()` camina día por día hacia atrás. Histórico 1999-2021 corre una
sola vez; incremental diario = `listar_desde(fecha_inicio=hoy)`.
**Watermark**: fecha del último día consultado (ver `ingestion_watermarks`).

### SIVEPJ (`harvest_sivepj2.py`, mac-local) — COMPLETO
Universo agotado: 4,512 combos (19 materias × juzgados × 2019-2026 × T1-T4),
0 errores, 212 juzgados detectados vacíos por probe.
**Diferencial**: re-query solo `(materia, juzgado, año_actual, T_actual)` y
`(año_actual-1, T4)` por si publican tarde.
**Estado**: `sivepj_estado2_{0..3}.json` + `sivepj_vacios_{0..3}.json`.

### Edomex (`harvest_edomex.py`, server-tmux)
API: `GET /files/search/elastic?search=juicio&typeSearch=match&typeDocument=sentencias
&year=N&subject=<materia_id>&size=500&from=M` (máx 10K/slice → sub-rebanar por
trimestre con startDate/endDate). PDFs directos en `electronico.pjedomex.gob.mx`.
**Diferencial**: fase1 solo `year>=año_actual`; fase2 salta PDFs ya en `estado.json`.

### BJV (`harvest_bjv.py`, server-tmux)
OAI-PMH: `ListRecords?set=col_123456789_8972` (Libros BJV), resumption tokens.
Bitstream: handle page → `/xmlui/bitstream/handle/…/FILE.pdf?sequence=1`.
**Diferencial**: OAI acepta `from=YYYY-MM-DD` → solo datestamps > última corrida.

### Gaceta CDMX (`download_gaceta_cdmx.py`, mac-local) — COMPLETO
Wayback CDX: `portal_old/uploads/gacetas/*.pdf` (2,409 archivados con status 200).
Vivo primero, wayback de respaldo; metadatos (No./fecha) extraídos de la 1a página.
**Diferencial**: re-query CDX con `from=<fecha última>`.

### Leyes estatales (4 harvesters, mac-local)
- **CDMX** (Consejería): nombre de archivo codifica versión (`_5.9.pdf`) → descargar versiones mayores.
- **Veracruz** (SEGOB): tabla trae fecha de última reforma → solo fechas > watermark.
- **Puebla/Guerrero** (Playwright): docman gids cambian al reformar → diff de gids.
- **Justia**: listado Cloudflare (irregular); PDFs de docs.mexico.justia.com sin bloqueo.

### OCR doctrina (`ocr_doctrina.py`, mac-local)
Apple Vision (`ocrmac`, es-ES) a 150 dpi, ~0.7s/página. Solo para material
escaneado: SCJN cuadernillos ✓, CDMX doctrina ✓ (en curso), boletín PJCDMX (caro).

## Ingestores

| Qué | Dónde | Nota |
|---|---|---|
| `ingest_sentencias.py` | server `corpus_downloads/sivepj/` | SIVEPJ+Edomex, idempotente |
| `harvest_bjv.py descarga` | escribe JSONL directo | ingesta vía `ingest_bjv.py` (pendiente) |
| Ingestores ad-hoc | server `/tmp/ingest_*.py` | se migriston a scripts/ gradualmente |

Convención de ingesta: fuente nueva → INSERT con `ON CONFLICT (fuente,dedup_key)
DO NOTHING/UPDATE` + chunking 1,200 con `ON CONFLICT (documento_id,ordinal)`.

## Pendientes priorizados

1. Repositorio central UNAM: 48,053 tesis Facultad de Derecho (~1.9B) — reverse-engineering pendiente
2. Edomex fase2: ~197K PDFs
3. Revistas UNAM (Boletín Derecho Comparado, etc.)
4. derechoenmexico.mx: 214 libros (Google Drive → Playwright)
5. Boletín Judicial PJCDMX: 4,084 flip-books de imágenes (OCR masivo, caro)
