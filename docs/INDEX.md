# Índice de Documentación — AI Justicia

> Actualizado: 14 octubre 2026. Estado de cada documento respecto a la realidad de producción.

## Leer primero

| Doc | Qué contiene | Estado |
|---|---|---|
| [`DEPLOYMENT.md`](../DEPLOYMENT.md) | **Operación de producción**: topología real (162 es producción, DB local 473K docs), deploys, cron DOF diario, crons, diagnóstico rápido, scripts de corpus | ✅ al día (14-oct) |
| [`arquitectura-corpus-rag.md`](arquitectura-corpus-rag.md) | DB, ingestion, retrieval (buscar_en_ley 2 fases + rama de recientes), chat 2-agentes, §8 estado 14-oct con números y deuda | ✅ al día (14-oct) |
| [`tlamatini-readiness.md`](tlamatini-readiness.md) | Preparación para el entrenamiento de Tlamatini (Soup, pasos) | ⚠️ vigente en método; re-exportar corpus desde **162** cuando termine la limpieza |

## Diseño por área (sept 2026 — mayormente vigentes)

| Doc | Área | Nota |
|---|---|---|
| [`arquitectura.md`](arquitectura.md) | Visión general del sistema | pre-rediseño del chat; ver §8 del corpus-rag para el chat nuevo |
| [`seguridad.md`](seguridad.md) | Amenazas y mitigaciones | vigente |
| [`autenticacion.md`](autenticacion.md) | Auth progresiva (anónimo→email→frase) | vigente (implementada: registro.py, migración 006) |
| [`integracion-nextcloud.md`](integracion-nextcloud.md) | Piloto Nextcloud/bufetes | vigente; el stack vive en Docker de la Mac (`aijusticia-pilot-*`) |
| [`spec-abogado-bufete.md`](spec-abogado-bufete.md) | Spec tier abogado/bufete | vigente |
| [`ui-spec-completa.md`](ui-spec-completa.md) | Spec UI | vigente salvo chat (rediseñado: Izel streaming) |
| [`harness-agente.md`](harness-agente.md) | Pares (aserto, artículo, ley) para CPT | vigente |
| [`reporte_portales_sentencias_32_estados.md`](reporte_portales_sentencias_32_estados.md) | Recon de los 32 portales judiciales | vigente como referencia de recon |

## Históricos (conservados como referencia del diseño inicial)

| Doc | Nota |
|---|---|
| `engine/ARCHITECTURE.md`, `engine/DATA_ACQUISITION.md`, `engine/README.md` | ⚠️ jul-2026: LoRA v5 local, embeddings nomic, DB vía túnel — **sustituidos** por los dos docs de "Leer primero" |
| [`CORPUS.md`](CORPUS.md), [`CORPUS_SCRAPING.md`](CORPUS_SCRAPING.md) | ago/jul-2026: cifras y procedimientos del corpus viejo (397K vía 182); la ingesta viva está descrita en DEPLOYMENT §5 y corpus-rag §8 |
| `docs/papers/thomson-1.0-small_model_card.md` | model card del experimento Thomson (histórico) |
| `docs/article-draft.md`, `docs/llm-articulo/` | borrador de artículo de difusión |
| `engine/data/lora_adapter*/TRAINING_NOTES.md` | notas de los LoRA históricos v1-v3 |

## Vivos fuera de docs/

- `tohil/README.md` — pipeline de entrenamiento Soup (Makefile: prep/smoke/eval/merge/export-gguf).
- `engine/scripts/eval_bateria_prod.py` — batería de evaluación contra producción (el "score" del asistente).
- `www/` — sitio tlamatini.live; `deck/` — pitch deck.

## Pendientes documentadas (14-oct)

- [ ] Re-medir batería sin carga concurrente (limpieza terminada)
- [ ] Sincronizar a 162 lo nuevo del harvest ordenjuridico de 66 (~1-2 días)
- [ ] 11 códigos de ley 404 en `LEYES_CLAVE`; Morelos casi vacío en OrdenJuridico
- [ ] NL/Jalisco/Coahuila: sentencias pendientes (ver corpus-rag §8.5)
