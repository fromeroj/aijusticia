#!/usr/bin/env python3
"""Cosecha las EJECUTORIAS del SJF (sentencias completas, 23K+).

Feed: POST /ejecutorias?page=N&size=200 (newest-first), cada item trae
rubro + texto. Si el texto no viene en el feed, se pide el detalle.
Ingesta: Fuente=EjecutoriasSJF, registro=EJ:{id}, con ius y votación en raw.

Uso (server):  nohup python3 harvest_ejecutorias.py > log 2>&1 &
Resume: /opt/aijusticia/corpus_downloads/ejecutorias/estado.json
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.models import Documento, Fuente
from ai_justicia.corpus.store import batch_upsert_documentos

BASE = "https://sjf2.scjn.gob.mx"
FEED = f"{BASE}/services/sjfejecutoriamicroservice/api/public/ejecutorias"
DIR = Path("/opt/aijusticia/corpus_downloads/ejecutorias")
ESTADO = DIR / "estado.json"
SIZE = 200

import os
import random

IPROYAL_USER = "g3fNhiqGMBQxwpbX"
IPROYAL_PASS = "UNsQCR3SepyWDcIE"
def nueva_sesion():
    """Sesión vía proxy residencial rotatorio de IPRoyal."""
    proxy = f"http://{IPROYAL_USER}:{IPROYAL_PASS}@geo.iproyal.com:12321"
    return creq.Session(impersonate="chrome", timeout=90, proxy=proxy, headers={
        "Referer": "https://sjf2.scjn.gob.mx/", "Accept": "application/json",
    })


def calentar():
    try:
        s.get(f"{BASE}/", timeout=40)
    except Exception:
        pass
    time.sleep(2)


def rotar_sesion():
    global s
    s = nueva_sesion()
    print("  nueva sesión (IP rotada)", flush=True)
    calentar()


s = nueva_sesion()


def get_con_reintentos(url, **kw):
    ultimo = None
    for _ in range(6):
        try:
            return s.get(url, **kw)
        except Exception as e:
            ultimo = e
            time.sleep(5)
    raise ultimo


def limpiar_html(html: str) -> str:
    t = re_sub(html)
    return t


def re_sub(t: str) -> str:
    import re
    t = re.sub(r"<br\s*/?>", "\n", t, flags=re.I)
    t = re.sub(r"</p>", "\n\n", t, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = t.replace("&nbsp;", " ").replace("&iacute;", "í").replace("&aacute;", "á")
    t = t.replace("&eacute;", "é").replace("&oacute;", "ó").replace("&uacute;", "ú")
    t = t.replace("&ntilde;", "ñ").replace("&quot;", '"').replace("&amp;", "&")
    return t.strip()


def main():
    DIR.mkdir(parents=True, exist_ok=True)
    est = json.loads(ESTADO.read_text()) if ESTADO.exists() else {"hechos": []}
    hechos = set(est["hechos"])
    print(f"ya hechos: {len(hechos)}", flush=True)
    try:
        s.get(f"{BASE}/", timeout=40)  # calentar sesión Imperva (cookies incap)
    except Exception:
        pass
    time.sleep(2)

    total = 0
    lote: list = []
    pagina = 1
    try:
        while True:
            r = None
            for _ in range(6):
                try:
                    r = s.post(f"{FEED}?page={pagina}&size={SIZE}",
                               json={"criteria": {"searchTerms": [], "classifiers": []}},
                               timeout=120)
                    break
                except Exception as e:
                    print(f"p\u00e1gina {pagina}: red ({str(e)[:50]}) \u2014 reintento", flush=True)
                    time.sleep(8)
            if r is None:
                print(f"página {pagina}: sin respuesta de red — pausa 30s", flush=True)
                time.sleep(30)
                continue
            if r.status_code != 200:
                # Imperva: rotar a una IP pegajosa nueva, calentar y reintentar
                print(f"página {pagina}: HTTP {r.status_code} — rotando sesión", flush=True)
                rotar_sesion()
                try:
                    r = s.post(f"{FEED}?page={pagina}&size={SIZE}",
                               json={"criteria": {"searchTerms": [], "classifiers": []}},
                               timeout=120)
                except Exception:
                    pass
            if r.status_code != 200:
                print(f"página {pagina}: sigue HTTP {r.status_code} — pausa 60s", flush=True)
                time.sleep(60)
                continue
            d = r.json()
            docs = d.get("items") or []
            if not docs:
                print(f"página {pagina}: sin items — fin del feed", flush=True)
                break
            nuevos = 0
            for item in docs:
                eid = str(item.get("id") or "")
                if not eid or eid in hechos:
                    continue
                texto = item.get("texto") or ""
                if len(texto) < 200:
                    try:
                        rd = get_con_reintentos(f"{FEED}/{eid}?isSemanal={int(item.get('semanal') or 0)}")
                        texto = (rd.json() or {}).get("texto") or texto
                    except Exception:
                        pass
                texto_limpio = limpiar_html(texto)
                if len(texto_limpio) < 200:
                    continue
                rubro = re_sub(item.get("rubro") or "")[:300]
                lote.append(Documento(
                    fuente=Fuente.EJECUTORIAS_SJF,
                    titulo=rubro,
                    texto=texto_limpio,
                    registro_sjf=f"EJ:{eid}",
                    fecha_publicacion=None,
                    url_origen=f"{FEED}/{eid}",
                    raw={
                        "ius": item.get("ius"), "promovente": item.get("promovente"),
                        "votacion": item.get("votacion"), "sala": item.get("sala"),
                        "epoca": item.get("epoca"), "instancia": item.get("instancia"),
                        "tipo_asunto": item.get("tipoAsunto"),
                    },
                ))
                hechos.add(eid)
                nuevos += 1
            if lote:
                n = batch_upsert_documentos(lote)
                total += n
                lote = []
                est["hechos"] = sorted(hechos)
                print(f"página {pagina}: +{n} (total {total}, vistos {len(hechos)})", flush=True)
                estado_guardar(est)
            else:
                est["hechos"] = sorted(hechos)
                estado_guardar(est)
            pagina += 1
            time.sleep(0.4)
    finally:
        if lote:
            total += batch_upsert_documentos(lote)
        estado_guardar(est)
        print(f"EJECUTORIAS TERMINADO: ingesta={total} vistos={len(hechos)}", flush=True)


def estado_guardar(est: dict) -> None:
    ESTADO.write_text(json.dumps(est, ensure_ascii=False))


if __name__ == "__main__":
    main()
