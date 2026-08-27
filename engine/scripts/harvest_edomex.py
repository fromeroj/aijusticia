#!/usr/bin/env python3
"""Harvesta TODAS las sentencias públicas del PJEdomex via su API elástica.

Fase 1: enumerar (materia × año) con paginacion -> manifiesto de PDFs
Fase 2: descargar PDFs (workers) + extraer texto -> JSONL

Corre en el server (ambos hosts accesibles). Uso:
  python3 harvest_edomex.py fase1
  python3 harvest_edomex.py fase2
"""
import concurrent.futures as cf
import io
import json
import sys
import time
import urllib.request
import ssl

BACK = "https://backgestiondocumental.pjedomex.gob.mx"
DIR = "/opt/aijusticia/corpus_downloads/edomex"
MANIFEST = f"{DIR}/manifest.jsonl"
JSONL = f"{DIR}/sentencias_edomex.jsonl"
ESTADO = f"{DIR}/estado_fase2.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

import os
os.makedirs(DIR, exist_ok=True)


def get_json(url):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return json.load(r)


def fase1():
    materias = get_json(f"{BACK}/materias")["data"]
    materias = [m for m in materias if m.get("enabled", True)]
    print(f"materias: {[m['name'] for m in materias]}", flush=True)
    anios = list(range(2026, 2013, -1))
    vistos = set()
    total_hits = 0

    def pagina(mat, anio, rango, out):
        """Pagina un slice (opcionalmente con startDate/endDate)."""
        frm, n = 0, 0
        while True:
            url = (f"{BACK}/files/search/elastic?search=juicio&typeSearch=match"
                   f"&typeDocument=sentencias&year={anio}&subject={mat['_id']}"
                   f"&size=500&from={frm}")
            if rango:
                url += f"&startDate={rango[0]}&endDate={rango[1]}"
            d = get_json(url)
            hits = d.get("data", {}).get("hits", {})
            hh = hits.get("hits", [])
            total = hits.get("total", {}).get("value", 0)
            gte = hits.get("total", {}).get("relation") == "gte"
            if not hh:
                return n, gte
            for h in hh:
                s0 = h.get("_source", {})
                ie = s0.get("infoElastic", {})
                pdf = ie.get("src") or ""
                if not pdf.lower().endswith(".pdf") or pdf in vistos:
                    continue
                vistos.add(pdf)
                out.write(json.dumps({
                    "materia": mat["name"], "anio": anio,
                    "number": ie.get("number"),
                    "fecha_reg": (ie.get("dates") or {}).get("registration", ""),
                    "name": s0.get("name", ""), "pdf": pdf,
                }, ensure_ascii=False) + "\n")
                n += 1
            frm += 500
            # tope elástico: este slice necesita sub-rebanado
            if gte and frm >= 10000:
                return n, True
            if frm >= total:
                return n, False
            time.sleep(0.4)

    TRIMESTRES = [("%s-01-01", "%s-03-31"), ("%s-04-01", "%s-06-30"),
                  ("%s-07-01", "%s-09-30"), ("%s-10-01", "%s-12-31")]
    with open(MANIFEST, "w") as out:
        for mat in materias:
            for anio in anios:
                n, gte = pagina(mat, anio, None, out)
                if gte:  # >10K: sub-rebanar por trimestre
                    n = 0
                    for a, b in TRIMESTRES:
                        nt, _ = pagina(mat, anio, (a % anio, b % anio), out)
                        n += nt
                if n:
                    print(f"  {mat['name']} {anio}: {n}", flush=True)
                total_hits += n
                out.flush()
    print(f"FASE1 COMPLETA: {total_hits} sentencias unicas en manifiesto", flush=True)


def procesar(item):
    pdf_url = item["pdf"]
    try:
        req = urllib.request.Request(pdf_url, headers=UA)
        with urllib.request.urlopen(req, timeout=120, context=CTX) as r:
            data = r.read()
        if data[:4] != b"%PDF" or len(data) > 40e6:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages)
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 400:
            return None
        return {
            "materia": item["materia"], "anio": item["anio"],
            "titulo": f"Sentencia {item.get('number') or ''} {item['materia']} {item['anio']} {item['name'][:80]}".strip(),
            "texto": texto, "paginas": len(rd.pages), "url": pdf_url,
        }
    except Exception:
        return None


def fase2():
    items = [json.loads(l) for l in open(MANIFEST)]
    hechos = set()
    if os.path.exists(ESTADO):
        hechos = set(json.loads(open(ESTADO).read()))
    print(f"manifiesto: {len(items)}, ya hechos: {len(hechos)}", flush=True)
    n = ok = 0
    with open(JSONL, "a") as out:
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            for item, res in zip(items, ex.map(procesar, items)):
                n += 1
                if item["pdf"] in hechos:
                    continue
                if res:
                    out.write(json.dumps(res, ensure_ascii=False) + "\n")
                    ok += 1
                hechos.add(item["pdf"])
                if n % 100 == 0:
                    out.flush()
                    open(ESTADO, "w").write(json.dumps(list(hechos)))
                    print(f"  {n}/{len(items)} ok={ok}", flush=True)
    open(ESTADO, "w").write(json.dumps(list(hechos)))
    print(f"FASE2 COMPLETA: {ok} sentencias con texto", flush=True)


if __name__ == "__main__":
    {"fase1": fase1, "fase2": fase2}[sys.argv[1]]()
