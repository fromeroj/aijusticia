#!/usr/bin/env python3
"""Cosecha las versiones públicas de sentencias del PJ de Chiapas.

Fuente: transparencia.poderjudicialchiapas.gob.mx fracción de versiones
públicas — XLSX trimestrales por juzgado, cada fila = 1 sentencia con
hipervínculo al PDF completo.

Uso (server):  nohup python3 harvest_chiapas.py > log 2>&1 &
Resume: /opt/aijusticia/corpus_downloads/chiapas/estado.json
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

FRACCION = "https://transparencia.poderjudicialchiapas.gob.mx/fracciones/versiones-publicas-sentencias/15"
DIR = Path("/opt/aijusticia/corpus_downloads/chiapas")
XLSX_DIR = DIR / "xlsx"
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

s = creq.Session(impersonate="chrome", timeout=60, verify=False)


def extraer_texto_pdf(path: Path) -> str:
    try:
        r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  pdf→texto: {str(e)[:70]}", flush=True)
        return ""


def parsear_xlsx(contenido: bytes):
    """Rinde (meta, url_pdf) por cada fila con hipervínculo."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(contenido), read_only=True, data_only=True)
    for hoja in wb.sheetnames:
        ws = wb[hoja]
        filas = list(ws.iter_rows(values_only=True))
        # localizar la fila de encabezados (contiene 'Materia' o 'Ejercicio')
        if len(filas) < 6:
            continue
        for fila in filas[6:]:
            vals = [c for c in fila]
            if not any(vals):
                continue
            ejercicio = vals[0] if len(vals) > 0 else None
            materia = vals[3] if len(vals) > 3 else None
            tema = vals[4] if len(vals) > 4 else None
            fecha_emision = vals[5] if len(vals) > 5 else None
            expediente = vals[6] if len(vals) > 6 else None
            organo = vals[7] if len(vals) > 7 else None
            magistrado = vals[8] if len(vals) > 8 else None
            # hipervínculo: buscar la celda con URL a un pdf/anexo
            url_pdf = None
            for c in vals[9:]:
                if isinstance(c, str) and "http" in c and (".pdf" in c or "archivos" in c or "Anexos" in c):
                    url_pdf = c.strip()
                    break
            if not url_pdf and len(vals) > 10 and vals[10]:
                cand = str(vals[10]).strip()
                if cand.startswith("http"):
                    url_pdf = cand
            if not url_pdf:
                continue
            yield {
                "ejercicio": str(ejercicio or ""),
                "materia": str(materia or ""),
                "tema": str(tema or ""),
                "fecha_emision": str(fecha_emision or ""),
                "expediente": str(expediente or ""),
                "organo": str(organo or ""),
                "magistrado": str(magistrado or ""),
            }, url_pdf


def main():
    XLSX_DIR.mkdir(parents=True, exist_ok=True)
    PDFS.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": []}
    hechos = set(est["hechos"])
    print(f"ya hechos: {len(hechos)}", flush=True)

    # 1) enumerar XLSX de la fracción
    try:
        t = s.get(FRACCION, timeout=40, verify=False).text
    except Exception:
        t = s.get(FRACCION, timeout=40, verify=False).text
    xlsx = sorted(set(re.findall(r'href=["\']([^"\']*archivos/[^"\']*\.xlsx[^"\']*)["\']', t, re.I)))
    xlsx = [u if u.startswith("http") else "https://transparencia.poderjudicialchiapas.gob.mx" + u for u in xlsx]
    print(f"XLSX en la fracción: {len(xlsx)}", flush=True)

    ok = err = 0
    procesados = 0
    try:
        for url_xlsx in xlsx:
            nombre_x = url_xlsx.split("/")[-1]
            if nombre_x in hechos:
                continue
            try:
                rx = s.get(url_xlsx, timeout=90, verify=False)
                if rx.status_code != 200:
                    err += 1
                    continue
                for meta, url_pdf in parsear_xlsx(rx.content):
                    if url_pdf in hechos:
                        continue
                    try:
                        rd = s.get(url_pdf, timeout=120, verify=False)
                        if rd.status_code != 200 or rd.content[:4] != b"%PDF":
                            err += 1
                            continue
                        h = hashlib.md5(rd.content).hexdigest()[:12]
                        fname = f"{h}.pdf"
                        dest = PDFS / fname
                        dest.write_bytes(rd.content)
                        texto = extraer_texto_pdf(dest)
                        if len(texto.strip()) < 300:
                            err += 1
                            continue
                        titulo = (f"Sentencia {meta['expediente']} — {meta['materia']} / "
                                  f"{meta['tema']} ({meta['fecha_emision'][:10] if meta['fecha_emision'] else 's/f'})")[:300]
                        docs = [Documento(
                            fuente=Fuente("SentenciasChiapas"),
                            titulo=titulo,
                            texto=texto,
                            registro_sjf=f"CHIS:{h}",
                            url_origen=url_pdf,
                            entidad="Chiapas",
                            raw={"materia": meta["materia"], "tema": meta["tema"],
                                 "expediente": meta["expediente"], "organo": meta["organo"],
                                 "magistrado": meta["magistrado"], "ejercicio": meta["ejercicio"]},
                        )]
                        batch_upsert_documentos(docs)
                        ok += 1
                        hechos.add(url_pdf)
                    except Exception as e:
                        err += 1
                        print(f"  pdf {url_pdf[-40:]}: {str(e)[:70]}", flush=True)
                    if MAX and ok >= MAX:
                        raise KeyboardInterrupt
            except Exception as e:
                print(f"  {nombre_x}: {str(e)[:80]}", flush=True)
            procesados += 1
            hechos.add(nombre_x)
            est["hechos"] = sorted(hechos)
            if procesados % 25 == 0:
                estado_guardar(est)
                print(f"  XLSX procesados: {procesados} | sentencias ok: {ok} | err: {err}", flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        estado_guardar(est)
        print(f"CHIAPAS TERMINADO (por ahora): ok={ok} err={err} procesados={procesados}", flush=True)


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
