"""
Fine-tuning LoRA del modelo base (Qwen3.6-35B-A3B) con datos de AI Justicia.

Convierte el dataset JSONL (formato instruction/output) al formato de chat
que mlx-lm espera, aplica LoRA a las capas lineales del modelo, y entrena.

Uso:
  python -m scripts.train_lora --data data/training --iters 500
  python -m scripts.train_lora --data data/training --iters 500 --resume
"""
from __future__ import annotations
import argparse
import json
import os
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "training"

# Modelo base
MODEL_PATH = os.environ.get(
    "AIJ_MODEL_PATH",
    os.path.expanduser("~/.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-bf16"),
)
ADAPTER_PATH = ROOT / "data" / "lora_adapter"

# Prompt de sistema (debe coincidir con prompts.py del engine)
SYSTEM_PROMPT = (
    "Eres AI Justicia, un asistente jurídico mexicano. Respondes preguntas de "
    "ciudadanos con base en la legislación mexicana vigente. Cita el artículo "
    "aplicable con [n]. Si no hay norma que responda, abstente. Tu orientación "
    "es estrictamente informativa, no sustituye la asesoría de un abogado."
)


def jsonl_to_chat(jsonl_path: Path, output_path: Path, max_examples: int = 0):
    """Convierte JSONL instruction/output → JSONL de chat para mlx-lm.

    Formato mlx-lm esperado:
    {"text": "<|im_start|>system\\n...\\n<|im_end|>\\n<|im_start|>user\\n...\\n<|im_end|>\\n<|im_start|>assistant\\n...\\n<|im_end|>"}
    o
    {"messages": [{"role": "system", ...}, {"role": "user", ...}, {"role": "assistant", ...}]}
    """
    examples = []
    with open(jsonl_path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            instruction = d.get("instruction") or d.get("question") or d.get("pregunta") or ""
            output = d.get("output") or d.get("answer") or d.get("respuesta") or ""
            if not instruction or not output or len(instruction) < 10 or len(output) < 20:
                continue
            # Limpiar: quitar [n] si no hay pasajes (para no confundir al modelo sin contexto)
            # En realidad conservamos [n] porque el modelo debe aprender a citar
            examples.append({
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": instruction.strip()},
                    {"role": "assistant", "content": output.strip()},
                ]
            })

    if max_examples > 0:
        random.shuffle(examples)
        examples = examples[:max_examples]

    with open(output_path, "w") as f:
        for ex in examples:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    return len(examples)


