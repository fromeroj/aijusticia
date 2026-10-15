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

## Estado / pendientes (15-oct)
- SIVEPJ 30,526 sentencias CDMX: en cola nocturna (mantenimiento 02:30).
- Harvest OJ: COMPLETO — 24,022 directos + recuperación en curso de 2,789
  rechazos que eran OOXML mal-extensionados (`recupera_oj.py`, extrae y sube a 182).
- ❌ **Coahuila BLOQUEADO**: la API lista autoridades y sentencias, pero el
  acceso a PDF está roto por su lado — URL firmada de GCS devuelve 403 y
  `?descargar=true` devuelve `url` vacía. Evidencia en 15-oct. Requiere
  contacto con PJECZ o descubrir el nuevo flujo de descarga.
- NL: metadatos sin texto — re-corrida Playwright en Mac.
- 7 códigos de `LEYES_CLAVE` siguen 404 (lnsijp, lm, la, lamp, lcp, cft, cpcf —
  abreviaturas oficiales desconocidas; 4 ya corregidos: lgpdppso/lopjf/cnpcf/lgsm).
- Morelos: ordenjuridico.gob.mx lista solo 5 ordenamientos para el estado —
  no es un bug nuestro.
- Storage: 148.135.106.227 (hostname `tlamatini`) reemplaza al caído
  161.129.70.21 — NFS `/srv/office` y `/srv/backups` montados en 162 (soft).
