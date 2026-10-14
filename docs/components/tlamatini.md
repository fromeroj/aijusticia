# Componente: Tlamatini (modelo legal open-weight)

**Qué es**: CPT (continued pre-training) de un base model abierto sobre el corpus
mexicano, para sustituir al LLM cloud con uno propio, exportable on-premise.
**Vive en**: `models/tlamatini/` (ex `tohil/`).

## Pipeline (Makefile: prep → smoke → eval → merge → export-gguf)
- `soup-*.yaml` — configs Soup CLI (QLoRA smoke / FSDP full).
- `merge_linear.py` — merge lineal post-CPT (mecanismo Thomson): `merged=(1−α)·base+α·cpt`.
- `eval_bateria.py` — batería de 30 preguntas ciudadanas para checkpoints.
- `data/prep/prep_cpt_completo.py` — arma el corpus de entrenamiento (universal + wikipedia + harness pairs).

## Contrato con producción
Mismo endpoint OpenAI-compatible que MiniMax. El día que un checkpoint gane el A/B
(`eval_bateria` vs MiniMax con `eval_bateria_prod`), el swap es una env var en 162.

## Pendiente (en orden)
1. Terminar limpieza + ingesta SIVEPJ (162) → 2. `prep_cpt_completo.py` **desde 162** →
3. smoke run → full CPT → 4. A/B con baterías → 5. swap si gana.
**Base prevista**: Qwen3.6-35B-A3B (MoE). Entrena en 66.154 o Mac; lee de 182 (archivo) o de un dump de 162.
