# AI Justicia — Arquitectura del Motor LLM + RAG

> Documento vivo. Última actualización: 29 julio 2026.
> Estructura, decisiones y plan de ejecución del directorio `engine/`.

---

## 1. Visión general

AI Justicia es un motor de IA jurídica mexicana que combina **un LLM fine-tuned
con LoRA** con **recuperación aumentada (RAG)** sobre fuentes oficiales y
**verificación automática de cada cita** contra registros reales. El objetivo:
respuestas precisas, con alucinaciones reducidas al mínimo técnico posible y
trazabilidad completa.

El motor se organiza en **3 capas** y un **pipeline de inferencia de 5 etapas**.

```
┌─────────────────────────────────────────────────────────────┐
│                    API (FastAPI, :8000)                       │
│   POST /query/stream (SSE)  ·  /admin/*  ·  /docs            │
└───────────────────────────┬─────────────────────────────────┘
                            │
                ┌───────────▼───────────┐
                │   ORQUESTADOR          │  pipeline/orchestrator.py
                │   (5 etapas + SSE)     │  + traza en DB
                └───────────┬───────────┘
                            │
   ┌────────────────────────┼────────────────────────┐
   │                        │                        │
   ▼                        ▼                        ▼
┌──────────┐         ┌──────────────┐         ┌──────────────┐
│ CAPA 1   │         │   CAPA 2     │         │   CAPA 3     │
│ RAG      │ ──────► │   LLM        │ ──────► │ VERIFICACIÓN │
│          │         │              │         │              │
│ FTS +    │         │ Qwen3-Next   │         │ resolvedor   │
│ vectorial│         │ -80B-A3B     │         │ + abstención │
│ + rerank │         │ + LoRA r=32  │         │              │
└──────────┘         └──────────────┘         └──────────────┘
   ▲                        ▲                        │
   │                        │                        ▼
┌──┴──────────┐      ┌──────┴───────┐       ┌──────────────┐
│ CORPUS      │      │  LM STUDIO   │       │ DECISIÓN     │
│ 158K docs   │      │  :1234/v1    │       │ RESPONDER o  │
│ 32 estados  │      │  (OpenAI-    │       │ ABSTENERSE   │
│ + federal   │      │  compatible) │       │ → abogado    │
│ + SJF       │      │              │       │              │
└─────────────┘      └──────────────┘       └──────────────┘
```

---

## 2. Las 3 capas

### Capa 1 — Conocimiento (RAG)

**Propósito:** cobertura completa y vigencia. El sistema nunca responde "de memoria".

| Componente | Módulo | Tecnología |
|---|---|---|
| Corpus oficial | `corpus/` | DOF, LeyesBiblio, SJF, leyes de 32 entidades federativas |
| Persistencia | `corpus/store.py` | PostgreSQL 16 + pgvector (`:5433`) |
| **Índice léxico (primario)** | `retrieval/fts_index.py` | **PostgreSQL FTS** `to_tsvector('spanish')` con matching OR + stopwords jurídicas |
| Índice semántico (secundario) | `retrieval/vector_index.py` | pgvector coseno + nomic-embed-text-v1.5 (768 dim) |
| Recuperación híbrida | `pipeline/retrieve.py` | FTS (peso 0.75) + vectorial (peso 0.25). Vectorial-only descartado si FTS retorna suficiente |
| Reranking jurídico | `retrieval/reranker.py` | jerarquía art. 133 constitucional, vinculante vs persuasivo, vigencia |
| **Documentos en corpus** | — | **~158,873 documentos** (federal + 32 estados + SJF jurisprudencia) |

**Fuentes oficiales y sus claves de verificación:**

| Fuente | Qué contiene | Clave de cita |
|---|---|---|
| LeyesBiblio | Legislación federal consolidada (diputados.gob.mx) | artículo + fecha de reforma |
| SJF | Jurisprudencia y tesis (sjf2.scjn.gob.mx) | número de registro digital |
| DOF | Diario Oficial de la Federación | fecha de publicación |
| GacetaEstatal | Legislación de 32 entidades (Playwright + HTTP) | ingesta programada |
| LEYFED | Leyes federales en zip (LEYFED_zip) | filename original |

### Capa 2 — Razonamiento (LLM + LoRA)

**Propósito:** calidad de razonamiento jurídico en español mexicano a costo bajo.

