#!/usr/bin/env python3
"""Veracruz: Marco Juridico Vigente (SEGOB Ver) — leyes consolidadas pdf_ult/N.pdf.

CORRER EN LA MAC (segobver bloquea IPs extranjeras).
Salida: engine/data/leyes_veracruz.jsonl {titulo, tipo, texto, url, fecha_reforma}
"""
import io
import json
import re
import ssl
import time
import urllib.request
from html import unescape
from pathlib import Path

BASE = "https://www.segobver.gob.mx/juridico/"
OUT = Path.home() / "workspace/aijusticia/engine/data/leyes_veracruz.jsonl"
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

TIPO_MAP = {"CONSTITUCIÓN": "constitucion", "CÓDIGOS": "codigo", "CODIGOS": "codigo",
            "LEYES ORGÁNICAS": "ley-organica", "LEYES ORGANICAS": "ley-organica",
            "LEYES ORDINARIAS": "ley", "REGLAMENTOS": "reglamento"}


def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return r.read()


def main():
    html = fetch(BASE + "marco1.php").decode("utf-8", "replace")

    # secciones (card-header) para el tipo
    sections = []
    for m in re.finditer(r'<div class="card-header[^"]*">\s*([^<]+?)\s*</div>', html):
        sections.append((m.start(), unescape(m.group(1)).strip()))

    def tipo_en(pos):
        t = "ley"
        for sp, name in sections:
            if sp < pos and name.upper() in TIPO_MAP:
                t = TIPO_MAP[name.upper()]
        return t

    # filas: titulo en 2o td + link pdf_ult/N.pdf + fecha de reforma
    rows = []
    for m in re.finditer(
            r'<tr>\s*<td[^>]*>\s*\d+\s*</td>\s*<td[^>]*>(.*?)</td>.*?href="(pdf_ult/(\d+)\.pdf)"[^>]*>\s*([^<]*?)\s*</a>',
            html, re.S):
        titulo = unescape(re.sub(r"<[^>]+>", "", m.group(1))).strip()
        titulo = re.sub(r"\s+", " ", titulo)[:250]
        pdf, law_id = m.group(2), m.group(3)
        fecha_m = re.search(r"(\d{2}/\d{2}/\d{4})", m.group(4))
        fecha = fecha_m.group(1) if fecha_m else None
        if titulo and law_id:
            rows.append((titulo, pdf, law_id, fecha, tipo_en(m.start())))
    print(f"filas detectadas: {len(rows)}")

    ok = err = 0
    recs = []
    for titulo, pdf, law_id, fecha, tipo in rows:
        try:
            data = fetch(BASE + pdf)
            from pypdf import PdfReader
            r = PdfReader(io.BytesIO(data))
            texto = "\n".join(pg.extract_text() or "" for pg in r.pages)
            if len(texto) < 300:
                err += 1
                print(f"  [vacio] {titulo[:50]}")
                continue
            recs.append({"titulo": titulo, "tipo": tipo, "texto": texto,
                         "url": BASE + pdf, "fecha_reforma": fecha})
            ok += 1
            print(f"  [ok] {titulo[:55]} ({len(r.pages)}p)")
        except Exception as e:
            err += 1
            print(f"  [ERR] {titulo[:45]}: {str(e)[:60]}")
        time.sleep(0.35)

    with open(OUT, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ntok = sum(len(r["texto"]) for r in recs) // 4
    print(f"\nVeracruz: ok={ok} err={err} ~{ntok:,} tokens -> {OUT}")


if __name__ == "__main__":
    main()
