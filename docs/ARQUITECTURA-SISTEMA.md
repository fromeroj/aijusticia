# Arquitectura del Sistema — AI Justicia

> Actualizado: 18 noviembre 2026. Este documento mapea **subsistemas →
> módulos → directorios → servers**. La misión y las reglas de colaboración
> viven en [`VISION.md`](VISION.md); el detalle operativo por componente en
> [`components/`](components/); operación y despliegue en
> [`../DEPLOYMENT.md`](../DEPLOYMENT.md).

---

## 1. Los 12 subsistemas en una tabla

| # | Subsistema | Directorio (repo) | Server | Estado |
|---|---|---|---|---|
| 1 | Web App | `apps/web/` | 162 :3000 (nginx :6234) | 🟢 |
| 2 | API Producto | `engine/ai_justicia/api/` | 162 :8000 (systemd) | 🟢 |
| 3 | Izel + Bibliotecario (agentes) | `engine/.../api/routes/chat_stream.py` → extraer a `agents/` | dentro del engine | 🟢 |
| 4 | RAG (retrieval) | `engine/.../retrieval/` + `chat_stream::_buscar_*` | librería del engine | 🟢 |
| 5 | Tlamatini (modelo) | `models/tlamatini/` (ex `tohil/`) | entrenamiento en Mac; artefactos GGUF/MLX | 🟡 |
| 6 | Data Consumer | `data/` (harvesters, ingestion, quality, prep) | 162 (crons), 66 (harvest), Mac (browser) | 🟢 |
| 7 | DBs | prod **local en 162** · archivo 182 muerto | postgres 16 | 🟢 |
| 8 | Auth | `engine/.../api/routes/{auth,registro,email}.py` | dentro del engine | 🟢 |
| 9 | Office (Nextcloud) | `office/` | 162 Docker :8080 | 🟢 |
| 10 | Eval | `eval/` + `models/tlamatini/eval_bateria.py` | Mac (corre contra prod) | 🟢 |
| 11 | Infra/CI | `infra/`, `.github/workflows/ci.yml`, crons 162 | RackNerd (Caddy) + runners | 🟢 |
| 12 | Marca/GTM | `brand/` (www, deck), `docs/article-draft.md` | tlamatini.live | 🟢 |

---

## 2. Server map — qué corre dónde

```
USUARIO (navegador)
   │ HTTPS
   ▼
RACKNERD 192.227.167.147 — Caddy en Docker (:80/:443)
   │ TLS aijusticia.mx, laley.com.mx → reverse_proxy
   ▼
PRODUCCIÓN 162.35.113.166 (3 vCPU · 11GB RAM · 197GB disco)
   ├── nginx :6234
   │    ├── /health /query /dossiers /auth /admin /jobs
   │    │   /documentos /corpus/status /chat/stream  → FastAPI :8000
   │    └── /* (resto)                                → Next.js :3000
   ├── systemd: aijusticia-engine (uvicorn ×2), aijusticia-web (next start)
   ├── PostgreSQL 16 LOCAL (127.0.0.1:5432) — LA DB canónica
   │    493,354 documentos · 19M chunks · expuesta solo a 66 con scram
   ├── Docker: aijusticia-oficina (Nextcloud :8080 + Collabora :9980
   │    + postgres + redis) — datadir en DISCO LOCAL
   ├── Crontab:
   │    11:30 CDMX  dof_diario.sh         (ingesta DOF del día)
   │    02:30 CDMX  mantenimiento_nocturno.sh (limpieza + SIVEPJ + SJF + UNAM)
   │    04:00 UTC   backup_cron.sh → backup_db.sh (pg_dump + off-site SSH)
   └── /opt/aijusticia/{engine,app,oficina,data,backups,corpus_downloads}

AUXILIAR 66.154.100.25 (3 vCPU · 2GB · 30GB)
   └── harvesters pesados y recovery → escriben DIRECTO a 162 (:5432 scram)
       /opt/aijusticia/{engine,data,corpus_downloads,run_oj.sh}

STORAGE 148.135.106.227 "tlamatini" (1 vCPU · 933MB · 197GB) — Multacom, LA
   └── NFS: /srv/backups (dumps off-site) · /srv/corpus (ro, workspace UNAM)
       ⚠ 933MB RAM: solo bulk tolerante — NADA latency-critical (lección NFS)

MUERTO: 182.255.84.124 (DB archivo — suspendida 15-oct) · 161.129.70.21 (NFS viejo)

MAC STUDIO (casa) — cosechas con navegador (Playwright/CDP), entrenamiento
   Soup de Tlamatini, LM Studio (legacy). Túnel autossh vestigial → 66.154.
```

