# AI Justicia — Motor LLM + RAG

Motor de IA jurídica mexicana: LLM destilado + RAG con verificación de citas.

Tres capas (según el plan del proyecto):
1. **Conocimiento (RAG)** — corpus oficial mexicano con índice híbrido BM25 + vectorial
2. **Razonamiento (LLM)** — Qwen3.6-35B-A3B servido vía LM Studio
3. **Garantías (verificación)** — resolvedor de citas contra registros reales + prueba de implicación (NLI)

## Requisitos

- Python 3.12+
- Docker (para PostgreSQL + pgvector)
- **LM Studio** corriendo en `http://localhost:1234/v1` con:
  - `qwen3.6-35b-a3b` (LLM)
  - `text-embedding-nomic-embed-text-v1.5` (embeddings)
- (Opcional) Tesseract para OCR: `brew install tesseract`

## Instalación

```bash
cd engine
cp .env.example .env          # ajusta si hace falta
docker compose up -d           # levanta Postgres + pgvector en :5433
pip install -e ".[dev]"        # instala el paquete en modo desarrollo
python scripts/setup_db.py     # crea el esquema de la DB
```

## Verificación rápida

```bash
# Comprobar conexión con LM Studio
python -c "from ai_justicia.llm.client import check_connection; print(check_connection())"

# Ejecutar una consulta end-to-end (tras ingesta del corpus)
python scripts/run_pipeline.py "¿Qué dice el artículo 14 sobre cargos no autorizados?"
```

## Estructura

Ver `pyproject.toml` y el directorio `ai_justicia/`. Documentación completa en
`/docs/Plataforma_IA_Legal_Mexico_Plan_Reestructurado.docx`, sección 7.

## Fine-tuning (LoRA)

El modelo base (Qwen3.6-35B-A3B) se fine-tunea con LoRA para especializarlo
en respuestas jurídicas mexicanas con citas de artículos específicos.

### Dataset
- **3,848 ejemplos sintéticos** generados desde leyes federales (LFT, CC, CPF, etc.)
- **998 ejemplos boost** de materias subrepresentadas (Laboral, Civil, Penal)
- **247 ejemplos reales** del foro de justiciamexico.mx
- Total: ~5,093 ejemplos (2,288 únicos tras dedup)

### Pipeline
```bash
# 1. Generar ejemplos sintéticos desde el corpus
python scripts/generate_synthetic_v2.py --count 5000

# 2. Boost de materias subrepresentadas (opcional)
python scripts/generate_synthetic_v2.py --count 1000 --output data/training/synthetic_boost.jsonl

# 3. Consolidar dataset (filtros + <think> prefix + splits)
python -c "
import json, re
# Ver scripts/process_questions.py para pipeline completo
"

# 4. Entrenar LoRA
python scripts/train_lora.py --iters 400

# O directamente con mlx_lm:
python -m mlx_lm lora --config data/lora_adapter_v3/config.yaml
```

### Resultados (v3, 2026-07-28)
- **Val loss**: 3.789 → 0.921 (76% reducción)
- **Adapter size**: 32 MB
- **Trainable params**: 8.5M (0.024%)
- **Memoria pico**: 76 GB (modelo + gradientes + optimizer state)

### Notas importantes
1. **Formato `<think>`**: El modelo Qwen3.6 es de razonamiento. El training data
   DEBE incluir `<think>\n\n</think>\n\n` al inicio de cada respuesta de assistant
   para coincidir con el modo `enable_thinking=False`.
2. **Claves LoRA**: La arquitectura híbrida (self_attn cada 8 capas + GatedDeltaNet)
   requiere claves específicas: `self_attn.{q,k,v,o}_proj`, `linear_attn.in_proj_*`,
   `mlp.shared_expert.*`. NO usar `switch_mlp` (256 experts = demasiado).
3. **Filtrado de basura**: Filtrar chunks con firmas, promulgaciones, tablas
   (regex: Rúbrica, Salinas de Gortari, D.O., etc.)

### Uso del adapter
```python
import mlx_lm
model, tokenizer = mlx_lm.load(
    "~/.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-bf16",
    adapter_path="data/lora_adapter_v3/adapters.safetensors"
)
# Generar con thinking deshabilitado
prompt = tokenizer.apply_chat_template(
    messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
)
response = mlx_lm.generate(model, tokenizer, prompt=prompt, max_tokens=400)
```
