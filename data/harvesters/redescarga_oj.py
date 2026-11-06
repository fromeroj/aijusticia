#!/usr/bin/env python3
"""Re-descarga las leyes de OrdenJurídico que se perdieron con la DB archivo
(182, suspendida 15-oct-2026 con ~1,400 leyes recuperadas dentro).

Lógica: para cada id del listing oficial que NO exista en la DB canónica
(162) y NO esté entre los 358 archivos pendientes, re-descarga desde
fichaOrdenamiento.php, extrae y upsertea. Idempotente (dedup ORDJ:id).
Borra el archivo tras éxito.

Uso (en 66): setsid nohup .venv/bin/python scripts/harvesters/redescarga_oj.py \
  > /var/log/aijusticia_redescarga.log 2>&1 < /dev/null &
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

from ai_justicia.config import settings
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos
import psycopg

BASE = "https://ordenjuridico.gob.mx"
TMP = Path("/opt/aijusticia/corpus_downloads/ordenjuridico/redescarga")
TMP.mkdir(parents=True, exist_ok=True)

_FICHA_RE = re.compile(r'https?://[^"\']*Documentos/Estatal/([^"\']+)')
_TITULO_RE = re.compile(r">\s*([^<>]{10,300}?)\s*</a>", re.I)
DOCX_BODY = re.compile(r"<w:body[ >].*</w:body>", re.S)
XML_TAG = re.compile(r"<[^>]+>")


def extraer(path: Path) -> str:
    suf = path.suffix.lower()
    if suf == ".pdf":
        r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=120)
        return r.stdout.decode("utf-8", errors="replace")
    if suf == ".rtf":
        r = subprocess.run(["unrtf", "--text", str(path)], capture_output=True, timeout=120)
        return re.sub(r"\\[a-z]+[0-9]* ?", "", r.stdout.decode("utf-8", errors="replace"))
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", errors="replace")
            body = DOCX_BODY.search(xml)
            if body:
                t = body.group(0).replace("</w:p>", "\n")
                return XML_TAG.sub("", t)
    except (zipfile.BadZipFile, KeyError, ValueError):
        pass
    r = subprocess.run(["antiword", str(path)], capture_output=True, timeout=120)
    return r.stdout.decode("utf-8", errors="replace") if r.returncode == 0 else ""


def main():
    s = creq.Session(impersonate="chrome", timeout=60, headers={"Referer": BASE})
    s.get(f"{BASE}/", timeout=30)
    time.sleep(1)

    with psycopg.connect(settings.psycopg_dsn) as conn:
        en_db = {r[0] for r in conn.execute(
            "SELECT registro_sjf FROM documentos WHERE fuente = 'OrdenJuridico'").fetchall()}

    pendientes = []
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
        # pares (id, título) del listing
        for m in re.finditer(
                r'idArchivo=(\d+)&ambito=estatal[^>]*>.*?>([^<>]{10,300})</a>', t, re.S):
            id_arch, titulo = m.group(1), re.sub(r"\s+", " ", m.group(2)).strip()
            if f"ORDJ:{id_arch}" not in en_db:
                pendientes.append((id_arch, titulo))
        time.sleep(2)
    print(f"pendientes por re-descargar: {len(pendientes)}", flush=True)

    ok = err = 0
    for i, (id_arch, titulo) in enumerate(pendientes, 1):
        try:
            rf = s.get(f"{BASE}/fichaOrdenamiento.php?idArchivo={id_arch}&ambito=estatal",
                       timeout=60).content.decode("windows-1252", errors="replace")
            mf = _FICHA_RE.search(rf)
            if not mf:
                err += 1
                continue
            url = f"https://www.ordenjuridico.gob.mx/Documentos/Estatal/{mf.group(1)}"
            rd = s.get(url, timeout=180)
            if rd.status_code != 200 or len(rd.content) < 1000:
                err += 1
                continue
            fname = mf.group(1).split("/")[-1]
            dest = TMP / f"{id_arch}.{fname.split('.')[-1].lower()}"
            dest.write_bytes(rd.content)
            texto = extraer(dest).replace("\x00", "")
            if len(texto.strip()) < 200:
                err += 1
                dest.unlink(missing_ok=True)
                continue
            batch_upsert_documentos([Documento(
                fuente=Fuente.ORDEN_JURIDICO,
                titulo=titulo,
                texto=texto,
                registro_sjf=f"ORDJ:{id_arch}",
                url_origen=url,
                raw={"archivo": fname, "redescarga": "nov-2026"},
            )])
            ok += 1
            dest.unlink(missing_ok=True)
            if ok % 50 == 0:
                print(f"[{i}/{len(pendientes)}] re-descargadas {ok} (err {err})", flush=True)
        except Exception as e:
            print(f"  {id_arch}: {str(e)[:70]}", flush=True)
            err += 1
        time.sleep(1)
    print(f"FIN: ok={ok} err={err}", flush=True)


if __name__ == "__main__":
    main()