---

## 3. Árbol del repo ↔ módulos ↔ subsistema

```
aijusticia/
├── engine/                        # ⚙️ UNIDAD DE DEPLOY → 162:/opt/aijusticia/engine
│   └── ai_justicia/
│       ├── api/                   # [2] API producto — FastAPI app, main.py
│       │   └── routes/            #    14 routers: query, chat_stream ⭐, dossiers,
│       │                          #    auth, registro, bufetes, archivos, admin,
│       │                          #    corpus_status, email, practica, tts, jobs
│       ├── retrieval/             # [4] RAG — fts_index ⭐ (dos fases + locator),
│       │                          #    bm25_index, embeddings (off), hybrid, reranker
│       ├── corpus/                # [7] capa DB — store ⭐ (batch_upsert,
│       │   │                      #    chunk_and_index), models ⭐ (Fuente/Jerarquia),
│       │   └── adapters/          #    clean, adapters/ por fuente (dof, sjf ⭐…)
│       ├── llm/                   # [5→3] cliente OpenAI-compat (MiniMax/Tlamatini swap)
│       ├── verification/          # NLI + citation_resolver + abstention (/query clásico)
│       ├── ingestion/             # [6] runner + scheduler + health (rutas legacy)
│       ├── dossiers/ auth/ email/ # expedientes, identidad, notificaciones
│       ├── jobs/ ocr/ tools/ eval/# workers, OCR, utilidades, eval offline
│       └── pipeline/              # pipeline clásico /query (pre-Izel)
│   ├── migrations/                # SQL (006 email_auth, RLS dossiers…)
│   └── .env                       # creds — NUNCA commitear, NUNCA borrar en 162
│
├── apps/web/                      # [1] Next.js → 162:/opt/aijusticia/app
│   └── src/app/                   # chat ⭐, estado, studio, panel, casos, dossiers,
│   └── src/lib/chatStream.ts      # entrar, cuenta, onboarding, admin, tlamatini…
│                                  # cliente SSE (token/laws/done/reset/error)
│
├── data/                          # [6] Data Consumer (corre en 162 y 66)
│   ├── harvesters/                # 37 scripts: harvest_ordenjuridico ⭐ (resume,
│   │   │                          # disk-safe), _edomex, _chiapas, _coahuila (API
│   │   │                          # bloqueada), _sivepj, _nl (Playwright pendiente),
│   │   │                          # redescarga_oj ⭐, recupera_oj ⭐ (OOXML),
│   │   └── browser/               # extension-jalisco (CDP + reCAPTCHA)
│   ├── ingestion/                 # ingest_all ⭐ (DOF/SJF diarios con watermark),
│   │   │                          # ingest_sentencias, ingest_unam_tesis ⭐ (NUL-fix),
│   │   │                          # backup_db ⭐ (superuser + integridad + off-site),
│   │   │                          # refrescar_leyesbiblio ⭐ (consolidadas + PDF-fallback)
│   ├── quality/                   # limpieza_profunda ⭐ (idempotente, dual-schema)
│   └── prep/                      # prep_cpt_completo ⭐, build_harness (export Tlamatini)
│
├── models/tlamatini/              # [5] Soup CLI: soup-*.yaml, Makefile
│   │                              # (prep/smoke/eval/merge/export-gguf), merge_linear
│
├── eval/                          # [10] eval_bateria_prod ⭐ (8 casos contra prod)
│   └── runs/                      # JSONs históricos (score por corrida)
│
├── office/                        # [9] compose Nextcloud+Collabora+DB+redis
├── infra/                         # [11] deploy.sh ⭐, salud.py ⭐, cron/ (3 wrappers),
│   │                              # ci_ed25519.pub (llave CI), requirements
├── brand/                         # [12] deck/ (LaTeX+HTML+PDF), www/ (tlamatini.live)
└── docs/                          # VISION ⭐, ARQUITECTURA-SISTEMA (este), INDEX,
                                   # components/×12, diseño histórico con banners
```

