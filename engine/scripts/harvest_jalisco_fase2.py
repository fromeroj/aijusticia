#!/usr/bin/env python3
"""Jalisco fase 2 (MAC): descarga los PDFs de las tocas listadas en ids.jsonl.

El backend exige un token reCAPTCHA v3 (action=visitor_verify) por petición en
el header X-Recaptcha-Token. El token se genera dentro de la página con
grecaptcha.execute — por eso corre en un navegador local, no en el server.

Uso:  python3 harvest_jalisco_fase2.py [max_descargas]
Estado/resume: data/jalisco/estado_fase2.json · PDFs: data/jalisco/pdfs/
"""
import base64
import json
import os
import sys
import time
from pathlib import Path

import requests

from playwright.sync_api import sync_playwright

FRONT = "https://publicacionsentencias.stjjalisco.gob.mx/sentencias"
BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx"
SITE_KEY = "6LeVK48tAAAAABtfSIPLusp-4cMthtofl497dZvX"
DIR = Path(__file__).resolve().parent.parent / "data" / "jalisco"
IDS = DIR / "ids.jsonl"
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado_fase2.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

# corre DENTRO de la página: genera token v3 y pide la URL firmada de S3
FETCH_JS = """
async (tocaId) => {
  const token = await grecaptcha.execute('%s', {action: 'visitor_verify'});
  const r = await fetch('%s/toca/' + tocaId + '/file?modo=descargar',
                        {headers: {'X-Recaptcha-Token': token}});
  const j = await r.json();
  return {status: r.status, url: (j.data || {}).url || null, body: JSON.stringify(j).slice(0, 120)};
}
""" % (SITE_KEY, BACK)


def ids_cargados():
    out = []
    for line in IDS.read_text().strip().split("\n"):
        try:
            out.append(json.loads(line))
        except Exception:
            pass
    return out


def main():
    todo = ids_cargados()
    hechos = set()
    if ESTADO.exists():
        hechos = set(json.loads(ESTADO.read_text()))
    os.makedirs(PDFS, exist_ok=True)
    pendientes = [t for t in todo if t.get("file") and t["file"] not in hechos]
    print(f"IDs: {len(todo)}, ya descargados: {len(hechos)}, pendientes: {len(pendientes)}", flush=True)

    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False, channel="chrome",
                                args=["--disable-blink-features=AutomationControlled"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page = ctx.new_page()
    page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
    page.wait_for_timeout(12000)

    ok = err = 0
    try:
        for t in pendientes:
            if MAX and ok >= MAX:
                break
            rel = t["file"]
            toca_id = t["id"]
            ok_file = False
            res = {"body": ""}
            for espera in (0, 3, 8, 15, 25):
                if espera:
                    time.sleep(espera)
                try:
                    res = page.evaluate(FETCH_JS, str(toca_id))
                except Exception:
                    # página caducada: recargar y volver a intentar
                    page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_timeout(8000)
                    try:
                        res = page.evaluate(FETCH_JS, str(toca_id))
                    except Exception:
                        continue
                if res["status"] == 200 and res.get("url"):
                    r = requests.get(res["url"], timeout=120)
                    if r.content[:4] == b"%PDF":
                        dest = PDFS / rel
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        dest.write_bytes(r.content)
                        hechos.add(rel)
                        ok += 1
                        ok_file = True
                        break
                if res["status"] != 403:
                    break
            if ok_file:
                err_consec = 0
            else:
                err += 1
                err_consec += 1
                if err_consec == 1 or err_consec % 10 == 0:
                    print(f"  {rel}: {res.get('body', '')[:100]}", flush=True)
                if err_consec >= 25:
                    print("25 fallos consecutivos — abortando (reanudar más tarde)", flush=True)
                    break
            if ok and ok % 100 == 0:
                ESTADO.write_text(json.dumps(sorted(hechos)))
                print(f"  {ok} descargados ({err} errores)", flush=True)
            time.sleep(0.3)
    finally:
        ESTADO.write_text(json.dumps(sorted(hechos)))
        browser.close()
        p.stop()
        print(f"FASE2 TERMINADA: ok={ok} err={err} total_hechos={len(hechos)}", flush=True)


if __name__ == "__main__":
    main()