#### Modelo base

| Parámetro | Valor |
|---|---|
| **Modelo** | **Qwen3.6-35B-A3B** (MLX bf16, **sin cuantización**) |
| **Arquitectura** | `qwen3_5_moe` — MoE híbrido (Qwen3_5MoeForConditionalGeneration) |
| **Parámetros totales** | 34.7B |
| **Parámetros activos por token** | ~3B (MoE: 256 experts, 8 activos) |
| **Capas** | 40 |
| **Hidden size** | 2048 |
| **Atención** | Híbrida: self_attn cada 8 capas + GatedDeltaNet (linear attn) en el resto |
| **Contexto** | 262,144 tokens |
| **Tamaño en disco** | 65 GB (bf16 sin cuantizar) |
| **Licencia** | Apache 2.0 |
| **Servidor de inferencia** | LM Studio (`localhost:1234/v1`, API OpenAI-compatible) |

> **Decisión: por qué Qwen3.6-35B-A3B bf16 y no Qwen3-Next-80B-A3B 8-bit:**
> - Probamos Qwen3-Next-80B (80B, 8-bit quantized) — mejor base para generación
>   pero **LoRA es inestable en modelos cuantizados**: la escala del adapter se
>   amplifica por la cuantización produciendo output corrupto (caracteres chinos,
>   repeticiones). bf16 sin cuantizar permite LoRA preciso.
> - Qwen3.6-35B bf16 + LoRA v3 produce **citas exactas de artículos** en 7/7 tests.
> - El modelo 80B está disponible como fallback para RAG sin LoRA si se necesita
>   más capacidad de razonamiento en consultas complejas.

#### Fine-tuning LoRA

| Parámetro | Valor |
|---|---|
| **Tipo** | LoRA (Low-Rank Adaptation) |
| **Rank** | 16 |
| **Scale (alpha)** | 32.0 (alpha = 2 × rank) |
| **Dropout** | 0.05 |
| **Capas objetivo** | Últimas 16 de 40 |
| **LR** | 5e-5 |
| **Optimizer** | AdamW |
| **Batch size** | 1 (grad accumulation 8) |
| **Max seq length** | 2048 |
| **Grad checkpoint** | True |
| **Trainable params** | 8.5M (0.024% del total) |
| **Tamaño del adapter** | 32 MB |
| **Memoria pico (training)** | ~76 GB (model 65 + LoRA/grad/optim 11) |
| **Tiempo de training (400 iters)** | ~20 min |

**Claves LoRA** (arquitectura híbrida — self_attn + GatedDeltaNet + shared_expert):

```yaml
lora_parameters:
  rank: 16
  scale: 32.0
  dropout: 0.05
  keys:
    # Self-attention estándar (capas 0, 8, 16, 24, 32, 39)
    - "self_attn.q_proj"
    - "self_attn.k_proj"
    - "self_attn.v_proj"
    - "self_attn.o_proj"
    # Linear attention / GatedDeltaNet (mayoría de capas)
    - "linear_attn.in_proj_a"
    - "linear_attn.in_proj_b"
    - "linear_attn.in_proj_z"
    - "linear_attn.in_proj_qkv"
    - "linear_attn.out_proj"
    # Shared expert (NO switch_mlp — 256 experts son demasiados para LoRA)
    - "mlp.shared_expert.up_proj"
    - "mlp.shared_expert.down_proj"
    - "mlp.shared_expert.gate_proj"
```

> **Nota sobre claves LoRA:** Qwen3.6 tiene arquitectura híbrida — la mayoría
> de capas usan GatedDeltaNet (atención lineal tipo Mamba) con `in_proj_*`, y cada
> 8ª capa usa self_attn estándar con `q/k/v/o_proj`. Las claves deben incluir AMBOS
> tipos. NO aplicar LoRA a `switch_mlp` (256 experts = estallaría el tamaño del adapter).
>
> **Nota sobre cuantización:** El modelo DEBE ser bf16 (sin cuantizar) para que LoRA
> funcione correctamente. Probamos con Qwen3-Next-80B 8-bit quantized y el adapter
> produjo output corrupto — la escala del LoRA se amplifica por la dequantización.

#### Dataset de entrenamiento

