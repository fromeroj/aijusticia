#!/usr/bin/env python3
"""Descarga el orden jurídico consolidado de la CDMX (Consejería Jurídica).

CORRER EN LA MAC — data.consejeria.cdmx.gob.mx bloquea IPs extranjeras
(el server 182.255.84.124 no puede entrar). Luego se sube al server con scp.

Secciones: constitucion, codigos, leyes, reglamentos (con paginacion ?start=N).
Se baja .docx (mejor extraccion) y .pdf como respaldo.
"""
import os
import re
import sys
import time
import hashlib
import urllib.request
import ssl

BASE = "https://data.consejeria.cdmx.gob.mx"
DEST = os.path.expanduser("~/workspace/aijusticia/engine/data/cdmx_leyes")
SECCIONES = ["constitucion", "codigos", "leyes", "reglamentos"]
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE  # certificado gob.mx invalido

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=40, context=CTX) as r:
        return r.read()


def listar_docs(seccion: str):
    """Itera paginacion y produce (url_docx, url_pdf)."""
    docs, start = {}, 0
    while True:
        url = f"{BASE}/index.php/leyes/{seccion}?start={start}"
        try:
            html = fetch(url).decode("utf-8", "replace")
        except Exception as e:
            print(f"  [ERR] {url}: {e}", flush=True)
            break
        nuevos = 0
        for m in re.finditer(r'href="(/images/leyes/[^"]+?\.(docx|pdf))"', html, re.I):
            path = m.group(1)
            key = re.sub(r"\.(docx|pdf)$", "", path, flags=re.I).lower()
            docs.setdefault(key, {})[m.group(2).lower()] = path
            nuevos += 1
        print(f"  start={start}: {nuevos} links", flush=True)
        if nuevos == 0 or f"?start={start + 27}" not in html:
            break
        start += 27
        time.sleep(0.5)
    return docs


def main():
    os.makedirs(DEST, exist_ok=True)
    total_ok = total_err = 0
    for sec in SECCIONES:
        print(f"[{sec}]", flush=True)
        docs = listar_docs(sec)
        print(f"  -> {len(docs)} documentos unicos", flush=True)
        for key, variants in sorted(docs.items()):
            fname = os.path.basename(variants.get("docx") or variants["pdf"])
            out = os.path.join(DEST, sec + "__" + fname)
            if os.path.exists(out) and os.path.getsize(out) > 0:
                total_ok += 1
                continue
            url = BASE + (variants.get("docx") or variants["pdf"])
            try:
                data = fetch(url)
                with open(out, "wb") as f:
                    f.write(data)
                total_ok += 1
                print(f"  [ok] {fname} ({len(data)/1024:.0f}KB)", flush=True)
            except Exception as e:
                total_err += 1
                print(f"  [ERR] {fname}: {e}", flush=True)
            time.sleep(0.4)
    print(f"\nTOTAL: ok={total_ok} err={total_err} -> {DEST}", flush=True)


if __name__ == "__main__":
    sys.exit(main())
