#!/usr/bin/env python3
"""Merge lineal post-CPT: mezcla los pesos del modelo CPT con el base.

Mecanismo Thomson-1.0: `merged = (1-α) * base + α * cpt_model`
α controla cuánto del conocimiento nuevo entra. Empieza en 0.5 y ajusta.

Uso:
  python3 merge_linear.py --base Qwen/Qwen3-30B-A3B \
                          --cpt ./output_tlamatini_v1 \
                          --alpha 0.5 \
                          --output ./tlamatini_v1_merged
"""
import argparse
import shutil
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer


def merge_linear(base_path: str, cpt_path: str, alpha: float, output: str):
    print(f"Cargando base: {base_path}")
    model_base = AutoModelForCausalLM.from_pretrained(base_path, torch_dtype=torch.bfloat16)
    print(f"Cargando CPT: {cpt_path}")
    model_cpt = AutoModelForCausalLM.from_pretrained(cpt_path, torch_dtype=torch.bfloat16)

    print(f"Merging con α={alpha}...")
    base_params = dict(model_base.named_parameters())
    cpt_params = dict(model_cpt.named_parameters())

    for name in base_params:
        if name in cpt_params:
            base_params[name].data.mul_(1 - alpha).add_(cpt_params[name].data, alpha=alpha)
        else:
            print(f"  WARN: {name} solo en base")

    print(f"Guardando merged → {output}")
    model_base.save_pretrained(output)
    tok = AutoTokenizer.from_pretrained(base_path)
    tok.save_pretrained(output)
    print("OK")


if __name__ == "__main__":
    import fire
    fire.Fire(merge_linear)
