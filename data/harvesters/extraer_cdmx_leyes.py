#!/usr/bin/env python3
"""Extrae texto de las leyes CDMX descargadas y produce JSONL para ingesta.

Salida: engine/data/cdmx_leyes.jsonl con {titulo, tipo, texto, url, fecha}
"""
import json
import os
import re
import sys
from pathlib import Path

SRC = Path.home() / "workspace/aijusticia/engine/data/cdmx_leyes"
OUT = Path.home() / "workspace/aijusticia/engine/data/cdmx_leyes.jsonl"

TIPO = {"constitucion": "constitucion", "codigos": "codigo",
        "leyes": "ley", "reglamentos": "reglamento"}


def titulo_limpio(fname: str) -> str:
    stem = re.sub(r"\.(docx|pdf)$", "", fname, flags=re.I)
    stem = re.sub(r"[\d]+(\.[\d]+)?$", "", stem)  # version final
    stem = stem.replace("_", " ").strip()
    return stem[:250]


def fecha_de(fname: str):
    # versiones nuevas viven en 2025/2026/DDMMYY/ pero el nombre no la trae;
    # sin fecha fiable -> None (la GacetaBiblio no la requiere)
    return None


def extraer_docx(p: Path) -> str:
    import docx
    d = docx.Document(str(p))
    parts = [par.text for par in d.paragraphs if par.text.strip()]
    for t in d.tables:
        for row in t.rows:
            parts.append(" | ".join(c.text for c in row.cells))
    return "\n".join(parts)


def extraer_pdf(p: Path) -> str:
    from pypdf import PdfReader
    r = PdfReader(str(p))
    return "\n".join(pg.extract_text() or "" for pg in r.pages)


def main():
    n_ok = n_vacio = 0
    with open(OUT, "w") as out:
        for f in sorted(SRC.iterdir()):
            if f.suffix.lower() not in (".docx", ".pdf"):
                continue
            sec = f.name.split("__")[0]
            try:
                texto = extraer_docx(f) if f.suffix.lower() == ".docx" else extraer_pdf(f)
            except Exception as e:
                print(f"[ERR] {f.name}: {e}", file=sys.stderr)
                continue
            texto = texto.strip()
            if len(texto) < 300:
                n_vacio += 1
                print(f"[vacio] {f.name} ({len(texto)} chars)")
                continue
            rec = {
                "titulo": titulo_limpio(f.name),
                "tipo": TIPO.get(sec, "ley"),
                "texto": texto,
                "url": f"https://data.consejeria.cdmx.gob.mx/images/leyes/{f.name.split('__',1)[1]}",
                "archivo": f.name,
            }
            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n_ok += 1
    print(f"\nok={n_ok} vacios={n_vacio} -> {OUT}")


if __name__ == "__main__":
    main()