⭐ = archivo con lógica crítica o recientemente reparado.

---

## 4. Arquitectura interna por subsistema

### [3+4] Izel + Bibliotecario + RAG — el corazón del producto

```
POST /chat/stream {consulta, historial}
  │
  ├─▶ PARALELO: Bibliotecario (LLM, max_tokens 3000) → {ley, leyes[], terminos[]}
  │                                                     │
  │                                                     ▼
  │                     _buscar_en_ley(ley, terminos):
  │                       Fase 1: pool ≤1500 docs por titulo_search (FTS)
  │                       Fase 2: chunks; ORDER cobertura, rank×(art?1.5)×recencia
  │                     + _buscar_recientes(terminos): DOF ≤150d determinístico
  │                       (boost ×2.2 decretos de reforma, fecha explícita)
  │                                                     │
  ▼                                                     ▼
Izel (LLM stream) ◀── pasajes (máx 6, 400 chars, recientes primero)
  │  guardas: purge CJK, <think>-solo=vacío→reintento×3 (5000 tokens el 3º),
  │  anti-voseo, fechas-solo-del-pasaje, "gana el pasaje fresco",
  │  pasajes irrelevantes se declaran, nunca inventar artículos
  │
  └─▶ SSE: token* → laws → done (reset/error ante fallo)
```

- **Modelo**: `LMSTUDIO_LLM_MODEL` (env var). Historia: M3 → (crisis thinking
  forzado server-side 28-oct) → M2.7 → **M3.1-Flash + `reasoning_effort:"low"`**
  (actual, única combinación que responde limpio). Contrato OpenAI-compatible —
  el swap es una env var.
- **Ranking**: `cobertura DESC, rank×(es_articulo?1.5)×(recencia 1+1.2·e^(−d/180d))`;
  bibliotecario `max_tokens 3000` (el reasoning del formato nuevo se come el JSON
  con 1500).
- **Calidad medible**: `eval/eval_bateria_prod.py` — 8 casos, **5/8** en
  M3.1-Flash (varianza ±1); el techo de M3 sano fue 6-7/8. Los fallos residuales
  (B4 confunde órgano administrador, C2 confabula leyes) son de calidad del
  modelo, no de retrieval — el retrieval entrega los pasajes correctos.

### [6] Data Consumer — tres cadenas de ingesta

```
DIARIA (162, crons):  DOF 11:30 CDMX → ingest_all(DOF, watermark ✓)
                      02:30 mantenimiento: limpieza_profunda (idempotente)
                        + SIVEPJ (dedup) + SJF diario (watermark ✓) + UNAM resume
                        ⚠ puentes oficiales: DOF puede callar 6 días (umbral salud)
PESADA (66.154):      harvest_ordenjuridico (24,076 ✓ completo, disk-safe)
                      + recupera_oj (OOXML mislabeled — terminó)
                      + redescarga_oj (3,039 → 1,382 recuperadas ✓, 1,657 OCR-backlog)
Navegador (Mac):      Playwright/CDP — NL (pendiente), Jalisco (a medias)
```

Gotchas hard-won (cada uno costó horas — documentados en el código):
- `dossiers` tiene FORCE RLS → **pg_dump solo como superuser** (backup_db.sh),
  y SIEMPRE validar integridad del dump (gzip -t + COPY dossiers presente).
- JSONL de UNAM trae bytes NUL → sanitizar `\x00` siempre antes de insertar.
- Watermarks: `ingestion_watermarks` DEBE tener PK — sin ella ningún watermark
  se guarda y cada corrida nocturna re-rastrea el universo (y muere al final).
- NFS del storage se ahoga (933MB RAM) → solo bulk tolerante, nunca app-data
  (los segfaults de Apache del office salieron de ahí).
- `backup_db.sh` valida integridad (gzip -t + COPY dossiers) y borra si inválido.
- Trabajos pesados: SOLO ventana nocturna de 162 (02:30 CDMX) o en 66.

### [5] Tlamatini — pipeline de entrenamiento

```
data/prep/prep_cpt_completo.py  (export desde 162 — NUNCA desde 182, muerta)
  → JSONL CPT (leyes consolidadas + sentencias + doctrina UNAM + harness pairs)
    → Soup CLI smoke (QLoRA, ~35 min) → full CPT (Mac 275GB, horas)
      → merge_linear.py (α-blend sobre base Qwen3.6-35B-A3B)
        → eval_bateria.py (30 preguntas offline) + eval_bateria_prod --url (A/B)
          → si gana a MiniMax: export GGUF/MLX + swap de env var en 162
```