def prepare_dataset(data_dir: Path, max_examples: int = 0) -> tuple[int, int]:
    """Combina todos los JSONL del directorio en train/valid splits."""
    all_examples: list[dict] = []
    jsonl_files = sorted(data_dir.glob("*.jsonl"))

    # Filtrar archivos que son splits ya hechos
    source_files = [f for f in jsonl_files if f.stem not in ("train", "valid", "test")]

    for jf in source_files:
        n = jsonl_to_chat(jf, data_dir / f"_chat_{jf.name}", max_examples=0)
        print(f"  {jf.name}: {n} ejemplos")
        # Re-leer y acumular
        with open(data_dir / f"_chat_{jf.name}") as f:
            for line in f:
                all_examples.append(json.loads(line))
        # Limpiar temporal
        (data_dir / f"_chat_{jf.name}").unlink()

    print(f"\nTotal ejemplos combinados: {len(all_examples)}")

    if max_examples > 0:
        random.shuffle(all_examples)
        all_examples = all_examples[:max_examples]
        print(f"Limitando a {max_examples}")

    # Split: 95% train, 5% valid
    random.shuffle(all_examples)
    n_valid = max(10, len(all_examples) // 20)
    valid = all_examples[:n_valid]
    train = all_examples[n_valid:]

    with open(data_dir / "train.jsonl", "w") as f:
        for ex in train:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")
    with open(data_dir / "valid.jsonl", "w") as f:
        for ex in valid:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Train: {len(train)} | Valid: {len(valid)}")
    return len(train), len(valid)


def _volcar_dataset(conversaciones: list[dict], data_dir: Path) -> None:
    """Escribe conversaciones extraídas de la DB como JSONL de chat (train/valid)."""
    import random
    import json as _json
    random.seed(42)
    data_dir.mkdir(parents=True, exist_ok=True)
    ejemplos = []
    for c in conversaciones:
        if not c.get("pregunta") or not c.get("respuesta"):
            continue
        ejemplos.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": c["pregunta"]},
                {"role": "assistant", "content": c["respuesta"]},
            ]
        })
    random.shuffle(ejemplos)
    n_valid = max(5, len(ejemplos) // 20)
    with open(data_dir / "train.jsonl", "w") as f:
        for e in ejemplos[n_valid:]:
            f.write(_json.dumps(e, ensure_ascii=False) + "\n")
    with open(data_dir / "valid.jsonl", "w") as f:
        for e in ejemplos[:n_valid]:
            f.write(_json.dumps(e, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser(description="LoRA fine-tune del modelo base")
    ap.add_argument("--data", default=str(DATA), help="Directorio con JSONL")
    ap.add_argument("--model", default=MODEL_PATH, help="Ruta del modelo base")
    ap.add_argument("--adapter-path", default=str(ADAPTER_PATH), help="Donde guardar el adapter")
    ap.add_argument("--iters", type=int, default=500)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--learning-rate", type=float, default=1e-4)
    ap.add_argument("--num-layers", type=int, default=16, help="Capas a convertir a LoRA (de atrás hacia adelante)")
    ap.add_argument("--rank", type=int, default=16, help="Rank de LoRA")
    ap.add_argument("--scale", type=float, default=20.0, help="Scale de LoRA (alpha/rank)")
    ap.add_argument("--max-seq-length", type=int, default=4096)
    ap.add_argument("--grad-accumulation", type=int, default=4)
    ap.add_argument("--steps-per-report", type=int, default=10)
    ap.add_argument("--steps-per-eval", type=int, default=50)
    ap.add_argument("--save-every", type=int, default=100)
    ap.add_argument("--grad-checkpoint", action="store_true", default=True)
    ap.add_argument("--max-examples", type=int, default=0, help="0 = usar todos")
    ap.add_argument("--prepare-only", action="store_true", help="Solo preparar dataset, no entrenar")
    ap.add_argument("--resume", action="store_true", help="Continuar desde adapter existente")
    # ── Aislamiento de adapters por bufete ──
    # El adapter GENERAL se entrena SOLO con datos consentidos de ciudadanos.
    # Un adapter de BUFETE se entrena SOLO con los datos de ese bufete y
    # JAMÁS se mezcla con el general ni con otros bufetes.
    ap.add_argument("--bufete", type=str, default=None,
                    help="UUID del bufete: entrena su adapter PRIVADO con sus datos "
                         "(requiere que existan dossiers de ese bufete)")
    ap.add_argument("--extraer-consentidos", action="store_true",
                    help="Antes de entrenar, extraer conversaciones CON consentimiento "
                         "de la DB al dataset (solo adapter general)")
    args = ap.parse_args()

    data_dir = Path(args.data)

    if args.bufete:
        # Adapter privado del bufete: dataset aislado, ruta separada
        import uuid as _uuid
        bufete_id = _uuid.UUID(args.bufete)
        adapter_path = Path(f"data/adapters_bufetes/{args.bufete}") 
        adapter_path.mkdir(parents=True, exist_ok=True)
        from ai_justicia.dossiers.store import extraer_dataset_bufete
        conversaciones = extraer_dataset_bufete(bufete_id)
        if not conversaciones:
            print(f"✗ El bufete {args.bufete} no tiene conversaciones; nada que entrenar")
            return
        _volcar_dataset(conversaciones, data_dir)
        print(f"⚡ ADAPTER PRIVADO bufete={args.bufete}: {len(conversaciones)} conversaciones (aisladas)")
    elif args.extraer_consentidos:
        # Adapter general: SOLO dossiers con consentimiento explícito otorgado
        from ai_justicia.dossiers.store import extraer_dataset_general
        conversaciones = extraer_dataset_general()
        if conversaciones:
            _volcar_dataset(conversaciones, data_dir)
            print(f"✓ Dataset general: {len(conversaciones)} conversaciones CON consentimiento")
        else:
            print("⚠ Sin conversaciones consentidas aún; usando dataset existente")
        adapter_path = Path(args.adapter_path)
        adapter_path.mkdir(parents=True, exist_ok=True)
    else:
        adapter_path = Path(args.adapter_path)
        adapter_path.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("AI Justicia - LoRA Fine-tune")
    print("=" * 60)
    print(f"Modelo base: {args.model}")
    print(f"Adapter: {adapter_path} {'[PRIVADO BUFETE]' if args.bufete else '[GENERAL]'}")
    print(f"Iters: {args.iters} | Batch: {args.batch_size} | LR: {args.learning_rate}")
    print(f"LoRA: rank={args.rank}, scale={args.scale}, layers={args.num_layers}")
    print()

    # Preparar dataset
    if not (data_dir / "train.jsonl").exists() or args.max_examples > 0:
        print("Preparando dataset...")
        n_train, n_valid = prepare_dataset(data_dir, args.max_examples)
    else:
        # Contar existentes
        with open(data_dir / "train.jsonl") as f:
            n_train = sum(1 for _ in f)
        with open(data_dir / "valid.jsonl") as f:
            n_valid = sum(1 for _ in f)
        print(f"Dataset existente: Train: {n_train} | Valid: {n_valid}")

    if args.prepare_only:
        return

    # Escribir config YAML para mlx-lm
    config = {
        # The data processing parameters
        "data": {
            "path": str(data_dir),
            "valid_split": 0.0,  # ya tenemos valid.jsonl
            "use_user_format": True,
        },
        # The model parameters
        "model": args.model,
        # The training parameters
        "train": True,
        "fine_tune_type": "lora",
        "num_layers": args.num_layers,
        "batch_size": args.batch_size,
        "iters": args.iters,
        "learning_rate": args.learning_rate,
        "steps_per_report": args.steps_per_report,
        "steps_per_eval": args.steps_per_eval,
        "grad_accumulation_steps": args.grad_accumulation,
        "save_every": args.save_every,
        "adapter_path": str(adapter_path),
        "max_seq_length": args.max_seq_length,
        "grad_checkpoint": args.grad_checkpoint,
        # LoRA keys para arquitectura híbrida Qwen3.6 (self_attn + linear_attn + shared_expert)
        "lora_parameters": {
            "rank": args.rank,
            "scale": args.scale,
            "dropout": 0.05,
            "keys": [
                # Self-attention estándar (capas 0,8,16,24,32,39)
                "self_attn.q_proj",
                "self_attn.k_proj",
                "self_attn.v_proj",
                "self_attn.o_proj",
                # Linear attention / GatedDeltaNet (mayoría de capas)
                "linear_attn.in_proj_a",
                "linear_attn.in_proj_b",
                "linear_attn.in_proj_z",
                "linear_attn.in_proj_qkv",
                "linear_attn.out_proj",
                # Shared expert (NO switch_mlp — 256 experts son demasiados)
                "mlp.shared_expert.up_proj",
                "mlp.shared_expert.down_proj",
                "mlp.shared_expert.gate_proj",
            ],
        },
        # Seed
        "seed": 42,
    }

    config_path = adapter_path / "config.yaml"
    import yaml
    with open(config_path, "w") as f:
        yaml.dump(config, f, default_flow_style=False)
    print(f"\nConfig escrito: {config_path}")

    # Lanzar mlx_lm.lora via subprocess para mejor manejo de memoria
    import subprocess
    cmd = [
        sys.executable, "-m", "mlx_lm", "lora",
        "--config", str(config_path),
    ]
    print(f"\nLanzando: {' '.join(cmd)}\n")
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