| Fuente | Ejemplos | Origen |
|---|---|---|
| Synthetic v2 | 3,848 | Chunks de leyes federales principales (LFT, CC, CPF, PROFECO, etc.) |
| Synthetic boost | 998 | Materias subrepresentadas (Laboral +300, Civil +300, Penal +200) |
| Foro real | 247 | justiciamexico.mx/foro.php (Q&A reales de ciudadanos) |
| **Total bruto** | **5,093** | |
| **Tras dedup + filtro** | **~2,300** | Filtro: signatures/promulgaciones/tablas + NFKC + 10-gram artifacts |

**Formato de cada ejemplo:**
```json
{
  "messages": [
    {"role": "system", "content": "Eres AI Justicia, asistente jurídico mexicano..."},
    {"role": "user", "content": "Me despidieron sin motivo, ¿qué puedo hacer?"},
    {"role": "assistant", "content": "<think>\n\n</think>\n\nDe acuerdo con Artículo 484 de la Ley Federal del Trabajo:\n\n..."}
  ],
  "metadata": {"materia": "Laboral", "fuente": "LeyesBiblio", "synthetic": true}
}
```

> **Formato `<think>`:** Aunque Qwen3-Next es non-reasoning (Instruct), el chat
> template del modelo inserta `<think>\n\n</think>\n\n` antes de la respuesta
> cuando `enable_thinking=False`. El dataset incluye este prefijo para que el
> adapter aprenda el formato correcto.

### Capa 3 — Garantías (verificación)

**Propósito:** alucinaciones residuales detectadas y bloqueadas antes de llegar al usuario.

Cada oración de la respuesta que tiene cita pasa verificación:

| Control | Qué verifica | Módulo |
|---|---|---|
| **Resolvedor de citas** | La cita existe contra el registro real | `pipeline/verify.py` |
| **Ratio de sustento** | Proporción de oraciones con respaldo | `pipeline/verify.py` |

> **Dev alpha:** `sustentado = resolucion.resuelto` (NLI relajado — no bloquea).
> `abstention_min_backed_ratio = 0.30` (relajado para dev).

Si la proporción de oraciones sustentadas cae bajo el umbral, el sistema
**se abstiene**: declara que no hay base suficiente y ofrece derivar a un abogado.

---

## 3. Pipeline de inferencia — 5 etapas

Cada consulta pasa por estas 5 etapas en orden, con **streaming SSE** al frontend:

```
Usuario: "Me despidieron sin motivo, ¿qué puedo hacer?"
   │
   ▼
[1] ANÁLISIS        Extraer materia, jurisdicción, vigencia, entidades
   │                pipeline/query_analysis.py
   │                "Laboral · federal · 2026"
   │                → detectar_info_faltante() puede generar preguntas aclaratorias
   ▼
[2] RECUPERACIÓN    FTS (consulta original, peso 0.75) + vectorial (expandida, peso 0.25)
   │                pipeline/retrieve.py → recuperar_y_rerankear()
   │                FTS: to_tsquery OR con stopwords jurídicas
   │                Filtro: score >= 25% del top score
   ▼
[3] RERANKING       Ordenar por relevancia jurídica (art. 133, vinculante)
   │                retrieval/reranker.py
   │                Top-K pasajes finales (rerank_top_k)
   ▼
[4] GENERACIÓN      LLM + LoRA redacta SOLO desde los pasajes, con cita [n]
   │                llm/generate.py + llm/prompts.py
   │                Sistema de "contrato estricto de citas"
   │                → SSE: stage events + token streaming
   ▼
[5] VERIFICACIÓN    Cada cita verificada contra el pasaje
   │                pipeline/verify.py
   │                Calcular ratio de sustento → RESPONDER o ABSTENERSE
   │                → SSE: done payload con referencias
   ▼
Respuesta + citas verificadas + traza de auditoría en DB
```

| Etapa | Módulo | Tiempo típico |
|---|---|---|
| 1. Análisis | `pipeline/query_analysis.py` | <100ms (heurística) |
| 2. Recuperación | `pipeline/retrieve.py` | ~2s (FTS + embeddings + DB) |
| 3. Reranking | `retrieval/reranker.py` | <10ms |
| 4. Generación | `llm/generate.py` | 10-60s (con LoRA adapter) |
| 5. Verificación | `pipeline/verify.py` | <1s (dev alpha, sin NLI) |

**Total típico:** 15-65s por consulta (vs 60-300s con NLI completo).

