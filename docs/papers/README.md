# Papers de referencia — AI Justicia

Papers que fundamentan la estrategia de entrenamiento del modelo.
Ordenados por relevancia para nuestro roadmap (CPT-LoRA por capas).

## Estrategia del modelo (leer en este orden)

### 1. Thomson-1.0-Small — model card (2026)
**Archivo**: `thomson-1.0-small_model-card.md`
**URL**: https://huggingface.co/thomsonreuters/Thomson-1.0-Small
**Por qué importa**: Thomson Reuters construyó su modelo legal profesional
sobre **nuestra misma base** (Qwen3.6-35B-A3B). Valida la arquitectura y
demuestra el valor del CPT legal: LegalBench 79.9 vs 71.7 del base.
Su receta: CPT con **model merging anti-olvido** + Constitutional DPO +
datos con ontología IRAC + replay general.
⚠ Licencia PolyForm Strict — solo referencia, NO usable en producción.

### 2. SaulLM-7B: A pioneering LLM for Law (2024)
**Archivo**: `saullm-7b-pioneering-llm-for-law.pdf` | arXiv 2403.03883
**Por qué importa**: LA receta que seguimos. Mistral-7B + CPT sobre 30B
tokens legales + IFT con instruct sintético. Técnicas de limpieza de corpus
que ya adoptamos (NFKC, filtro perplejidad, dedup, 10-gramas). MIT.

### 3. SaulLM-54B & 141B: Scaling domain-specific (2024)
**Archivo**: `saullm-scaling-up-domain-specific-models.pdf` | arXiv 2407.19584
**Por qué importa**: El escalado de la receta: CPT (520B tokens) → IFT → DPO.
Hallazgo clave para nosotros: ~5% de datos de matemáticas/código en el mix
evita la regresión deductiva. El +7% del CPT se conserva tras IFT+DPO.

### 4. MultiLegalPile: 689GB corpus multilingüe (ACL 2024)
**Archivo**: `multilegalpile-689gb-multilingual-legal-corpus.pdf` | arXiv 2306.02069
**Dataset**: https://huggingface.co/datasets/joelniklaus/Multi_Legal_Pile
**Por qué importa**: El corpus abierto que SaulLM cita. Tiene subconjunto
**español** (Eurlex-es + Legal-MC4-es) que usaremos en nuestra Capa 1
(CPT-LoRA). Es derecho español/europeo, no mexicano — sirve para lenguaje
jurídico, no para derecho vigente en MX.

### 5. MEL: Legal Spanish LM (2025)
**Archivo**: `mel-spanish-legal-language-model.pdf` | arXiv 2501.16011
**Por qué importa**: Precedente directo de LM legal en español. Sus fuentes
y evaluaciones en español guían qué esperar de un CPT en nuestro idioma.

## Técnicas del entrenamiento continuo

### 6. TIES-Merging: model merging anti-forgetting (NeurIPS 2023)
**Archivo**: `model-merging-safetensors-ties.pdf` | arXiv 2306.01708
**Por qué importa**: La técnica de merging que usa Thomson para CPT sin
olvido catastrófico. Aplicable cuando fusionemos CPT-LoRA → base
(`mlx_lm.fuse` con selección de deltas).

### 7. Continual Pretraining of LLMs: survey (2024)
**Archivo**: `continual-pretraining-llms-survey.pdf` | arXiv 2402.01361
**Por qué importa**: Panorama de métodos anti-olvido (replay, EWC, merging).
Base teórica para nuestro ciclo mensual de CPT incremental sobre DOF/SJF
nuevos con replay del 10% de datos viejos.

## Cómo se conectan con nuestro plan

```
Capa 1 (CPT-LoRA fundación):  papers 2, 3 (receta) + 4, 5 (corpus es) + 6, 7 (anti-olvido)
Capa 2 (SFT):                 papers 2, 3 (IFT/DPO) — ya implementado (LoRA v5)
Benchmark meta:               paper 1 (Thomson: 79.9 LegalBench en nuestra misma base)
```