### [7] DBs — una canónica, un archivo muerto, un storage

| DB | Dónde | Rol | Esquema particular |
|---|---|---|---|
| **Prod** | 162 local | Serving del chat + producto | chunks **sin** columna `id`; `texto_search`+`titulo_search` GENERATED; `articulo_num` backfilled |
| ~~Archivo~~ | 182 | ❌ suspendida 15-oct; su rol lo absorbió 162 | chunks **con** `id` — los scripts portables detectan el schema |
| Storage NFS | 148 /srv | backups off-site + corpus lectura (CPT) | — |

---

## 5. Flujos de datos principales

1. **DOF diario**: cron 11:30 CDMX → `ingest_all --fuentes DOF` (watermark) →
   batch_upsert → chunks+FTS → consultable al instante → `corpus/status`.
2. **Pregunta de usuario**: browser → SSE → Izel → Bibliotecario → RAG (leyes
   consolidadas + decretos ≤150d) → respuesta con citas [n] + panel de leyes.
3. **Backup diario**: 04:00 UTC → pg_dump superuser (bypass RLS) → integridad
   → rsync SSH off-site a `tlamatini`/srv/backups (⏳ backlog nov-2026 drenando).
4. **Cosecha OJ**: 66 → re-descarga/recuperación → batch_upsert directo a 162.
5. **CPT**: prep exporta de 162 → Soup en Mac → checkpoint → A/B baterías → swap.

---

## 6. Puertos, protocolos y credenciales (mapa rápido)

| De → A | Puerto/protocolo | Auth |
|---|---|---|
| Internet → Caddy :443 | HTTPS (Let's Encrypt) | — |
| Caddy → 162 nginx :6234 | HTTP interno (red propia) | — |
| nginx → :8000 / :3000 / :8080 | HTTP localhost | — |
| engine → postgres 127.0.0.1:5432 | TCP scram-sha-256 | pass en `.env` |
| 66 → 162 postgres :5432 | TCP scram (pg_hba solo 66) | pass rotada (`/root/.pg_pass_rotada`) |
| 162 → 148 :2049 | NFSv4 soft (backups, corpus ro) | IP-allowlist |
| 162 → 148 :22 | SSH (llave ed25519) | key-only |
| CI runner → 162/66/148 :22 | SSH (llave `infra/ci_ed25519`) | GitHub secret `CI_SSH_KEY` |
| engine → api.minimax.io :443 | HTTPS | `LMSTUDIO_API_KEY` |
| Mac → 66/162/148 :22 | SSH key-only (deploy, cosechas) | llave del usuario |

Creds: `.env` del engine (DB + LLM key) · `/root/.pg_pass_rotada` (162) ·
`infra/ci_ed25519` (privada, gitignored) + secret GitHub `CI_SSH_KEY`.
Pendiente de endurecer: NFS sin TLS (propuesta: WireGuard 162↔148).

---

## 7. ¿Está bien documentado? — mapa de verdad

| Pregunta | Dónde se responde |
|---|---|
| ¿Para qué existe cada pieza y cómo colaboran? | `VISION.md` §1-3 |
| ¿Qué módulo hace qué, archivo por archivo? | **este doc §3-4** |
| ¿Qué corre en cada server, con qué recursos y puertos? | **este doc §2 y §6** |
| ¿Cómo deployo / diagnostico / qué cron hace qué? | `DEPLOYMENT.md` |
| ¿Cómo opera cada subsistema y sus gotchas? | `components/<subsistema>.md` |
| ¿Qué tan bueno es el asistente hoy? | `eval/runs/` + `make bateria` |
| ¿Qué cambió recientemente y por qué? | `git log` (cada commit explica el porqué) |

Deuda documental restante: `ARQUITECTURA.md` (banner histórico — su plan de
routers ya se ejecutó), `arquitectura.md` y `engine/ARCHITECTURE.md` describen
el diseño de julio (baneados), `ui-spec-completa.md` no refleja el chat
Izel-rediseñado (la verdad vive aquí §4 y en `components/izel.md`).
