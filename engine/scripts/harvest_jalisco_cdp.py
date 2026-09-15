#!/usr/bin/env python3
"""Jalisco fase 2 vía TU Chrome real (CDP).

Tu perfil tiene la reputación que reCAPTCHA v3 exige — el Chromium de
Playwright la rechaza. Este script se CONECTA a tu Chrome (abierto con
--remote-debugging-port=9222), abre la pestaña del sitio y descarga las
tocas generando los tokens dentro de tu propia sesión.

Preparación (una vez):
  1. Cierra Chrome.
  2. Ábrelo con el puerto de depuración:
     open -a "Google Chrome" --args --remote-debugging-port=9222
  3. Corre: python3 scripts/harvest_jalisco_cdp.py

Resume: data/jalisco/estado_fase2.json · PDFs: data/jalisco/pdfs/
"""
import base64
import json
import sys
import time
from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

FRONT = "https://publicacionsentencias.stjjalisco.gob.mx/sentencias"
SITE_KEY = "6LeVK48tAAAAABtfSIPLusp-4cMthtofl497dZvX"
CDP = "http://localhost:9222"
DIR = Path(__file__).resolve().parent.parent / "data" / "jalisco"
IDS = DIR / "ids.jsonl"
PDFS = DIR / "pdfs"
ESTADO = DIR / "estado_fase2.json"

MAX = int(sys.argv[1]) if len(sys.argv) > 1 else None

# corre DENTRO de tu sesión: token v3 + URL firmada de S3
FETCH_JS = """
async (tocaId) => {
  const token = await grecaptcha.execute('%s', {action: 'visitor_verify'});
  const r = await fetch('%s/toca/' + tocaId + '/file?modo=descargar',
                        {headers: {'X-Recaptcha-Token': token}});
  const j = await r.json();
  return {status: r.status, url: (j.data || {}).url || null,
          body: JSON.stringify(j).slice(0, 120)};
}
""" % (SITE_KEY, BACK := "https://publica-sentencias-backend.stjjalisco.gob.mx")


def main():
    todo = []
    for line in (IDS).read_text().strip().split("\n"):
        try:
            d = json.loads(line)
            if d.get("file"):
                todo.append(d)
        except Exception:
            pass
    hechos = set()
    if ESTADO.exists():
        hechos = set(json.loads(ESTADO.read_text()))
    pendientes = [t for t in todo if t["file"] not in hechos]
    print(f"IDs: {len(todo)}, hechos: {len(hechos)}, pendientes: {len(pendientes)}", flush=True)

    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp(CDP)
    ctx = browser.contexts[0]

    page = next((pg for pg in ctx.pages if "stjjalisco" in pg.url), None)
    if page is None:
        page = ctx.new_page()
    if FRONT not in (page.url or ""):
        page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
    page.bring_to_front()
    page.wait_for_function("() => window.grecaptcha && window.grecaptcha.execute", timeout=60000)

    ok = err = err_consec = 0
    res = {"body": ""}
    try:
        for t in pendientes:
            if MAX and ok >= MAX:
                break
            rel, toca_id = t["file"], t["id"]
            ok_file = False
            for espera in (0, 5, 15, 40):
                if espera:
                    time.sleep(espera)
                try:
                    res = page.evaluate(FETCH_JS, str(toca_id))
                except Exception:
                    page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
                    page.wait_for_function("() => window.grecaptcha && window.grecaptcha.execute", timeout=60000)
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
                if err_consec == 1 or err_consec % 5 == 0:
                    print(f"  {rel}: {res.get('body', '')[:100]}", flush=True)
                if err_consec >= 10:
                    print("10 fallos seguidos — ¿tu Chrome abrió con --remote-debugging-port=9222?",
                          flush=True)
                    break
            if ok and ok % 50 == 0:
                ESTADO.write_text(json.dumps(sorted(hechos)))
                print(f"  {ok} descargados ({err} errores)", flush=True)
            time.sleep(1.5)
    finally:
        ESTADO.write_text(json.dumps(sorted(hechos)))
        print(f"SESIÓN CDP TERMINADA: ok={ok} err={err} total_hechos={len(hechos)}", flush=True)


if __name__ == "__main__":
    main()
