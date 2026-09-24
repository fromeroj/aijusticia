# Arquitectura del Corpus y RAG — AI Justicia

## 1. Estructura de la Base de Datos

### 1.1 Tabla `documentos`

| Columna | Tipo | Descripción |
|---|---|---|
| `id` | bigint | ID interno (serial) |
| `fuente` | text | Fuente: DOF, SJF, SentenciasEdomex, SentenciasCDMX, SentenciasBC, SentenciasQro, SentenciasChiapas, SentenciasCoahuila, SentenciasSonora, GacetaEstatal, GacetaCDMX, OrdenJuridico, LeyesBiblio, SCJN-Libros, JustiaEstatal, LexMX |
| `entidad` | text | Entidad federativa (NULL para federal) |
| `materia` | text | Materia: Civil, Penal, Familiar, Mercantil, Laboral, etc. |
| `tipo` | text | Tipo de documento: Ley, Código, Reglamento, Sentencia, Tesis |
| `titulo` | text | Título del documento |
| `texto` | text | Texto completo extraído (pdftotext, unrtf, OCR) |
| `registro_sjf` | text | Número de registro SJF (solo tesis) o clave de dedup |
| `fecha_reforma` | date | Fecha de última reforma |
| `fecha_publicacion` | date | Fecha de publicación oficial |
| `fecha_vigencia` | date | Fecha de entrada en vigor |
| `derogado` | boolean | Si está derogado |
| `jerarquia` | smallint | Jerarquía constitucional (1=Constitución, 2=Ley, ...) |
| `vinculante` | boolean | Si es vinculante |
| `url_origen` | text | URL de donde se cosechó |
| `raw` | jsonb | Metadatos adicionales (JSON) |
| `dedup_key` | text | Clave única de deduplicación |
| `titulo_search` | tsvector | Índice FTS del título |
| `created_at` | timestamp | Fecha de ingesta |
| `updated_at` | timestamp | Última actualización |

### 1.2 Tabla `documentos_chunks`

| Columna | Tipo | Descripción |
|---|---|---|
| `documento_id` | bigint | FK a documentos.id |
| `ordinal` | integer | Número de fragmento dentro del documento |
| `texto` | text | Fragmento de texto (~300 tokens) |
| `texto_search` | tsvector | Índice FTS del fragmento (spanish stemming) |
| `embedding` | vector | Embedding para búsqueda semántica (opcional) |
| `articulo_num` | integer | Número de artículo extraído (para citación directa) |

### 1.3 Índices

| Índice | Tabla | Tipo | Uso |
|---|---|---|---|
| `idx_chunks_fts` | documentos_chunks | GIN | Búsqueda full-text en español |
| `idx_chunks_articulo` | documentos_chunks | B-tree | Localización directa de artículos |
| `uq_doc_fuente_dedup` | documentos | B-tree | Deduplicación por fuente+clave |
| `idx_doc_fuente_dedup` | documentos | B-tree | Mismo, para la versión raw |

### 1.4 Números actuales

- **456,590 documentos** totales
- **13.8M chunks** indexados
- **16 fuentes** de datos
- **34 entidades** con contenido
- **~3.8B tokens** estimados

---

## 2. El Pipeline RAG

### 2.1 Flujo de una consulta

```
Usuario escribe pregunta
    │
    ▼
┌──────────────────────────────────────┐
│ Izel (agente conversacional)         │
│ - Entrevista al usuario              │
│ - Detecta materia y entidad          │
│ - Streaming (~2s al primer token)    │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Bibliotecario (subagente)            │
│ - Identifica la ley aplicable        │
│ - Busca DENTRO de la ley             │
│ - Retorna artículos exactos          │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ Respuesta con citas verificadas      │
│ [n] → pasaje oficial de la ley       │
└──────────────────────────────────────┘
```

### 2.2 Retrieval: búsqueda full-text en dos fases

El retrieval usa PostgreSQL FTS (Full-Text Search) con stemming en español:

**Fase 1 (barata):** `ts_rank_cd` plano sobre `texto_search` → top 200 fragmentos

**Fase 2 (cara):** re-rank con:
- Peso del título (A-weight 1.3× para leyes)
- Multiplicador de fuente (LeyesBiblio 1.3×, DOF 1.2×)
- Penalización de basura (tablas, encabezados)
- Boost de artículos (chunks que empiezan con "Artículo N" suben)

**Localizador de artículos**: si la consulta menciona un artículo específico
("artículo 50 LFT"), se busca directamente el chunk que contiene ese artículo
usando el índice `articulo_num`.

