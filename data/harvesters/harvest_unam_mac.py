#!/usr/bin/env python3
"""Extracción masiva de tesis UNAM EN LA MAC (M-series, multiproceso).

El server (4 cores) se atraganta con pypdf; aquí usamos ProcessPool con
workers=P-core*0.6. Lee las fichas del server (36K URLs ya descubiertas),
baja los PDFs de tesiunamdocumentos.dgb.unam.mx y extrae el texto.
"""
import concurrent.futures as cf
import io
import json
import multiprocessing as mp
import os
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

DATA = Path.home() / "workspace/aijusticia/engine/data"
FICHAS = DATA / "unam_fichas_server.jsonl"
OUT = DATA / "unam_tesis_texto.jsonl"
ESTADO = DATA / "unam_estado_mac.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
N_WORKERS = max(4, int(os.environ.get("AIJ_WORKERS", "12")))


def procesar(rec):
    url = rec["pdf"]
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=180, context=CTX) as r:
            data = r.read()
        if data[:4] != b"%PDF" or len(data) > 80e6:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages[:600])
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 2000:
            return None
        return {"titulo": rec["titulo"], "texto": texto[:3_000_000],
                "paginas": len(rd.pages), "url": url}
    except Exception:
        return None


def main():
    recs = {}
    # fusionar fichas server + local (muestra mac previa)
    for fuente in (FICHAS, DATA / "unam_tesis_fichas.jsonl"):
        if fuente.exists():
            for l in open(fuente):
                r = json.loads(l)
                if r.get("pdf"):
                    recs[r["slug"]] = r
    hechos = set()
    if ESTADO.exists():
        hechos = set(json.loads(ESTADO.read_text()))
    pend = [r for s, r in recs.items() if s not in hechos]
    print(f"tesis con PDF: {len(recs)} | pendientes: {len(pend)} | workers: {N_WORKERS}", flush=True)
    n = ok = 0
    t0 = time.time()
    out = open(OUT, "a")
    with cf.ProcessPoolExecutor(max_workers=N_WORKERS) as ex:
        for rec, res in zip(pend, ex.map(procesar, pend, chunksize=4)):
            n += 1
            if res:
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                ok += 1
            hechos.add(rec["slug"])
            if n % 100 == 0:
                out.flush()
                ESTADO.write_text(json.dumps(list(hechos)))
                rate = n / (time.time() - t0) * 60
                print(f"  {n}/{len(pend)} ok={ok} ({rate:.0f}/min, ETA {(len(pend)-n)/max(rate,1)/60:.1f}h)", flush=True)
    out.flush()
    ESTADO.write_text(json.dumps(list(hechos)))
    print(f"FINAL: {ok}/{n} en {(time.time()-t0)/60:.0f} min", flush=True)


if __name__ == "__main__":
    main()
