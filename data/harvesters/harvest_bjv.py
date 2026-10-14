#!/usr/bin/env python3
"""Harvesta la Biblioteca Jurídica Virtual del IIJ-UNAM via OAI-PMH + bitstreams.

Corre EN EL SERVER (ru.juridicas accesible desde ahí). Uso:
  python3 harvest_bjv.py lista     -> recorre OAI y arma manifiesto
  python3 harvest_bjv.py descarga  -> baja PDFs y extrae texto a JSONL
"""
import io
import json
import os
import re
import ssl
import sys
import time
import urllib.request

BASE_OAI = "http://ru.juridicas.unam.mx/oai/request"
BASE_XMLUI = "http://ru.juridicas.unam.mx"
DIR = "/opt/aijusticia/corpus_downloads/bjv"
MANIFEST = f"{DIR}/manifest.jsonl"
JSONL = f"{DIR}/bjv_libros.jsonl"
ESTADO = f"{DIR}/estado.json"

SETS = {
    "col_123456789_8972": "Libros BJV",
    "col_123456789_14066": "Tesis",
    "col_123456789_57061": "1. Libros",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (compatible; AIEstudio/1.0)"}
os.makedirs(DIR, exist_ok=True)


def fetch(url, timeout=90):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def lista():
    vistos = set()
    try:
        vistos = {json.loads(l)["handle"] for l in open(MANIFEST)}
    except FileNotFoundError:
        open(MANIFEST, "w").close()
    with open(MANIFEST, "a") as out:
        for spec, nombre in SETS.items():
            token = None
            n = 0
            for _ in range(500):
                u = (f"{BASE_OAI}?verb=ListRecords&set={spec}&metadataPrefix=oai_dc"
                     if not token else f"{BASE_OAI}?verb=ListRecords&resumptionToken={token}")
                xml = fetch(u).decode("utf-8", "replace")
                for m in re.finditer(r"<record>(.*?)</record>", xml, re.S):
                    rec = m.group(1)
                    # el header OAI trae oai:ru.juridicas.unam.mx:123456789/N (fiable);
                    # dc:identifier puede ser ISBN
                    hdr = re.search(r"<identifier>oai:[^:]+:(\d+/\d+)</identifier>", rec)
                    title = re.search(r"<dc:title>([^<]+)</dc:title>", rec)
                    if not hdr:
                        continue
                    handle = f"{BASE_XMLUI}:80/xmlui/handle/{hdr.group(1)}"
                    if handle in vistos:
                        continue
                    vistos.add(handle)
                    out.write(json.dumps({
                        "handle": handle,
                        "titulo": title.group(1)[:300] if title else handle,
                        "coleccion": nombre,
                    }, ensure_ascii=False) + "\n")
                    n += 1
                rt = re.search(r"<resumptionToken[^>]*>\s*([^<]+?)\s*</resumptionToken>", xml)
                if not rt:
                    break
                token = rt.group(1)
                time.sleep(0.3)
            print(f"[{nombre}] +{n} (total {len(vistos)})", flush=True)


def bitstream_de(handle_url):
    html = fetch(handle_url, timeout=60).decode("utf-8", "replace")
    m = re.search(r'href="(/xmlui/bitstream/[^"]+?\.pdf[^"]*)"', html)
    if not m:
        return None
    return BASE_XMLUI + m.group(1).replace("&amp;", "&")


def procesa_item(it):
    """Devuelve el record JSONL o None."""
    try:
        pdf_url = bitstream_de(it["handle"])
        if not pdf_url:
            return None
        data = fetch(pdf_url, timeout=180)
        if data[:4] != b"%PDF" or len(data) < 20_000:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages[:800])
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 2000:
            return None
        return {
            "titulo": it["titulo"], "coleccion": it["coleccion"],
            "tipo": "libro" if "Libros" in it["coleccion"] else "tesis",
            "texto": texto[:4_000_000], "paginas": len(rd.pages),
            "url": it["handle"],
        }
    except Exception:
        return None


def descarga():
    import concurrent.futures as cf
    import threading
    items = [json.loads(l) for l in open(MANIFEST)]
    hechos = set()
    if os.path.exists(ESTADO):
        hechos = set(json.loads(open(ESTADO).read()))
    pendientes = [it for it in items if it["handle"] not in hechos]
    print(f"manifiesto: {len(items)}, pendientes: {len(pendientes)}", flush=True)
    lock = threading.Lock()
    n = ok = 0
    with open(JSONL, "a") as out:
        with cf.ThreadPoolExecutor(max_workers=4) as ex:
            for it, rec in zip(pendientes, ex.map(procesa_item, pendientes)):
                n += 1
                if rec:
                    with lock:
                        out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    ok += 1
                hechos.add(it["handle"])
                if n % 25 == 0:
                    out.flush()
                    open(ESTADO, "w").write(json.dumps(list(hechos)))
                    print(f"  {n}/{len(pendientes)} ok={ok}", flush=True)
    open(ESTADO, "w").write(json.dumps(list(hechos)))
    print(f"DESCARGA COMPLETA: ok={ok}", flush=True)


if __name__ == "__main__":
    {"lista": lista, "descarga": descarga}[sys.argv[1]]()
