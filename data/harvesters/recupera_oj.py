#!/usr/bin/env python3
"""Recupera los rechazos del harvest OrdenJurídico en 66.

Los 'err' del harvest son archivos .doc que en realidad son Word 2007+ (OOXML):
antiword no los lee. Este script re-descubre títulos/estados del listing,
extrae con el formato correcto, upsertea y borra el archivo. Idempotente.

Uso (en 66): setsid nohup .venv/bin/python scripts/harvesters/recupera_oj.py \
  > /var/log/aijusticia_recupera_oj.log 2>&1 < /dev/null &
"""
import json
import re
import subprocess
import sys
import time
import zipfile
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

BASE = "https://ordenjuridico.gob.mx"
FILES = Path("/opt/aijusticia/corpus_downloads/ordenjuridico/files")
ESTADO = Path("/opt/aijusticia/corpus_downloads/ordenjuridico/estado.json")
MIN_CHARS = 200

_FICHA_RE = re.compile(
    r'href\s*=\s*javascript:void\(window\.open\("fichaOrdenamiento\.php\?idArchivo=(\d+)&ambito=estatal')
_TITULO_RE = re.compile(r">\s*([^<>]{10,300}?)\s*</a>", re.I)

DOCX_BODY = re.compile(r"<w:body[ >].*</w:body>", re.S)
XML_TAG = re.compile(r"<[^>]+>")


def titulo_map() -> dict:
    """id_archivo → (título, estado_str) desde los 32 listados."""
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {}
    ent_por_id = est.get("entidades", {})
    s = creq.Session(impersonate="chrome", timeout=60, headers={"Referer": BASE})
    s.get(f"{BASE}/", timeout=30)
    time.sleep(1)
    mapa = {}
    for edo in range(1, 33):
        try:
            t = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0",
                      timeout=60).content.decode("windows-1252", errors="replace")
            if "incap_ses" in t or "Loading" in t[:3000]:
                s.get(f"{BASE}/", timeout=30)
                time.sleep(3)
                t = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0",
                          timeout=60).content.decode("windows-1252", errors="replace")
        except Exception as e:
            print(f"edo {edo}: red {str(e)[:50]}", flush=True)
            continue
        for m in _FICHA_RE.finditer(t):
            seg = t[m.end(): m.end() + 400]
            mt = _TITULO_RE.search(seg)
            if mt:
                titulo = re.sub(r"\s+", " ", mt.group(1)).strip()
                ent = ent_por_id.get(m.group(1))
                mapa[m.group(1)] = (titulo, ent) if ent else titulo
    return mapa


def extraer(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", errors="replace")
    if suf == ".rtf":
        r = subprocess.run(["unrtf", "--text", str(path)], capture_output=True, timeout=120)
        return re.sub(r"\\[a-z]+[0-9]* ?", "", r.stdout.decode("utf-8", errors="replace"))
    if suf == ".html":
        return XML_TAG.sub(" ", path.read_bytes().decode("latin-1", errors="replace"))
    # .doc: OOXML primero (la mayoría), luego antiword (binario viejo)
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            body = DOCX_BODY.search(xml)
            if body:
                t = body.group(0)
                t = t.replace("</w:p>", "\n").replace("<w:br/>", "\n")
                t = re.sub(r"<w:tab[^>]*/>", "\t", t)
                return XML_TAG.sub("", t)
    except (zipfile.BadZipFile, KeyError, ValueError):
        pass
    r = subprocess.run(["antiword", str(path)], capture_output=True, timeout=120)
    if r.returncode == 0 and r.stdout.strip():
        return r.stdout.decode("utf-8", errors="replace")
    return ""


def main():
    print("descubriendo títulos del listing…", flush=True)
    mapa = titulo_map()
    print(f"mapa: {len(mapa):,} ids", flush=True)

    ok = sin_texto = sin_meta = 0
    lote = []
    archivos = sorted(FILES.iterdir())
    for i, path in enumerate(archivos, 1):
        id_arch = path.stem
        meta = mapa.get(id_arch)
        texto = extraer(path)
        if len(texto.strip()) < MIN_CHARS:
            sin_texto += 1
            continue
        if isinstance(meta, tuple):
            titulo, entidad = meta
        elif meta:
            titulo, entidad = meta, None
        else:
            titulo, entidad = f"Ordenamiento {id_arch}", None
            sin_meta += 1
        texto = texto.replace("\x00", "")
        lote.append(Documento(
            fuente=Fuente.ORDEN_JURIDICO,
            titulo=titulo,
            texto=texto,
            registro_sjf=f"ORDJ:{id_arch}",
            url_origen="https://www.ordenjuridico.gob.mx/Documentos/Estatal/",
            entidad=entidad,
            raw={"archivo": path.name, "recuperado": "nov-2026"},
        ))
        if len(lote) >= 50:
            batch_upsert_documentos(lote)
            ok += len(lote)
            print(f"[{i}/{len(archivos)}] recuperados {ok}", flush=True)
            lote = []
        try:
            path.unlink()
        except OSError:
            pass
    if lote:
        batch_upsert_documentos(lote)
        ok += len(lote)
    print(f"FIN: recuperados={ok} sin-texto={sin_texto} sin-meta={sin_meta}", flush=True)


if __name__ == "__main__":
    main()
