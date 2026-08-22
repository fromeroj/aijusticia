"""
Sirve el modelo Qwen3.6 con el adapter LoRA v3 usando mlx_lm.server.

Esto levanta un servidor OpenAI-compatible (como LM Studio) pero con
el adapter LoRA cargado, para que el engine del AI Justicia use las
respuestas fine-tuned.

Uso:
    python -m scripts.serve_lora
    python -m scripts.serve_lora --port 1235  # puerto alternativo

Para usar en el engine:
    # .env
    LMSTUDIO_BASE_URL=http://localhost:1235/v1
"""
from __future__ import annotations
import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = os.environ.get(
    "AIJ_MODEL_PATH",
    os.path.expanduser("~/.lmstudio/models/mlx-community/Qwen3.6-35B-A3B-bf16"),
)
ADAPTER_PATH = str(ROOT / "data" / "lora_adapter_v3")


def main():
    ap = argparse.ArgumentParser(description="Servir modelo con LoRA adapter")
    ap.add_argument("--model", default=MODEL_PATH)
    ap.add_argument("--adapter", default=ADAPTER_PATH)
    ap.add_argument("--port", type=int, default=1235)
    ap.add_argument("--host", default="0.0.0.0")
    args = ap.parse_args()

    if not Path(args.adapter, "adapters.safetensors").exists():
        print(f"ERROR: Adapter no encontrado en {args.adapter}")
        sys.exit(1)

    print(f"Modelo: {args.model}")
    print(f"Adapter: {args.adapter}")
    print(f"Servidor: http://{args.host}:{args.port}/v1")
    print()

    # mlx_lm.server soporta --adapter-path
    cmd = [
        sys.executable, "-m", "mlx_lm", "server",
        "--model", args.model,
        "--adapter-path", args.adapter,
        "--port", str(args.port),
        "--host", args.host,
        "--trust-remote-code",
    ]
    print(f"Comando: {' '.join(cmd)}")
    subprocess.run(cmd)


if __name__ == "__main__":
    main()
