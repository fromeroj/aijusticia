# Tlamatini — Estado de Preparación para Entrenamiento

**Fecha de auditoría: 18 septiembre 2026**
**Objetivo: smoke test CPT el lunes 22 sep 2026, corrida real tras validación**

---

## 1. Resumen Ejecutivo

Tlamatini está **listo para entrenar con el corpus actual** (~3.8B tokens queryables,
más los harvests activos que suman 2-4B adicionales en las próximas 48 horas). Los
harvesters de Edomex, Chiapas, Sonora y las ejecutorias del SJF corren autónomos.
El pipeline Tohil (Soup CLI) está validado de punta a punta en Mac — el lunes
solo se repiten los mismos comandos en 4×H200.

---

## 2. Estado del Corpus (auditado 18 sep)

| Fuente | Documentos | Tokens est. | Estado |
|---|---|---|---|
| DOF (Diario Oficial) | 161,283 | ~300M | ✅ Diario |
| SJF (tesis) | 150,187 | ~22M | ✅ Completo |
| LeyesBiblio (316 federales) | 1,170 | ~50M | ✅ Completo |
| OrdenJuridico (32 estados) | 26,470 | ~85M | ✅ Completo |
| Sentencias CDMX (SIVEPJ) | 42,947 | ~52M | ✅ Completo |
| Sentencias Edomex | 46,211 | ~3-4B | 🔄 Fase 2 extrayendo |
| Sentencias BC | 2,838 | ~250M | ✅ Completo |
| Sentencias Sonora | 25 | — | 🔄 Iniciando |
| Sentencias Chiapas | 0 (XLSX minando) | ~1-2B est. | 🔄 Corriendo |
| Gacetas estatales (15) | 15,123 | ~143M | ✅ Completo |
| Gaceta CDMX | 4,397 | ~143M | ✅ Completo |
| JustiaEstatal | 340 | — | ✅ |
| SCJN-Libros | 885 | — | ✅ |
| LexMX | 317 | — | ✅ |
| UNAM Tesis (manifiesto) | 43,423 | ~2-3B | ⏳ Pendiente ingesta |
| **TOTAL DB** | **453,487** | **~3.8B** | |
| **+ Edomex fase 2** | **+49K pendientes** | **~2B** | 🔄 |
| **+ Jalisco PDFs** | **+13K pendientes** | **~2B** | ⏸️ Extensión Chrome |
| **+ Ejecutorias SJF** | **23,008** | **~500M** | Harvester listo, requiere CDP |
| **TOTAL PROYECTADO** | **~550K** | **~8-10B** | |

---

## 3. Lo que YA está listo ✅

### 3.1 Corpus ingestado y queryable
- 448K+ documentos en PostgreSQL con FTS (búsqueda en español).
- 13.7M chunks indexados.
- Cada chunk citable por documento, fragmento y URL de origen.
- Dashboard público: aijusticia.mx/estado (actualiza cada 5 min).

### 3.2 Pipeline de entrenamiento (Tohil)
- Config LoRA + QLoRA: `tohil/soup-tlamatini-smoke.yaml` (control).
- Config full-parameter CPT: `tohil/soup-tlamatini-full.yaml` (tratamiento).
- Validado en Mac: 334 pasos en MPS con Qwen2.5-0.5B + corpus slice.
- Soup CLI v0.75+ maneja: plaintext JSONL, MoE, FSDP, DeepSpeed, packing.

### 3.3 Infraestructura de harvest
- Harvester genérico JSONL → corpus (ingest_universal.py).
- 12+ fuentes con harvesters documentados y técnicas reproducibles.
- Ingestor de sentencias estatales genérico (ingest_sentencias.py).
- Dashboard /estado como sistema de registro público.

### 3.4 Modelo de datos
- Fuente enum cubre 16 fuentes (federales, estatales, sentencias, gacetas, OCR).
- Entidad: 32 estados + Federal, normalizados.
- Dedup por hash de texto en cada ingesta.

---

## 4. Gaps que deben cerrarse ANTES del lunes

| # | Gap | Tarea | Estimado | Bloquea |
|---|---|---|---|---|
| 1 | **Edomex fase 2 sin terminar** | Esperar a que complete (99,400/178,439, ok=26,967) | ~24-48h | Corpus final |
| 2 | **Export CPT desactualizado** | Regenerar `derecho_mx.jsonl` con todo lo nuevo (OrdenJuridico 24K, BC 2.8K, CDMX +23K, Sonora, Chiapas) | 1h | Entrenamiento |
| 3 | **General replay 2-5%** | Descargar Wikipedia es + código + instruct (~500M tokens) | 2-4h | Mix de entrenamiento |
| 4 | **Harness pairs a escala** | Solo 586 pares (426 grounded). Objetivo: 50K+ minando considerandos→artículos de las 300K sentencias | 4-8h | Harness training |
| 5 | **Tohil pipeline completo** | Tokenizador, packing, config FSDP, merge lineal post-CPT, script de evaluación | 4-6h | Lunes |
| 6 | **Vast.ai setup** | Cuenta + instancia 4×H200 + SSH + Soup instalado | 1-2h | Entrenamiento |
| 7 | **Validación post-entrenamiento** | Batería 30 preguntas + comparación base vs CPT vs RAG-only | 2h | Resultados |

