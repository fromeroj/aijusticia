#!/usr/bin/env python3
"""Descarga el archivo histórico de la Gaceta Oficial CDMX/DF via Wayback Machine.

El buscador oficial (app ZK) resiste automatización; Wayback tiene 2,409 PDFs
archivados (portal_old/uploads/gacetas/<hash>.pdf). Se intenta el URL vivo
primero (desde la Mac, IP mexicana) y se cae a la copia de archive.org.

Salida: engine/data/gaceta_cdmx_pdfs/ + gaceta_cdmx.jsonl (texto extraido)
"""
import concurrent.futures as cf
import io
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

OUT_DIR = Path.home() / "workspace/aijusticia/engine/data/gaceta_cdmx_pdfs"
JSONL = Path.home() / "workspace/aijusticia/engine/data/gaceta_cdmx.jsonl"
CDX = Path("/tmp/cdx_gacetas_full.txt")

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}


def fetch(url, timeout=75):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def pdf_text(data):
    from pypdf import PdfReader
    try:
        r = PdfReader(io.BytesIO(data))
        return "\n".join(pg.extract_text() or "" for pg in r.pages), len(r.pages)
    except Exception:
        return "", 0


def metadata(texto):
    """Extrae numero y fecha de la primera pagina de la gaceta."""
    cab = texto[:3000]
    num = re.search(r"N[uú]m(?:ero)?\.?\s*([0-9]{1,5})", cab, re.I)
    fecha = re.search(r"(\d{1,2}\s+de\s+[a-zá-ú]+\.?\s+de\s+\d{4})", cab, re.I)
    return (num.group(1) if num else None), (fecha.group(1) if fecha else None)


def procesar(item):
    url, ts, _ = item
    m = re.search(r"gacetas[^/]*?/?([A-Fa-f0-9]{8,})\.pdf", url)
    if not m:
        return ("err", "?", f"url rara: {url[:60]}", 0)
    h = m.group(1)
    out_pdf = OUT_DIR / f"{h}.pdf"
    if out_pdf.exists() and out_pdf.stat().st_size > 10000:
        data = out_pdf.read_bytes()
    else:
        data = None
        try:
            data = fetch(url)  # vivo
        except Exception:
            try:
                data = fetch(f"https://web.archive.org/web/{ts}id_/{url}")
            except Exception as e:
                return ("err", h, str(e)[:60], 0)
        if not data or data[:4] != b"%PDF":
            try:
                data = fetch(f"https://web.archive.org/web/{ts}id_/{url}")
            except Exception as e:
                return ("err", h, str(e)[:60], 0)
        if not data or data[:4] != b"%PDF":
            return ("err", h, "no pdf", 0)
        out_pdf.write_bytes(data)
    texto, npag = pdf_text(data)
    # pypdf a veces produce sustitutos huerfanos que rompen json.dumps
    texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
    if len(texto) < 500:
        return ("vacio", h, f"{npag}p", 0)
    num, fecha = metadata(texto)
    titulo = f"Gaceta Oficial CDMX{f' No. {num}' if num else ''}{f' ({fecha})' if fecha else ''}"
    return ("ok", h, titulo, len(texto), texto, npag, url)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items = []
    for line in CDX.read_text().splitlines():
        m = re.match(r"(\S+)\s+(\d{14})\s+(\d+)", line.strip())
        if m and m.group(3) == "200" and m.group(1).endswith(".pdf"):
            items.append((m.group(1), m.group(2), m.group(3)))
    print(f"a descargar: {len(items)} PDFs", flush=True)

    # resume: ya procesados en corridas previas
    hecho_path = OUT_DIR / ".hechos"
    hechos = set(hecho_path.read_text().split()) if hecho_path.exists() else set()
    items = [it for it in items
             if re.search(r"gacetas[^/]*?/?([A-Fa-f0-9]{8,})\.pdf", it[0]) is None
             or re.search(r"gacetas[^/]*?/?([A-Fa-f0-9]{8,})\.pdf", it[0]).group(1) not in hechos]
    print(f"pendientes tras resume: {len(items)}", flush=True)

    ok = err = vacio = 0
    with open(JSONL, "a") as out, open(hecho_path, "a") as hecho_f, cf.ThreadPoolExecutor(max_workers=4) as ex:
        for i, res in enumerate(ex.map(procesar, items), 1):
            if res[0] == "ok":
                _, h, titulo, nch, texto, npag, url = res
                out.write(json.dumps({
                    "titulo": titulo, "tipo": "gaceta", "texto": texto,
                    "url": url, "hash": h, "paginas": npag,
                }, ensure_ascii=False) + "\n")
                hecho_f.write(h + "\n")
                ok += 1
            elif res[0] == "vacio":
                vacio += 1
            else:
                err += 1
            if i % 50 == 0:
                print(f"  {i}/{len(items)} ok={ok} vacio={vacio} err={err}", flush=True)
                out.flush()
    print(f"\nFINAL: ok={ok} vacio={vacio} err={err} -> {JSONL}", flush=True)


if __name__ == "__main__":
    main()
