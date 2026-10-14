#!/usr/bin/env python3
"""Cosecha las sentencias públicas del PJ de Sonora (API JSON).

API: GET /api/Sentencias.php?page=N — JSON con resultado[]
Cada sentencia: Id, Asunto, Anio, Fecha, Unidad, IdCatRamo, etc.
Ver individual: /Publicaciones/Sentencias/Ver/{IdCrypt}

Uso (server):  nohup python3 harvest_sonora.py > log 2>&1 &
Resume: /opt/aijusticia/corpus_downloads/sonora/estado.json
"""
from __future__ import annotations

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
ESTADO = DIR / "estado.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

s = creq.Session(impersonate="chrome", timeout=40, headers={
    "Referer": f"{BASE}/Publicaciones/Sentencias", "Accept": "application/json",
})


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": [], "pagina": 1}
    hechos = set(est["hechos"])
    pagina = est.get("pagina", 1)
    print(f"ya hechos: {len(hechos)}, desde página {pagina}", flush=True)

    ok = err = 0
    try:
        while True:
            r = s.get(API, params={"page": pagina}, timeout=60)
            if r.status_code != 200:
                print(f"página {pagina}: HTTP {r.status_code} — pausa", flush=True)
                time.sleep(30)
                continue
            d = r.json()
            resultado = d.get("resultado") or []
            if not resultado:
                print(f"página {pagina}: sin resultados — fin", flush=True)
                break
            lote = []
            for item in resultado:
                sid = item.get("Id") or ""
                if not sid or sid in hechos:
                    continue
                texto = item.get("Contenido") or ""
                titulo = (f"Sentencia {item.get('Asunto')}/{item.get('Anio')} — "
                          f"{item.get('Unidad', '')}").strip()[:300]
                # texto puede venir en el campo Contenido o Nota
                if len(texto) < 200:
                    texto = json.dumps(item, ensure_ascii=False)
                lote.append(Documento(
                    fuente=Fuente("SentenciasSonora"),
                    titulo=titulo,
                    texto=texto,
                    registro_sjf=f"SON:{sid}",
                    url_origen=f"{BASE}/Publicaciones/Sentencias/Ver/{sid}",
                    entidad="Sonora",
                    raw={"unidad": item.get("Unidad"), "asunto": item.get("Asunto"),
                         "anio": item.get("Anio"), "ramo": item.get("IdCatRamo"),
                         "juicio": item.get("IdCatJuicio"),
                         "fecha": item.get("Fecha"),
                         "sentido": item.get("IdCatSentidoSentencia"),
                         "perspectiva_genero": item.get("IsPerspectivaGenero")},
                ))
                hechos.add(sid)
                ok += 1
                if MAX and ok >= MAX:
                    break
            if lote:
                n = batch_upsert_documentos(lote)
                print(f"página {pagina}: +{n} (total {ok})", flush=True)
            est["hechos"] = sorted(hechos)
            est["pagina"] = pagina + 1
            estado_guardar(est)
            if MAX and ok >= MAX:
                break
            pagina += 1
            time.sleep(0.5)
    finally:
        estado_guardar(est)
        print(f"SONORA TERMINADO: ok={ok} err={err} vistos={len(hechos)}", flush=True)


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