---

## 5. Gaps NO bloqueantes (post-entrenamiento)

| # | Gap | Impacto | Cuándo |
|---|---|---|---|
| 1 | Jalisco (1,417/13,272 PDFs) | +2-3B tokens adicionales | Semana 2 |
| 2 | Ejecutorias SJF (23K) | Sentencias completas | Sesión CDP |
| 3 | Coahuila (Enterprise captcha) | +147K registros | Sesión CDP |
| 4 | 20+ estados sin sentencias | Cobertura total | Batch, 2-3 estados/día |
| 5 | Morelos, Guerrero, Tabasco (57-300 docs c/u) | Cobertura débil | OrdenJuridico 2a pasada |

---

## 6. Datos descargados sin procesar (~120 GB)

| Archivo | Tamaño | Contenido | Acción pendiente |
|---|---|---|---|
| dump_texto_rag_sources.jsonl | 9.6 GB | Texto consolidado RAG | Verificar si ya está en DB |
| lawinstruct_instructivos/ | 1.9 GB | 51 archivos SFT | Ingest para Stage 2 SFT |
| lawinstruct_es/ | 15 MB | Instrucciones es | Ingest para SFT |
| reglamentos_federales.jsonl | 88.5 MB | Reglamentos federales | Ingest |
| reglamentos_edomex.jsonl | 32.9 MB | Reglamentos Edomex | Ingest |
| reglamentos_fed_v2.jsonl | 19 MB | Reglamentos v2 | Ingest |
| leyes_guerrero.jsonl | 25.2 MB | Leyes Guerrero | Ingest |
| leyes_justia_col.jsonl | 15 MB | Leyes Colima | Ingest |
| leyes_justia_sonora.jsonl | 19.5 MB | Leyes Sonora | Ingest |
| leyes_puebla.jsonl | 20.1 MB | Leyes Puebla | Ingest |
| leyes_veracruz.jsonl | 8 MB | Leyes Veracruz | Ingest |
| ocr_cdmx.jsonl | 9.4 MB | OCR CDMX | Ingest |
| ocr_scjn.jsonl | 0.5 MB | OCR SCJN | Ingest |
| preguntas_all.jsonl | 1.6 MB | Preguntas training | Ingest |
| unam_tesis/ | 4.8 GB | Tesis UNAM | Extraer texto + ingest |
| lora_adapter_v3/v4/v5 | 625 MB | Adaptadores LoRA previos | Referencia histórica |

---

## 7. Recursos del equipo

| Recurso | Ubicación | Estado |
|---|---|---|
| Corpus DB (PostgreSQL) | 162.35.113.166:/opt/aijusticia | 453K+ docs, activo |
| Archivos raw | 162.35.113.166:/opt/aijusticia/corpus_downloads | ~85 GB |
| Export CPT v0 | 162.35.113.166:cpt_export/ | 71 MB (desactualizado) |
| Export CPT local | Mac:data/cpt/ | 584 MB (train+valid) |
| Modelos LM Studio | Mac:~/.lmstudio/ | 239 GB (incluye Qwen 3.6-35B base) |
| Tohil configs | aijusticia/tohil/ | ✅ Committeado |
| Harvesters | aijusticia/engine/scripts/ | ✅ Committeado |
| Proxy IPRoyal | geo.iproyal.com:12321 | Credenciales en .env |
| Nextcloud (bóveda) | oficina.konen.guru | Activo, 12+ usuarios |
| Vast.ai | Por configurar | 4×H200, ~$3-5/h |

---

## 8. Cronograma

| Día | Tarea |
|---|---|
| **Hoy (vie)** | Regenerar export CPT + ingest universal + replay Wikipedia + harness pairs |
| **Sáb** | Edomex fase 2 termina → ingest → export final |
| **Dom** | Tohil pipeline completo (tokenizador, packing, merge script) + Vast.ai setup |
| **Lun** | Smoke test CPT (1 época, corpus completo, QLoRA) |
| **Mar** | Validación + batería 30 preguntas + corrección de carencias |
| **Mié-Jue** | Full CPT run (4×H200, ~6h por época) |
