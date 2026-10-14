# Tohil — el forjo de Tlamatini

Pipeline de entrenamiento de Tlamatini, el modelo base soberano de derecho
mexicano. Basado en **Soup CLI** (Apache-2.0) — un config, un comando.

## Diseño experimental (v1)

Tres brazos sobre el mismo corpus mexicano (`derecho_mx.jsonl`):

| Brazo | Config | Qué mide |
|---|---|---|
| **Base** | Qwen3-30B-A3B sin tocar | línea base de alucinación |
| **Control LoRA** | `soup-tlamatini-smoke.yaml` (LoRA r64 + QLoRA) | cuánto aporta CPT vía adapters |
| **Full CPT** | `soup-tlamatini-full.yaml` (full-parameter, FSDP) | la receta Thomson: strong CPT |

Post-CPT del brazo full: **merge lineal con el base** (α ≈ 0.5–0.7,
mecanismo anti-olvido de Thomson) → cuarta variante evaluada.

## Evaluación

La batería de 30 preguntas ciudadanas (tasa de respuesta, precisión de
citas a nivel artículo) + QA de leyes con sensibilidad a reformas +
calibración de abstención. Todos los brazos + base, mismos prompts.

## Datasets

- `data/derecho_mx.jsonl` — corpus mexicano (export CPT, plaintext)
- `data/harness_mx.jsonl` — pares (pasaje de ley + pregunta → respuesta
  anclada [n]) minados de sentencias del corpus
- `data/harness_pairs.jsonl` — pares instructivos ingleses (FreeLaw)
- Replay general 2-5%: Wikipedia es + código + instruct

## Smoke test ( lunes)

1. Vast.ai → instancia 4×H200 (o 2×H100 para el smoke con QLoRA)
2. `pip install "soup-cli[train,deepspeed]"`
3. `soup train --config soup-tlamatini-smoke.yaml`
4. Validar: loss baja, checkpoint guarda, merge corre, GGUF exporta
5. `soup doctor` si algo falla

## Corrida real (v1)

`soup train --config soup-tlamatini-full.yaml` en 4×H200 con FSDP.
Post-CPT: merge lineal → evaluación de los 4 brazos → Tlamatini v1.