### Flujo de clarify (2 round-trips SSE)

Si `detectar_info_faltante()` detecta que faltan datos críticos (ej. estado
para leyes estatales), el pipeline hace 2 viajes:
1. **Primer viaje:** envía evento `clarify` con preguntas interactivas
2. **Segundo viaje:** usuario responde → pipeline completo con `respuestas_aclaratorias`

### Caso B (deferred response)

Si el diagnóstico identifica que falta una ley no descargada:
1. Crea `pending_job` en DB (estado: pendiente)
2. Worker en background descarga la ley → la ingiere → re-ejecuta pipeline
3. Usuario recibe respuesta diferida cuando el job completa

---

## 4. Estructura del directorio `engine/`

```
engine/
├── ARCHITECTURE.md              ← este documento
├── README.md                    ← setup + fine-tuning docs
├── pyproject.toml               ← dependencias
├── docker-compose.yml           ← PostgreSQL + pgvector (:5433)
├── .env.example                 ← variables de entorno
│
├── ai_justicia/                 ← paquete Python principal
│   ├── config.py                ← settings (pydantic-settings)
│   │
│   ├── corpus/                  ═══ CAPA 1: Conocimiento ═══
│   │   ├── models.py            ← Documento, Chunk, Fuente, Jerarquia
│   │   ├── store.py             ← batch_upsert, chunk_and_index, get_conn
│   │   ├── clean.py             ← NFKC, HTML strip, 10-gram filter, non-Spanish
│   │   ├── watermark.py         ← incremental ingestion watermarks
│   │   ├── adapters/            ← scrapers por fuente
│   │   │   ├── sjf.py           ← SJF API JSON (sjf2.scjn.gob.mx)
│   │   │   ├── dof.py           ← DOF HTML scraping
│   │   │   ├── leyes_biblio.py  ← diputados.gob.mx .doc download
│   │   │   ├── generico.py      ← PDF/DOC genérico (HTTP, dead-domain rewrite)
│   │   │   ├── playwright_adapter.py ← JS-rendered states (Chromium headless)
│   │   │   ├── edomex.py        ← Estado de México leyvig{NNN}.pdf
│   │   │   ├── nuevo_leon.py    ← HCNL HTML scraping
│   │   │   └── jalisco.py       ← CongresoJal PDF extraction
│   │
│   ├── retrieval/               ═══ índice híbrido ═══
│   │   ├── fts_index.py         ← PostgreSQL FTS (PRIMARIO, peso 0.75)
│   │   ├── vector_index.py      ← pgvector coseno (SECUNDARIO, peso 0.25)
│   │   ├── bm25_index.py        ← Legacy BM25 (reemplazado por FTS)
│   │   └── reranker.py          ← reranking jurídico (art. 133)
│   │
│   ├── llm/                     ═══ CAPA 2: Razonamiento ═══
│   │   ├── client.py            ← LMStudioClient (OpenAI-compatible adapter)
│   │   ├── prompts.py           ← system prompt + templates + contrato de citas
│   │   └── generate.py          ← generación anclada + parser de oraciones [n]
│   │
│   ├── pipeline/                ═══ orquestación de etapas ═══
│   │   ├── query_analysis.py    ← etapa 1 (materia, jurisdicción, clarify)
│   │   ├── retrieve.py          ← etapas 2-3 (FTS+vectorial híbrido + rerank)
│   │   ├── generate.py          ← etapa 4 (generación anclada)
│   │   ├── verify.py            ← etapa 5 (verificación + abstención)
│   │   ├── diagnostico.py       ← A/B diagnosis tras abstención
│   │   └── orchestrator.py      ← end-to-end + traza + Caso B
│   │
│   ├── jobs/                    ═══ background jobs ═══
│   │   └── worker.py            ← pending_jobs queue (Caso B)
│   │
│   ├── ingestion/               ═══ ingesta programada ═══
│   │   ├── runner.py            ← run_source() end-to-end
│   │   ├── health.py            ← 3 detectores (empty-result, page-hash, yield-drift)
│   │   ├── scheduler.py         ← entrypoint: python -m ai_justicia.ingestion.scheduler
│   │   └── store.py             ← CRUD source_health + ingestion_runs
│   │
│   ├── api/                     ═══ API REST + SSE ═══
│   │   ├── main.py              ← FastAPI app, /query/stream, /admin/*, clarify gate
│   │   └── schemas.py           ← request/response models
│   │
│   └── eval/                    ═══ evaluación ═══
│       ├── benchmark.py         ← benchmark MX (tipo LegalBench-Instruct)
│       └── metrics.py           ← tasa de citas incorrectas
│
├── scripts/                     ← CLI utilities + training
│   ├── setup_db.py              ← crea esquema Postgres
│   ├── generate_synthetic_v2.py ← genera ejemplos sintéticos desde corpus
│   ├── train_lora.py            ← prepara dataset + lanza mlx_lm.lora
│   ├── serve_lora.py            ← sirve modelo + adapter via mlx_lm.server
│   ├── process_questions.py     ← pipeline traducir+clasificar+responder
│   └── run_pipeline.py          ← ejecuta consulta end-to-end
│
├── data/                        ← datos de entrenamiento + adapters
│   ├── training/                ← datasets JSONL
│   │   ├── train.jsonl          ← split de entrenamiento
│   │   ├── valid.jsonl          ← split de validación
│   │   ├── synthetic_v2.jsonl   ← ejemplos desde leyes federales
│   │   ├── synthetic_boost.jsonl← boost Laboral/Civil/Penal
│   │   ├── ift_qa.jsonl         ← Q&A reales del foro
│   │   └── final_training_v3.jsonl ← consolidado
│   │
│   ├── lora_adapter/            ← v1 adapter (deprecated, sin <think> fix)
│   ├── lora_adapter_v3/         ← v3 adapter (Qwen3.6, val loss 0.921)
│   └── lora_adapter_v4/         ← v4 adapter (Qwen3-Next-80B, rank 32) ← PRÓXIMO
│
└── tests/
    └── fixtures/
        └── corpus_fixture.py    ← documentos MX reales (dev)
```