### 2.3 Normalización de lenguaje

Antes de buscar, el sistema traduce lenguaje coloquial a terminología legal:

| Usuario dice | Sistema busca |
|---|---|
| "me despidieron" | "despido injustificado" → artículo 47 LFT |
| "no me pagan aguinaldo" | "aguinaldo" → artículo 87 LFT |
| "cargo no autorizado" | "operación no reconocida" → LTOSF art. 81 |

---

## 3. El Bibliotecario: cómo encuentra las leyes aplicables

### 3.1 El flujo del Bibliotecario

Cuando Izel necesita saber qué ley aplica, invoca al Bibliotecario, que:

1. **Recibe** la conversación completa (últimos mensajes del usuario e Izel)
2. **Identifica** la materia (civil, penal, familiar...) y la entidad
3. **Genera** términos de búsqueda técnicos (lenguaje legal, no coloquial)
4. **Busca** en el corpus dentro de la ley identificada
5. **Retorna** los artículos exactos con su texto oficial

### 3.2 Configuración

```python
# engine/ai_justicia/api/routes/chat_stream.py

# La API de búsqueda del Bibliotecario:
# POST {api}/sentencias/datatable?autoridad_id=X&fecha=YYYY-MM-DD
# Headers: X-Api-Key (extraída del JS ofuscado del portal)

# El Bibliotecario NO usa embeddings — usa FTS con:
#   - Matching de frases exactas (operador <-> en tsquery)
#   - Cobertura (cuántas frases distintas toca cada chunk)
#   - Boost a chunks que INICIAN un artículo
```

### 3.3 El algoritmo de ranking

```
Score = cobertura × 10 + ts_rank_cd × 1 + es_articulo_boost

donde:
  cobertura   = cuántas frases de búsqueda aparecen en el chunk
  ts_rank_cd  = ranking nativo de PostgreSQL FTS
  es_articulo = 1 si el chunk empieza con "Artículo N"
```

---

## 4. Rutas de Configuración

```
aijusticia/
├── engine/
│   ├── ai_justicia/
│   │   ├── config.py                      # TODAS las settings (DB, LLM, NC, etc.)
│   │   ├── api/
│   │   │   ├── main.py                    # App FastAPI + routers
│   │   │   └── routes/
│   │   │       ├── auth.py                # Frase, dispositivo, Google OAuth, NC
│   │   │       ├── registro.py            # Registro con email + contraseña
│   │   │       ├── chat_stream.py         # Izel + Bibliotecario (SSE)
│   │   │       ├── corpus_status.py       # Dashboard /estado
│   │   │       ├── dossiers.py            # Expedientes, bóveda, compartir
│   │   │       └── ...
│   │   ├── corpus/
│   │   │   ├── models.py                  # Fuente enum, Documento dataclass
│   │   │   ├── store.py                   # batch_upsert, dedup, chunking
│   │   │   ├── adapters/                  # Por fuente (SJF, DOF, edomex...)
│   │   │   └── http_client.py             # Cliente HTTP con warmup
│   │   ├── auth/
│   │   │   ├── jwt.py                     # Emisión/verificación JWT
│   │   │   └── deps.py                    # Dependencias FastAPI
│   │   └── retrieval/
│   │       ├── fts_index.py               # FTS bidireccional
│   │       └── reranker.py                # Re-ranking de pasajes
│   ├── scripts/
│   │   ├── harvest_edomex.py              # Cosecha Edomex (Elasticsearch)
│   │   ├── harvest_chiapas.py             # Cosecha Chiapas (XLSX)
│   │   ├── harvest_sonora.py              # Cosecha Sonora (API JSON)
│   │   ├── harvest_coahuila.py            # Cosecha Coahuila (API v3)
│   │   ├── harvest_ejecutorias.py         # Ejecutorias SJF
│   │   ├── harvest_jalisco_fase2.py       # Jalisco (CDP + reCAPTCHA v3)
│   │   ├── harvest_ordenjuridico.py       # Leyes estatales (OrdenJurídico)
│   │   ├── harvest_bc.py                  # BC (API JSON)
│   │   ├── ingest_sentencias.py           # Ingestor genérico de sentencias
│   │   ├── ingest_universal.py            # Ingestor universal de JSONL
│   │   └── prep_cpt_completo.py           # Preparación del corpus CPT
│   ├── data/
│   │   ├── cpt/                           # Export CPT local
│   │   ├── questions_clean.json           # Batería de preguntas
│   │   └── ...
│   └── migrations/                        # SQL migrations
├── tohil/
│   ├── soup-tlamatini-smoke.yaml          # Control LoRA (smoke test)
│   ├── soup-tlamatini-full.yaml           # Full CPT (4×H200 FSDP)
│   ├── merge_linear.py                    # Merge lineal post-CPT
│   ├── eval_bateria.py                    # Batería de evaluación
│   ├── Makefile                           # make prep/smoke/eval
│   └── README.md                          # Diseño experimental
├── docs/
│   ├── article-draft.md                   # Whitepaper Tlamatini
│   ├── reporte_portales_sentencias_32_estados.md  # Inventario 32 estados
│   ├── autenticacion.md                   # Diseño de auth progresiva
│   ├── tlamatini-readiness.md             # Auditoría de preparación
│   └── CORPUS.md                          # Composición del corpus
└── app/src/
    ├── app/estado/page.tsx                # Dashboard /estado
    ├── components/studio/                 # Studio (despacho)
    ├── components/chat/                   # Chat ciudadano
    └── lib/                               # Frontend utils
```

