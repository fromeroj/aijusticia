#!/usr/bin/env python3
"""infra/salud.py para CI: alerta UNA vez por conjunto de fallos.

Un monitor cada 30 min sobre una falla que dura horas manda decenas de correos
idénticos, y eso entrena a la gente a ignorarlos. Este wrapper conserva la
memoria de lo ya alertado y decide el exit code así:

  - hay fallos y el conjunto es DISTINTO del último alertado   → exit 1 (correo)
  - hay fallos, es el mismo conjunto y pasaron 12h del aviso   → exit 1 (recordatorio)
  - hay fallos, es el mismo conjunto y aún no pasan 12h        → exit 0 (el fallo
    queda impreso en el log; no se repite el correo)
  - sin fallos → exit 0 y se limpia la memoria

El conjunto de fallos incluye el detalle: un kill por OOM a una hora nueva es
un conjunto nuevo y vuelve a alertar de inmediato.

La memoria es un archivo JSON (--estado) que el workflow guarda y recupera de
la cache de Actions (ver .github/workflows/ci.yml).

Uso:
  python3 infra/salud_ci.py --estado .salud-alerta.json [--sin-ssh]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import salud  # noqa: E402

RECORDAR_CADA_H = 12


def decidir(fallos: list[str], previo: dict, ahora: float) -> tuple[dict, int, str]:
    """Devuelve (estado nuevo, exit code, motivo)."""
    if not fallos:
        return {}, 0, "sin fallos" + (" — se limpia la memoria de alertas" if previo else "")
    mismo = previo.get("fallos") == fallos
    if not mismo:
        return ({"fallos": fallos, "desde": ahora, "notificado": ahora}, 1,
                "conjunto de fallos NUEVO: se alerta")
    if ahora - previo.get("notificado", 0) >= RECORDAR_CADA_H * 3600:
        estado = dict(previo, notificado=ahora)
        return estado, 1, f"persiste desde hace {(ahora - previo.get('desde', ahora)) / 3600:.1f}h: recordatorio"
    estado = dict(previo)
    return estado, 0, (f"ya alertado hace {(ahora - previo.get('notificado', ahora)) / 3600:.1f}h: "
                       "no se repite el correo")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--estado", required=True, help="archivo JSON con la memoria de alertas")
    ap.add_argument("--sin-ssh", action="store_true")
    args = ap.parse_args()

    res = salud.correr(sin_ssh=args.sin_ssh or os.environ.get("SALUD_SIN_SSH") == "1")
    fallos = sorted(f"{r['check']}: {r['detalle']}" for r in res if r["estado"] == "fail")
    try:
        previo = json.load(open(args.estado, encoding="utf-8"))
        if not isinstance(previo, dict):
            previo = {}
    except (OSError, ValueError):
        previo = {}

    estado, codigo, motivo = decidir(fallos, previo, time.time())
    with open(args.estado, "w", encoding="utf-8") as f:
        json.dump(estado, f, ensure_ascii=False)
    print(f"\n[alertas] {motivo}" + (f" · exit {codigo}" if codigo else ""), flush=True)
    return codigo


if __name__ == "__main__":
    sys.exit(main())
