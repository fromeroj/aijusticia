# Componente: Data Consumer (cosecha, ingesta, limpieza)

**Qué es**: todo lo que llena y mantiene limpias las bases de datos.
**Vive en**: repo `data/` (harvesters/, ingestion/, quality/, prep/).
**Corre en**: 162 (DOF diario, ventana nocturna de mantenimiento), 66.154 (harvest pesado OJ→182), Mac (cosechas que requieren navegador).

## Piezas
- `harvesters/` — uno por fuente: `harvest_ordenjuridico.py` (32 estados, resume por `estado.json`, borra archivos tras extraer), `_edomex`, `_bc`, `_chiapas`, `_coahuila` (API PJECZ), `_sivepj` (CDMX), `_nl` (Playwright en Mac), `_lexmx`, `_ejecutorias` (Imperva + proxy), `browser/` (extension-jalisco).
- `ingestion/` — `ingest_all.py` (adapters DOF/SJF/LeyesBiblio/…), `ingest_sentencias.py` (JSONL→corpus, dedup por md5 del texto), `ingest_universal.py`, `migrar_*.py`, `cron_diferencial.sh` (⚠️ legacy, funcionalmente duplicado por `dof_diario.sh` — limpiar).
- `quality/` — `limpieza_profunda.py` (idempotente, portable a ambos schemas, solo toca filas sucias), `fix_titulos_oj.py`.
- `prep/` — `prep_cpt_completo.py`, `build_harness_mx.py` (export para Tlamatini).

## Cómo corre
| Job | Dónde | Cuándo |
|---|---|---|
| DOF diario | 162 cron 11:30 CDMX (`dof_diario.sh`) | diario |
| Mantenimiento (limpieza + re-ingestas) | 162 cron 02:30 CDMX (`mantenimiento_nocturno.sh`, nice 19) | diario |
| Harvest OJ 32 estados | 66.154 (`/opt/aijusticia/run_oj.sh`, setsid) | continuo hasta terminar |
| Cosechas con navegador | Mac, manual | por proyecto |

## Reglas
- Escribe SOLO vía `batch_upsert_documentos` (dedup por `(fuente, dedup_key)`).
- Nunca importa de `services/`; la DB de destino es un parámetro del entorno.
- Cosechas con WAF: curl_cffi impersonate=chrome; con reCAPTCHA: CDP/extension.
- Trabajos pesados: SOLO en ventana nocturna de 162 o en 66 (lección 14-oct: load 20 = sitio degradado).

## Estado / pendientes
- SIVEPJ 30,526 sentencias CDMX: en ingesta.
- Coahuila: harvester listo, sin correr → 162.
- NL: metadatos sin texto — re-corrida Playwright en Mac.
- 11 códigos 404 en `LEYES_CLAVE`; Morelos con 4 leyes en OJ (investigar).
- Storage server NFS (161.129.70.21) caído — `corpus_downloads` ahora es disco local de 162.