---

## 5. Variables de Configuración

### 5.1 Engine (`.env` en `/opt/aijusticia/engine/`)

```bash
# PostgreSQL (corpus + usuarios)
PG_HOST=127.0.0.1
PG_PORT=5432
PG_DB=aijusticia
PG_USER=aijusticia
PG_PASSWORD=***

# LLM (MiniMax API)
LMSTUDIO_BASE_URL=https://api.minimax.io/v1
LMSTUDIO_API_KEY=***
LMSTUDIO_LLM_MODEL=MiniMax-M3

# Resend (email)
RESEND_API_KEY=***

# Nextcloud (bóveda)
BUFETE_NC_URL=https://oficina.konen.guru
BUFETE_NC_USER=admin
BUFETE_NC_APP_PASS=***

# JWT
JWT_SECRET=***
```

### 5.2 Chihuahua/Coahuila API (obtenida del JS del portal)

```python
# La key se extrae del bundle JS ofuscado del portal
X_API_KEY = "gAAAAABlErx6..."
API_BASE = "https://api.justiciadigital.gob.mx/v3"
# Headers: {"X-Api-Key": KEY}
# Endpoints:
#   GET /autoridades?distrito_id=N
#   GET /sentencias/datatable?autoridad_id=N&pagina=N&tamano=50
#   GET /sentencias/{id}  → incluye "url" a GCS
```

### 5.3 Jalisco (reCAPTCHA v3)

```python
# El backend exige token reCAPTCHA v3 por petición
SITE_KEY = "6LeVK48tAAAAABtfSIPLusp-4cMthtofl497dZvX"
# Token: grecaptcha.execute(SITE_KEY, {action: 'visitor_verify'})
# Header: X-Recaptcha-Token: {token}
# PDF: GET /toca/{id}/file?modo=descargar → S3 presigned URL
```

---

## 6. Benchmark y Preguntas de Test

Las baterías de evaluación viven en `engine/data/`:

| Archivo | Contenido |
|---|---|
| `questions_clean.json` | Preguntas curadas y limpias |
| `questions_curated.json` | Preguntas curadas originales |
| `questions_en.json` | Preguntas en inglés (traducidas) |
| `questions_good.json` | Subconjunto de alta calidad |
| `extra_questions.json` | Preguntas adicionales |
| `preguntas_all.jsonl` | Todas las preguntas combinadas |
| `foro_questions_index.json` | Índice de preguntas de foro |

La batería de evaluación de Tlamatini (30 preguntas ciudadanas) está en
`tohil/eval_bateria.py` — cubre laboral, consumidor, familiar, vivienda y civil.

---

## 7. Cómo Agregar un Nuevo Estado

1. **Recon**: abre el portal del PJ estatal, identifica si hay API JSON, WebForms o SPA
2. **Clasifica la técnica**: API JSON → harvester directo · WebForms → viewstate · SPA → CDP
3. **Escribe el harvester** en `engine/scripts/harvest_{estado}.py`
4. **Corre** en el server: `nohup python3 harvest_{estado}.py > log 2>&1 &`
5. **Ingiere** con `ingest_sentencias.py Sentencias{Estado} '{JSONL pattern}'`
6. **Agrega el enum** en `models.py` si es una fuente nueva
7. **Verifica** en `/estado` que el mapa se pinte