---

## 5. Stack tecnológico

### Inferencia
- **LM Studio** (`localhost:1234/v1`) — API OpenAI-compatible
  - LLM: `Qwen3-Next-80B-A3B-Instruct` (MLX 8-bit, 84.7 GB)
  - Embeddings: `text-embedding-nomic-embed-text-v1.5` (768 dim)
- **mlx-lm** (fine-tuning + serving con adapter LoRA)
- **vLLM** (producción Nivel 2, on-premise) — mismo adapter, sin cambiar código

### Datos
- **PostgreSQL 16 + pgvector** (Docker, `:5433`)
- Tablas: `documentos`, `documentos_chunks`, `trazas`, `pending_jobs`,
  `source_health`, `ingestion_runs`, `pares_destilacion`

### Frontend
- **Next.js 15** (`app/`) — chat multi-burbuja, stage progress, expandible references
- **Zustand** (state: messages, stages, clarify, timings)
- **SSE** streaming via fetch + ReadableStream

### Scraping
- **Playwright** (headless Chromium para sitios JS-rendered de congresos estatales)
- **requests + BeautifulSoup4** (HTTP directo para sitios estáticos)
- **textutil** (conversión .doc → texto en macOS)

### Hardware
- **Mac Studio M3 Ultra · 256 GB unified memory · 28 cores**
- Modelo + LoRA training: ~95 GB peak
- LM Studio + modelo cargado: ~85 GB
- Ambos simultáneamente: ~180 GB (cabe en 256 GB)

---

## 6. Cobertura del corpus (32 estados + federal)

| Categoría | Documentos | Fuentes |
|---|---|---|
| Federal (leyes) | ~6,000 | LeyesBiblio (diputados.gob.mx) + LEYFED zip |
| Jurisprudencia | ~50,000 | SJF (sjf2.scjn.gob.mx) |
| DOF | ~500 | Diario Oficial (con cap de 500/run) |
| Estados (32) | ~100,000 | Gacetas estatales via 3 adapter types |
| **Total** | **~158,873** | |

**Adapters de ingesta por estado:**
- **Dedicados:** Edomex, Nuevo León, Jalisco, CDMX
- **HTTP genérico:** Michoacán, Guerrero, Sonora, Chihuahua, etc.
- **Playwright (JS-rendered):** Chiapas, Veracruz, Yucatán, Zacatecas, Sinaloa
- **Degradados:** Puebla (Cloudflare WAF), Sonora (Vue SPA con API key)

