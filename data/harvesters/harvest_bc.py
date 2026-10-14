#!/usr/bin/env python3
"""Cosecha las versiones públicas de sentencias del PJ de Baja California.

API: GET /Sentencia/ListadoSentencias (JSON paginado)
Archivos: RTF en documento_path + descripcion (URL-encode necesario)
Extracción: unrtf · Ingesta: Fuente SentenciasBC, entidad Baja California

Uso (server):  python3 harvest_bc.py
Resume: data del estado en /opt/aijusticia/corpus_downloads/bc/estado.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

BASE = "https://versionespublicas.pjbc.gob.mx"
DIR = Path("/opt/aijusticia/corpus_downloads/bc")
FILES = DIR / "rtf"
ESTADO = DIR / "estado.json"
REGISTROS = 50

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None


def extraer_texto(path: Path) -> str:
    try:
        r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  extracción: {str(e)[:80]}", flush=True)
        return ""


def re_sub(t: str) -> str:
    import re
    t = re.sub(r"\\'[0-9a-f]{2}", "", t)
    return t


def main():
    FILES.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": []}
    hechos = set(est["hechos"])
    print(f"ya hechos: {len(hechos)}", flush=True)

    s = creq.Session(impersonate="chrome", timeout=90, headers={
        "Referer": f"{BASE}/", "Accept": "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    s.get(f"{BASE}/", timeout=30)

    total_ing = err = 0
    pagina = 1
    try:
        while True:
            r = s.get(f"{BASE}/Sentencia/ListadoSentencias", params={
                "palabra": "", "pagina": str(pagina), "registros": str(REGISTROS),
                "cve_tipo_sentencia": "0", "perspectiva": "false",
                "reg_encontrados": "", "fec_ini": "1900-01-01",
                "fec_fin": time.strftime("%Y-%m-%d"),
            }, timeout=120)
            if r.status_code != 200:
                print(f"página {pagina}: HTTP {r.status_code} — reintentando en 20s", flush=True)
                time.sleep(20)
                continue
            d = r.json()
            res = d.get("result") or []
            pag = d.get("paginacion") or {}
            if not res:
                print(f"página {pagina}: sin resultados — fin", flush=True)
                break
            lote = []
            for item in res:
                path = (item.get("documento_path") or "").strip()
                fname = (item.get("descripcion") or "").strip()
                if not path or not fname or fname in hechos:
                    continue
                key = fname
                url_file = f"{BASE}/DescargaDocumento/Index?cadena={item.get('documento_id')}"
                try:
                    rd = s.get(url_file, timeout=120)
                    if rd.status_code != 200 or rd.content[:4] != b"%PDF":
                        err += 1
                        continue
                    fname = f"{item.get('documento_id')}.pdf"
                    dest = FILES / fname
                    dest.write_bytes(rd.content)
                    texto = extraer_texto(dest)
                    if len(texto.strip()) < 200:
                        err += 1
                        continue
                    lote.append(Documento(
                        fuente=Fuente("SentenciasBC"),
                        titulo=(f"Sentencia {item.get('tipo_juicio') or ''} "
                                f"{item.get('juzgado') or ''} ({item.get('fecha') or item.get('anio') or ''})").strip()[:300],
                        texto=texto,
                        registro_sjf=f"BC:{hashlib.md5(texto.encode()).hexdigest()[:16]}",
                        url_origen=url_file,
                        entidad="Baja California",
                        raw={"ciudad": item.get("ciudad"), "juzgado": item.get("juzgado"),
                             "tipo_juicio": item.get("tipo_juicio"), "anio": item.get("anio"),
                             "folio": item.get("folio"), "fecha": item.get("fecha")},
                    ))
                    hechos.add(key)
                except Exception as e:
                    print(f"  {fname[:40]}: {str(e)[:80]}", flush=True)
                    err += 1
                time.sleep(0.15)
            if lote:
                total_ing += batch_upsert_documentos(lote)
            est["hechos"] = sorted(hechos)
            estado_guardar(est)
            print(f"página {pagina}: +{len(res)} vistos, ingesta acumulada {total_ing}, err {err}, "
                  f"paginación {pag.get('PaginaActual')}/{pag.get('TotalPaginas')}", flush=True)
            if pag.get("PaginaActual") and pag.get("TotalPaginas") and \
                    int(pag["PaginaActual"]) >= int(pag["TotalPaginas"]):
                print("FIN del listado", flush=True)
                break
            pagina += 1
            if MAX and ok_pages(pagina, MAX):
                break
    finally:
        estado_guardar(est)
        print(f"BC TERMINADO: ingesta={total_ing} err={err} vistos={len(hechos)}", flush=True)


def ok_pages(pagina: int, max_pages: int) -> bool:
    return pagina > max_pages


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
