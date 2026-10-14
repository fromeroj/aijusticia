#!/usr/bin/env python3
"""Batería de evaluación del chat en producción — claves verificadas.

Corre las preguntas B/C contra el chat en vivo y califica:
  - texto de la respuesta contra patrones requeridos / prohibidos
  - títulos que DEBEN aparecer en el panel de leyes (pasajes del bibliotecario)
  - latencia y salud del stream (evento done, sin error)

Uso:
  python3 scripts/eval_bateria_prod.py                    # batería completa
  python3 scripts/eval_bateria_prod.py --solo B1,B3       # subconjunto
  python3 scripts/eval_bateria_prod.py --url http://127.0.0.1:8000
  python3 scripts/eval_bateria_prod.py --guardar          # guarda JSON en data/eval/

Claves construidas a partir del corpus (decretos verificados en la DB):
  B1 reforma jornada: DOF 03/03/2026 (const. 123 IV) + DOF 01/05/2026 (LFT 59)
     gradual: 2027→46h, 2028→44h, 2029→42h, 2030→40h (tabla en PDF, no en HTML)
  B2 reforma nacionalidad única: DOF 07/10/2026 (arts. 82, 116, 122)
  B3 decreto El Buen Fin: DOF 30/09/2026 (sorteo 13–17 nov 2026, acreditable ISR)
  B4 Órgano de Administración Judicial: reforma DOF 15/11/2024
  B5 Reglamento Ley de Infraestructura de la Calidad: DOF 04/09/2026
  B6 adiciones Reglamento LFDA: DOF 24/09/2026
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

URL_DEFAULT = "https://aijusticia.mx"

# ---- batería --------------------------------------------------------------
# cada caso: pregunta, patrones requeridos, patrones prohibidos,
#            títulos que deben salir en el panel de leyes (str in titulo, casefold)
CASOS = [
    {
        "id": "B1",
        "q": "¿Cuál es la jornada máxima de trabajo ahora, ya aplican las 40 horas?",
        "requiere_txt": [r"gradual|etapa|poco a poco|progresiv", r"40 horas|cuarenta horas"],
        "prohibe_txt": [r"sigue(n)? (siendo|vigente) 48", r"jornada (máxima |maxima )?(es|de) 48 horas",
                        r"8 de abril de 2025", r"finales de 2024", r"publicada en 2024|publicado en 2024"],
        "ley_panel": ["jornada"],
        "nota": "decreto LFT DOF 01/05/2026 debe salir en el panel; fechas 2024/2025 = alucinación",
    },
    {
        "id": "B2",
        "q": "¿Un gobernador puede tener doble nacionalidad?",
        "requiere_txt": [r"renunci|nacionalidad [uú]nica|art[íi]culo[s]? (82|116|122)|7 de octubre"],
        "prohibe_txt": [r"respuesta corta: s[ií]", r"s[ií],? un gobernador (mexicano )?(sí |si )?puede tener"],
        "ley_panel": ["82"],
        "nota": "decreto DOF 07/10/2026 (arts 82/116/122) en panel; el decreto fresco manda sobre art. 32 (1997)",
    },
    {
        "id": "B3",
        "q": "¿Hay algún estímulo por pagar con tarjeta de crédito este año?",
        "requiere_txt": [r"est[ií]mulo", r"buen fin|medios de pago electr|noviembre"],
        "prohibe_txt": [],
        "ley_panel": ["pago"],
        "nota": "decreto DOF 30/09/2026 (medios de pago electrónicos / El Buen Fin) en panel",
    },
    {
        "id": "B4",
        "q": "¿Quién administra el Poder Judicial federal ahora que ya no está el Consejo de la Judicatura?",
        "requiere_txt": [r"[ÓO]rgano de Administraci[oó]n Judicial"],
        "prohibe_txt": [r"(sigue|contin[uú]a|a[uú]n est[aá])[^.]{0,40}Consejo de la Judicatura"],
        "ley_panel": [],
        "nota": "reforma judicial DOF 15/11/2024",
    },
    {
        "id": "B5",
        "q": "¿Existe ya el reglamento de la Ley de Infraestructura de la Calidad?",
        "requiere_txt": [r"existe|s[ií]\b"],
        "prohibe_txt": [r"31 de marzo de 2023"],
        "ley_panel": [],
        "nota": "no inventar fecha (real: DOF 04/09/2026)",
    },
    {
        "id": "B6",
        "q": "¿Qué cambió en materia de derecho de autor en septiembre?",
        "requiere_txt": [r"derecho de autor"],
        "prohibe_txt": [],
        "ley_panel": ["derecho de autor"],
        "nota": "adiciones al Reglamento LFDA DOF 24/09/2026 deberían salir",
    },
    {
        "id": "C1",
        "q": "¿Qué regula el artículo 135 Bis de la Constitución?",
        "requiere_txt": [r"no (tengo|encuentro|consta|existe)|no tengo certeza|no existe"],
        "prohibe_txt": [],
        "ley_panel": [],
        "nota": "NO inventar contenido del 135 Bis",
    },
    {
        "id": "C2",
        "q": "Explícame la Ley General de Economía Colaborativa",
        "requiere_txt": [r"no me consta|no existe|no hay una ley|no tengo"],
        "prohibe_txt": [],
        "ley_panel": [],
        "nota": "aclarar inexistencia + marco real",
    },
]


def correr_q(url: str, pregunta: str, timeout: float = 150.0) -> dict:
    t0 = time.time()
    tokens: list[str] = []
    leyes: list[str] = []
    eventos = {"laws": 0, "done": 0, "error": 0, "reset": 0}
    ev = ""
    try:
        r = requests.post(f"{url}/chat/stream",
                          json={"consulta": pregunta, "historial": []},
                          stream=True, timeout=(10, timeout))
        for line in r.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event: "):
                ev = line[7:]
            elif line.startswith("data: "):
                data = line[6:]
                if ev in eventos:
                    eventos[ev] += 1
                if ev == "token":
                    try:
                        v = json.loads(data)
                        if isinstance(v, str):
                            tokens.append(v)
                    except Exception:
                        pass
                elif ev == "laws":
                    try:
                        p = json.loads(data)
                        leyes += [pas.get("titulo", "") or "" for pas in p.get("pasajes", [])]
                    except Exception:
                        pass
                elif ev == "error":
                    print(f"    [error-sse] {data[:120]}", flush=True)
    except Exception as e:
        return {"texto": "", "leyes": [], "eventos": eventos,
                "error": str(e)[:150], "segundos": round(time.time() - t0, 1)}
    return {"texto": "".join(tokens), "leyes": leyes, "eventos": eventos,
            "segundos": round(time.time() - t0, 1)}


def calificar(caso: dict, res: dict) -> dict:
    txt = res.get("texto", "")
    fallas, avisos = [], []

    for pat in caso["requiere_txt"]:
        if not re.search(pat, txt, re.I):
            fallas.append(f"falta patrón requerido: {pat}")
    for pat in caso["prohibe_txt"]:
        if re.search(pat, txt, re.I):
            fallas.append(f"aparece patrón prohibido: {pat}")
    for sub in caso["ley_panel"]:
        if not any(sub.lower() in t.lower() for t in res.get("leyes", [])):
            avisos.append(f"panel de leyes sin «{sub}»")
    if res.get("eventos", {}).get("error"):
        fallas.append("evento error en el stream")
    if not txt.strip():
        fallas.append("respuesta vacía")
    if len(txt) < 120:
        fallas.append(f"respuesta demasiado corta ({len(txt)} chars)")
    return {"ok": not fallas, "fallas": fallas, "avisos": avisos}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=URL_DEFAULT)
    ap.add_argument("--solo", default="", help="ids separados por coma, ej B1,B3")
    ap.add_argument("--guardar", action="store_true")
    args = ap.parse_args()

    casos = [c for c in CASOS if not args.solo or c["id"] in args.solo.split(",")]
    resultados = []
    ok_n = 0
    print(f"== Batería contra {args.url} — {len(casos)} casos ==\n", flush=True)
    for caso in casos:
        res = correr_q(args.url, caso["q"])
        ver = calificar(caso, res)
        ok_n += ver["ok"]
        marca = "PASS" if ver["ok"] else "FAIL"
        print(f"[{marca}] {caso['id']}  {res.get('segundos','?'):>6}s  chars={len(res.get('texto',''))}  "
              f"leyes={len(res.get('leyes', []))}", flush=True)
        for f in ver["fallas"]:
            print(f"    ✗ {f}", flush=True)
        for a in ver["avisos"]:
            print(f"    ⚠ {a}", flush=True)
        print(f"    >> {res.get('texto','')[:180].replace(chr(10), ' ')}", flush=True)
        resultados.append({"id": caso["id"], "q": caso["q"], **res, **ver})
        print(flush=True)

    print(f"== RESULTADO: {ok_n}/{len(casos)} ==", flush=True)
    if args.guardar:
        out = Path(__file__).resolve().parent.parent / "data" / "eval"
        out.mkdir(parents=True, exist_ok=True)
        p = out / f"bateria_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        p.write_text(json.dumps({"url": args.url, "ok": ok_n, "total": len(casos),
                                 "resultados": resultados}, ensure_ascii=False, indent=1))
        print(f"guardado: {p}", flush=True)


if __name__ == "__main__":
    main()
