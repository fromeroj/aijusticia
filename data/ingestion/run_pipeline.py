"""Ejecuta una consulta end-to-end desde la línea de comandos.

Uso:
    python scripts/run_pipeline.py "¿Qué dice el artículo 14 sobre cargos no autorizados?"
    python scripts/run_pipeline.py "mi pregunta" --nivel Nivel1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.pipeline.orchestrator import ejecutar_consulta


def main() -> None:
    parser = argparse.ArgumentParser(description="Ejecuta el pipeline de AI Justicia")
    parser.add_argument("consulta", help="La consulta jurídica")
    parser.add_argument("--nivel", default="Nivel0", help="Nivel: Nivel0 | Nivel1 | Nivel2")
    parser.add_argument("--json", action="store_true", help="Salida en JSON completo")
    args = parser.parse_args()

    resultado = ejecutar_consulta(args.consulta, nivel=args.nivel)

    if args.json:
        print(json.dumps({
            "consulta": resultado.consulta,
            "abstenido": resultado.abstenido,
            "respuesta": resultado.respuesta,
            "analisis": resultado.analisis,
            "pasajes": resultado.pasajes,
            "verificacion": resultado.verificacion,
            "duracion_ms": resultado.duracion_ms,
            "traza_id": resultado.traza_id,
        }, ensure_ascii=False, indent=2))
        return

    # Salida legible
    print(f"\n{'='*70}")
    print(f"CONSULTA: {args.consulta}")
    print(f"{'='*70}\n")
    print(f"Materia: {resultado.analisis.get('materia', '—')}")
    print(f"Duración: {resultado.duracion_ms/1000:.1f}s | Traza ID: {resultado.traza_id}")
    print(f"\n{'─'*70}\nRESPUESTA ({'🟡 ABSTENCIÓN' if resultado.abstenido else '🟢 RESPONDER'}):\n{'─'*70}\n")
    print(resultado.respuesta)
    print(f"\n{'─'*70}\nVERIFICACIÓN:")
    v = resultado.verificacion
    print(f"  {v['n_sustentadas']}/{v['n_oraciones']} oraciones sustentadas ({v['ratio_sustento']:.0%})")
    print(f"  Pasajes usados:")
    for i, p in enumerate(resultado.pasajes, 1):
        vinc = "vinculante" if p["vinculante"] else "persuasiva"
        print(f"    [{i}] {p['fuente']} ({vinc}, score {p['score']}): {p['titulo'][:60]}")


if __name__ == "__main__":
    main()
