#!/usr/bin/env python3
"""Cosecha las leyes estatales de ordenjuridico.gob.mx (las 32 entidades).

Fases (en un solo pase, con resume):
  1. despliegaedo2.php?edo=N  → ids de archivo + títulos (warmup Imperva)
  2. fichaOrdenamiento.php?idArchivo=X → URL del archivo (.doc/.pdf/.rtf)
  3. descarga → extracción de texto → upsert al corpus con entidad

Uso (server):  python3 harvest_ordenjuridico.py [max_docs]
Resume: data/ordenjuridico/estado.json
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

BASE = "https://ordenjuridico.gob.mx"
DIR = Path("/opt/aijusticia/corpus_downloads/ordenjuridico")
ESTADO = DIR / "estado.json"
FILES = DIR / "files"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

s = creq.Session(impersonate="chrome", timeout=60)
s.headers.update({"Referer": BASE})

_FICHA_RE = re.compile(
    r"href\s*=\s*javascript:void\(window\.open\(\"fichaOrdenamiento\.php\?idArchivo=(\d+)&ambito=estatal"
)
_TITULO_RE = re.compile(r">\s*([^<>]{10,300}?)\s*</a>", re.I)
_FILE_RE = re.compile(r'https?://[^"\']*Documentos/Estatal/([^"\']+)')


def extraer_texto(path: Path) -> str:
    try:
        if path.suffix.lower() == ".pdf":
            r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=120)
            return r.stdout.decode("utf-8", errors="replace")
        if path.suffix.lower() == ".doc":
            r = subprocess.run(["antiword", str(path)], capture_output=True, timeout=120)
            if r.returncode != 0 or not r.stdout.strip():
                r = subprocess.run(
                    ["strings", "-e", "l", str(path)], capture_output=True, timeout=120
                )
            return r.stdout.decode("utf-8", errors="replace")
        if path.suffix.lower() == ".rtf":
            r = subprocess.run(["unrtf", "--text", str(path)], capture_output=True, timeout=120)
            t = r.stdout.decode("utf-8", errors="replace")
            return re.sub(r"\\[a-z]+[0-9]* ?", "", t)
        if path.suffix.lower() == ".docx":
            r = subprocess.run(
                ["python3", "-c",
                 f"import sys,zipfile,re;x=zipfile.ZipFile('{path}').read('word/document.xml').decode('utf-8',errors='replace');"
                 "print(re.sub('<[^>]+>',' ',x))"],
                capture_output=True, timeout=120,
            )
            return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  extracción falló: {str(e)[:80]}", flush=True)
    return ""


def estado_cargar() -> dict:
    if ESTADO.exists():
        return json.loads(ESTADO.read_text())
    return {}


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


def main():
    os.makedirs(FILES, exist_ok=True)
    est = estado_cargar()
    hechos = set(est.get("hechos", []))
    s = creq.Session(impersonate="chrome", timeout=60, headers={"Referer": BASE})
    s.get(f"{BASE}/", timeout=30)  # warmup Imperva
    time.sleep(1)

    ok = err = 0
    for edo in range(1, 33):
        try:
            r = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0", timeout=60)
        except Exception as e:
            print(f"edo {edo}: error de red, reintentando… ({str(e)[:60]})", flush=True)
            time.sleep(10)
            try:
                r = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0", timeout=60)
            except Exception as e2:
                print(f"edo {edo}: falló definitivamente ({str(e2)[:60]})", flush=True)
                continue
        t = r.text
        if "incap_ses" in t or "Loading" in t[:3000]:
            print(f"edo {edo}: reto WAF — recalentando…", flush=True)
            s.get(f"{BASE}/", timeout=30)
            time.sleep(3)
            t = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0", timeout=60).text

        filas = []
        for m in _FICHA_RE.finditer(t):
            id_arch = m.group(1)
            if id_arch in hechos:
                continue
            # título: el texto del enlace que sigue al match
            seg = t[m.end(): m.end() + 400]
            mt = _TITULO_RE.search(seg)
            titulo = mt.group(1).strip() if mt else f"Ordenamiento {id_arch}"
            filas.append((id_arch, titulo))
        mm = re.search(r"(?i)total de\s*&?nbsp;?\s*(\d[\d,]*)\s*Ordenamientos", re.sub(r"&iacute;", "í", t))
        total_edo = mm.group(1) if mm else "?"
        print(f"edo {edo}: {len(filas)} ordenamientos nuevos (total en sitio: {total_edo})", flush=True)

        for id_arch, titulo in filas:
            if MAX and ok >= MAX:
                break
            try:
                rf = s.get(f"{BASE}/fichaOrdenamiento.php?idArchivo={id_arch}&ambito=estatal", timeout=60)
                mf = _FILE_RE.search(rf.text)
                if not mf:
                    err += 1
                    continue
                rel_path = mf.group(1)          # ej. 'Baja California/wo19493.doc'
                fname = rel_path.split("/")[-1]
                estado_nombre = rel_path.split("/")[0].strip()
                url_file = f"https://www.ordenjuridico.gob.mx/Documentos/Estatal/{rel_path}"
                rd = s.get(url_file, timeout=180)
                if rd.status_code != 200 or len(rd.content) < 1000:
                    err += 1
                    continue
                ext = fname.split(".")[-1].lower()
                dest = FILES / f"{id_arch}.{ext}"
                dest.write_bytes(rd.content)

                texto = extraer_texto(dest)
                if len(texto.strip()) < 200:
                    err += 1
                    continue

                docs = [Documento(
                    fuente=Fuente.ORDEN_JURIDICO,
                    titulo=titulo,
                    texto=texto,
                    registro_sjf=f"ORDJ:{id_arch}",
                    url_origen=url_file,
                    entidad=estado_nombre,
                    raw={"archivo": fname, "estado_str": estado_nombre},
                )]
                n = batch_upsert_documentos(docs)
                ok += n
                hechos.add(id_arch)
                est["hechos"] = sorted(hechos)
                est["entidades"] = est.get("entidades", {}) | {id_arch: estado_nombre}
                if ok % 25 == 0:
                    estado_guardar(est)
                    print(f"  {ok} ingestidos ({err} errores)", flush=True)
            except Exception as e:
                print(f"  {id_arch}: {str(e)[:90]}", flush=True)
                err += 1
        estado_guardar(est)
        if MAX and ok >= MAX:
            break

    estado_guardar(est)
    print(f"ORDENJURIDICO TERMINADO: ok={ok} err={err} total_hechos={len(hechos)}", flush=True)


if __name__ == "__main__":
    main()
