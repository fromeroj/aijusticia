#!/usr/bin/env python3
"""Harvest MASIVO de tesis UNAM — server, sin navegador.

Descubierto: los PDFs viven en tesiunamdocumentos.dgb.unam.mx con ruta
ptd<YYYY>/<mes>/<id>/<id>.pdf — pero el id NO es derivable del slug.
Fase A (este script, en la Mac con Playwright): abrir fichas y extraer URLs.
Alternativa rápida: si el manifiesto de fichas ya tiene URLs para un patron,
la descarga directa corre en el server.

Optimizacion clave: probar GET directo de la ficha SIN sesion en el server
(el HTML de resultados ya vino server-rendered alguna vez; la ficha puede
ser igual). Si funciona, todo el pipeline corre en el server con curl.
"""
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

BASE = "https://repositorio.unam.mx"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

def fetch(url, timeout=60):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def probar_ficha_directa():
    """¿La ficha sirve HTML útil sin sesión de navegador?"""
    slugs = [json.loads(l)["slug"] for l in open("/opt/aijusticia/engine/data/unam_tesis_manifest.jsonl")][:5] \
        if Path("/opt/aijusticia/engine/data/unam_tesis_manifest.jsonl").exists() else []
    if not slugs:
        # desde el jsonl de fichas ya recolectado
        return "sin manifiesto en server"
    for slug in slugs[:3]:
        try:
            html = fetch(f"{BASE}/contenidos/ficha/{slug}").decode("utf-8", "replace")
            pdfs = re.findall(r'https?://[^"\'>\s]{10,150}\.pdf[^"\'>\s]*', html)
            print(f"{slug[:40]}: len={len(html)} pdfs={len(pdfs)} {pdfs[:1]}")
        except Exception as e:
            print(f"{slug[:40]}: ERR {str(e)[:60]}")
    return "done"


if __name__ == "__main__":
    print(probar_ficha_directa())
