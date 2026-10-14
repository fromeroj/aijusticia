#!/usr/bin/env python3
"""Harvest MASIVO de tesis UNAM — 100% server, sin navegador, con workers.

Validado:
  GET /contenidos/ficha/<slug> (sin sesión) → HTML con URL del PDF
  GET <pdf_url> (redirect a tesiunamdocumentos.dgb.unam.mx) → PDF

Fase A: fichas (extraer URL de PDF por slug) — 8 workers
Fase B: PDFs (descargar + extraer texto) — 6 workers nice

Uso: python3 harvest_unam_server.py fichas|pdfs
"""
import concurrent.futures as cf
import io
import json
import re
import ssl
import sys
import time
import urllib.request

BASE = "https://repositorio.unam.mx"
DIR = "/opt/aijusticia/corpus_downloads/unam_tesis"
MANIFEST = "/opt/aijusticia/engine/data/unam_tesis_manifest.jsonl"
FICHAS = f"{DIR}/fichas.jsonl"
PDFS = f"{DIR}/tesis_texto.jsonl"
ESTADO_A = f"{DIR}/estado_fichas.json"
ESTADO_B = f"{DIR}/estado_pdfs.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

import os
os.makedirs(DIR, exist_ok=True)


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def procesar_ficha(slug):
    try:
        html = fetch(f"{BASE}/contenidos/ficha/{slug}").decode("utf-8", "replace")
        m = re.search(r"<title>([^<]{5,250})</title>", html)
        titulo = m.group(1).split(" - ")[0] if m else slug
        pdfs = re.findall(r'https?://[^"\'<>\s]{10,160}\.pdf', html)
        return {"slug": slug, "titulo": titulo[:300], "pdf": pdfs[0] if pdfs else None}
    except Exception as e:
        return {"slug": slug, "err": str(e)[:80], "pdf": None}


def fase_fichas():
    slugs = [json.loads(l)["slug"] for l in open(MANIFEST)]
    hechos = set()
    if os.path.exists(ESTADO_A):
        hechos = set(json.loads(open(ESTADO_A).read()))
    pend = [s for s in slugs if s not in hechos]
    print(f"fichas: {len(pend)} pendientes de {len(slugs)}", flush=True)
    n = ok = 0
    lock_write = open(FICHAS, "a")
    with cf.ThreadPoolExecutor(max_workers=8) as ex:
        for rec in ex.map(procesar_ficha, pend):
            n += 1
            lock_write.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if rec.get("pdf"):
                ok += 1
            hechos.add(rec["slug"])
            if n % 500 == 0:
                lock_write.flush()
                open(ESTADO_A, "w").write(json.dumps(list(hechos)))
                print(f"  {n}/{len(pend)} con_pdf={ok}", flush=True)
            time.sleep(0.05)
    lock_write.flush()
    open(ESTADO_A, "w").write(json.dumps(list(hechos)))
    print(f"FASE FICHAS COMPLETA: {ok} con PDF", flush=True)


def procesar_pdf(rec):
    try:
        data = fetch(rec["pdf"], timeout=180)
        if data[:4] != b"%PDF" or len(data) > 60e6:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages[:600])
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 2000:
            return None
        return {"titulo": rec["titulo"], "texto": texto[:3_000_000],
                "paginas": len(rd.pages), "url": rec["pdf"]}
    except Exception:
        return None


def fase_pdfs():
    recs = [json.loads(l) for l in open(FICHAS) if json.loads(l).get("pdf")]
    hechos = set()
    if os.path.exists(ESTADO_B):
        hechos = set(json.loads(open(ESTADO_B).read()))
    pend = [r for r in recs if r["pdf"] not in hechos]
    print(f"pdfs: {len(pend)} pendientes de {len(recs)}", flush=True)
    n = ok = 0
    out = open(PDFS, "a")
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        for rec, res in zip(pend, ex.map(procesar_pdf, pend)):
            n += 1
            if res:
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                ok += 1
            hechos.add(rec["pdf"])
            if n % 200 == 0:
                out.flush()
                open(ESTADO_B, "w").write(json.dumps(list(hechos)))
                print(f"  {n}/{len(pend)} ok={ok}", flush=True)
            time.sleep(0.1)
    out.flush()
    open(ESTADO_B, "w").write(json.dumps(list(hechos)))
    print(f"FASE PDFS COMPLETA: {ok} tesis con texto", flush=True)


if __name__ == "__main__":
    {"fichas": fase_fichas, "pdfs": fase_pdfs}[sys.argv[1]]()
