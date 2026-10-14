#!/usr/bin/env python3
"""Cosecha las versiones públicas de sentencias de Coahuila (API PJECZ v3).

API: api.justiciadigital.gob.mx/v3 — autoridades → sentencias/datatable
→ detalle con archivo+url (GCS) → PDF → texto → corpus.

Uso (server):  nohup python3 harvest_coahuila.py > log 2>&1 &
Resume: /opt/aijusticia/corpus_downloads/coahuila/estado.json
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

KEY = "gAAAAABlErx69Ks3NE85EZmaGz7k2PnbGgtQ1tO8zJQfBPL1KwH4YCPUOGUrY6ng3yxiHzQi0p12n7SMPDE-JeHPAGS0ExVSiPjAAjGkP3HjEJmO6f4wf7c="
API = "https://api.justiciadigital.gob.mx/v3"
H = {"X-Api-Key": KEY, "Accept": "application/json", "User-Agent": "aijusticia/1.0"}
DIR = Path("/opt/aijusticia/corpus_downloads/coahuila")
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

s = creq.Session(impersonate="chrome", timeout=60, headers=H)


def extraer_pdf(path: Path) -> str:
    try:
        r = subprocess.run(["pdftotext", "-q", str(path), "-"], capture_output=True, timeout=180)
        return r.stdout.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  pdftotext: {str(e)[:70]}", flush=True)
        return ""


def main():
    PDFS.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": [], "autoridades": []}
    hechos = set(est["hechos"])

    # autoridades
    r = s.get(f"{API}/autoridades?es_jurisdiccional=true", timeout=40)
    auts = r.json().get("items") or []
    print(f"autoridades jurisdiccionales: {len(auts)}", flush=True)

    ok = err = 0
    try:
        for a in auts:
            aid = a["id"]
            if aid in est.get("autoridades", []):
                continue
            pagina = 1
            while True:
                r = s.get(f"{API}/sentencias/datatable", params={
                    "autoridad_id": aid, "pagina": pagina, "tamano": 50,
                }, timeout=60)
                if r.status_code != 200:
                    print(f"aut {aid} pág {pagina}: HTTP {r.status_code} — pausa", flush=True)
                    time.sleep(20)
                    continue
                d = r.json()
                data = d.get("data") or []
                if not data:
                    break
                lote = []
                for item in data:
                    sid = item["id"]
                    if str(sid) in hechos:
                        continue
                    try:
                        rd = s.get(f"{API}/sentencias/{sid}", headers=H, timeout=60)
                        det = rd.json()
                        url_pdf = det.get("url")
                        archivo = det.get("archivo")
                        if not url_pdf or not archivo:
                            continue
                        rd2 = s.get(url_pdf, timeout=120)
                        if rd2.status_code != 200 or rd2.content[:4] != b"%PDF":
                            err += 1
                            continue
                        dest = PDFS / f"{sid}.pdf"
                        dest.write_bytes(rd2.content)
                        texto = extraer_pdf(dest)
                        if len(texto.strip()) < 300:
                            err += 1
                            continue
                        titulo = (f"Sentencia {item.get('sentencia') or ''} — "
                                  f"{item.get('materia_tipo_juicio_descripcion') or ''} "
                                  f"({item.get('autoridad_descripcion_corta') or ''})").strip()[:300]
                        lote.append(Documento(
                            fuente=Fuente("SentenciasCoahuila"),
                            titulo=titulo,
                            texto=texto,
                            registro_sjf=f"COA:{sid}",
                            url_origen=url_pdf,
                            entidad="Coahuila",
                            raw={"expediente": item.get("expediente"),
                                 "sentencia_fecha": item.get("sentencia_fecha"),
                                 "fecha_publicacion": item.get("fecha"),
                                 "autoridad": det.get("autoridad_descripcion"),
                                 "distrito": det.get("distrito_nombre"),
                                 "archivo": archivo,
                                 "perspectiva_genero": det.get("es_perspectiva_genero")},
                        ))
                        hechos.add(str(sid))
                        ok += 1
                    except Exception as e:
                        print(f"  {sid}: {str(e)[:80]}", flush=True)
                        err += 1
                    time.sleep(0.1)
                if lote:
                    n = batch_upsert_documentos(lote)
                    lote = []
                    print(f"aut {aid} pág {pagina}: lote +{n} (ok {ok}, err {err})", flush=True)
                    est["hechos"] = sorted(hechos)
                    estado_guardar(est)
                pag = d.get("paginacion") or {}
                total_pag = int(pag.get("TotalPaginas") or 1)
                if pagina >= total_pag:
                    break
                pagina += 1
                time.sleep(0.2)
            nuevas_aut = est.get("autoridades", [])
            nuevas_aut.append(aid)
            est["autoridades"] = nuevas_aut
            estado_guardar(est)
            print(f"autoridad {aid} completa", flush=True)
            if MAX and ok >= MAX:
                break
    finally:
        estado_guardar(est)
        print(f"COAHUILA TERMINADO: ok={ok} err={err} vistos={len(hechos)}", flush=True)


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