**Health monitoring:** 3 detectores automáticos en `source_health`:
- `empty-result` — 2 resultados vacíos consecutivos = unhealthy
- `page-hash` — hash del listing cambió + bajo yield = degraded
- `yield-drift` — EWMA de documentos < 30% del promedio = degraded

---

## 7. Fine-tuning LoRA — pipeline

### Scripts

| Script | Función |
|---|---|
| `scripts/generate_synthetic_v2.py` | Genera ejemplos desde leyes federales (FTS-based Q&A) |
| `scripts/train_lora.py` | Prepara dataset + lanza `mlx_lm.lora` con config |
| `scripts/serve_lora.py` | Sirve modelo + adapter via `mlx_lm.server` (:1235) |
| `scripts/process_questions.py` | Pipeline: traducir + clasificar + responder con RAG |

### Historial de training

| Versión | Modelo base | Rank | Iters | Val Loss | Notas |
|---|---|---|---|---|---|
| v1 | Qwen3.6-35B-A3B | 16 | 500 | 1.097 | Sin `<think>` prefix → output degradado |
| **v3** | **Qwen3.6-35B-A3B** | **16** | **400** | **0.921** | **Con `<think>` fix → ✅ producción** |
| v4a | Qwen3-Next-80B-A3B (8-bit) | 32 | 400 | 0.858 | Scale 64 → output corrupto (quantization) |
| v4b | Qwen3-Next-80B-A3B (8-bit) | 32 | 300 | 0.987 | Scale 32 → output débil, perdió formato de citas |
| — | **Conclusión** | — | — | — | **LoRA requiere bf16 sin cuantizar. v3 es el adapter de producción.** |

### Tests de calidad v3 (7/7 pasaron)

| Pregunta | Cita correcta |
|---|---|
| "Me despidieron sin motivo" | Art. 484 LFT ✓ |
| "Casero sube renta al doble" | Art. 2744 CC Federal ✓ |
| "Días de aguinaldo" | Art. 87 LFT ✓ |
| "Tiempo para pagar finiquito" | Art. 96 LFT ✓ |
| "Cargo no reconocido tarjeta" | Art. 108 PROFECO ✓ |
| "Ex no deja ver hija" | Art. 248 CC Federal ✓ |
| "Acusación falsa" | Art. 19 CPF ✓ |

---

## 8. Hallazgos del paper SaulLM y cómo se aplican

SaulLM (Colombo et al., 2024, arXiv 2403.03883 y 2407.19584) es el primer LLM
público entrenado específicamente para derecho.

### SaulLM vs AI Justicia

| Aspecto | SaulLM | AI Justicia |
|---|---|---|
| Modelo base | Mistral 7B / Mixtral 54B-141B | **Qwen3-Next-80B-A3B** |
| Método | Continued pretraining (30-520B tokens) | **LoRA** (constraint: Apple Silicon) |
| Idioma | English only | **Español mexicano** |
| Corpus | FreeLaw, MultiLegal Pile | DOF, SJF, LeyesBiblio, 32 estados |
| Verificación | Ninguna | **RAG + verificación de citas** |
| Evaluación | LegalBench-Instruct | Benchmark MX propio |

### Lo que adoptamos de SaulLM
- Filtro de calidad del corpus (NFKC, 10-gram artifacts, non-Spanish detection)
- IFT sintético multi-turno
- Inclusión de datos generales (anti-catastrophic-forgetting)
- Evaluación post-cutoff (control de leakage)

### Lo que SaulLM NO cubre (nuestra ventaja)
- RAG ni recuperación → nuestra Capa 1
- Verificación de citas → nuestra Capa 3
- Destilación ni volante de datos → nuestros pasos 3-5
- Multilingüe / español → nuestro enfoque MX nativo

---

## 9. Referencias

- **SaulLM-7B:** Colombo et al., 2024, arXiv 2403.03883
- **SaulLM-54B/141B:** arXiv 2407.19584 — scaling domain-specific models
- **LoRA:** Hu et al., 2021, arXiv 2106.09685 — Low-Rank Adaptation
- **RAFT:** Gorja & Jafari — robustez ante recuperación imperfecta
- **LegalBench-Instruct:** Guha et al. 2023 — base para benchmark MX
- **Qwen3:** Alibaba, Apache 2.0 — modelo base
- **mlx-lm:** Apple Machine Learning Research — framework MLX para Apple Silicon
