#!/usr/bin/env python3
"""Sonora v2: cosecha con descarga de PDFs por UrlPdf.

API: GET /api/Sentencias.php?page=N — devuelve metadata + UrlPdf por sentencia.
PDF: GET UrlPdf — versión pública de la sentencia (texto extraíble).

Uso (server):  nohup python3 harvest_sonora_v2.py > log 2>&1 &
Resume: /opt/aijusticia/corpus_downloads/sonora/estado_v2.json
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

API = "https://stjsonora.gob.mx/api/Sentencias.php"
BASE = "https://stjsonora.gob.mx"
DIR = Path("/opt/aijusticia/corpus_downloads/sonora")
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado_v2.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

s = creq.Session(impersonate="chrome", timeout=60, headers={
    "Referer": f"{BASE}/Publicaciones/Sentencias",
    "Accept": "application/json",
})


def extraer_pdf(path):
    try:
        r = subprocess.run(["pdftotext", "-q", str(path), "-"],
                           capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  pdftotext: {str(e)[:70]}", flush=True)
        return ""


def main():
    PDFS.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": [], "pagina": 1}
    hechos = set(est["hechos"])
    pagina = est.get("pagina", 1)
    print(f"ya hechos: {len(hechos)}, desde página {pagina}", flush=True)

    ok = err = 0
    try:
        while True:
            r = s.get(API, params={"page": pagina}, timeout=60)
            if r.status_code != 200:
                print(f"pág {pagina}: HTTP {r.status_code} — pausa 30s", flush=True)
                time.sleep(30)
                continue
            d = r.json()
            resultado = d.get("resultado") or []
            if not resultado:
                print(f"pág {pagina}: sin resultados — FIN", flush=True)
                break

            lote = []
            for item in resultado:
                sid = item.get("Id") or ""
                if not sid or sid in hechos:
                    continue

                # construir la URL del PDF desde la API
                url_pdf = item.get("UrlPdf") or ""
                if not url_pdf:
                    # construir desde el patrón conocido
                    url_pdf = f"{BASE}/Controller/DocumentController.php?Documento={sid}"

                try:
                    rd = s.get(url_pdf, timeout=90)
                    if rd.status_code != 200 or rd.content[:4] != b"%PDF":
                        err += 1
                        continue
                    h = hashlib.md5(rd.content).hexdigest()[:12]
                    fname = f"{sid}_{h}.pdf"
                    dest = PDFS / fname
                    dest.write_bytes(rd.content)
                    texto = extraer_pdf(dest)
                    if len(texto.strip()) < 300:
                        err += 1
                        continue

                    titulo = (f"Sentencia {item.get('Asunto','')}/{item.get('Anio','')} — "
                              f"{item.get('Unidad','')}").strip()[:300]
                    lote.append(Documento(
                        fuente=Fuente("SentenciasSonora"),
                        titulo=titulo,
                        texto=texto,
                        registro_sjf=f"SON:{sid}",
                        url_origen=url_pdf,
                        entidad="Sonora",
                        raw={"asunto": item.get("Asunto"), "anio": item.get("Anio"),
                             "unidad": item.get("Unidad"), "fecha": item.get("Fecha"),
                             "juicio": item.get("Juicio"), "ramo": item.get("Ramo"),
                             "sentido": item.get("Sentido")},
                    ))
                    hechos.add(sid)
                    ok += 1
                except Exception as e:
                    err += 1
                    print(f"  {sid}: {str(e)[:70]}", flush=True)

                if ok and ok % 50 == 0:
                    est["hechos"] = sorted(hechos)
                    est["pagina"] = pagina
                    estado_guardar(est)
                    print(f"  {ok} descargados ({err} err) — pág {pagina}", flush=True)
                time.sleep(0.3)

            if lote:
                n = batch_upsert_documentos(lote)
                print(f"pág {pagina}: +{n} (total {ok})", flush=True)
            est["hechos"] = sorted(hechos)
            est["pagina"] = pagina + 1
            estado_guardar(est)
            if MAX and ok >= MAX:
                break
            pagina += 1
            time.sleep(0.5)
    finally:
        estado_guardar(est)
        print(f"SONORA V2 TERMINADO: ok={ok} err={err} vistos={len(hechos)}", flush=True)


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
