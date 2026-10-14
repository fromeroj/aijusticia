#!/usr/bin/env python3
"""Harvesta las tesis digitalizadas del Repositorio UNAM (colección Tesis, ~43,873 docs).

Flujo validado:
  1. calentar sesión con GET /contenidos (sin params da 200; con params en frío da 502)
  2. GET /contenidos?c=b0dZK5&q=derecho&t=search_0&i=<página>&v=1 → HTML server-rendered
     con 50 fichas (i = página 1-based, 50/página, 878 páginas)
  3. ficha/ → localizar PDF / link de digitalización (fase B)

El backend es intermitente: reintento con backoff y sesión nueva.
CORRER EN LA MAC. Uso: python3 harvest_tesis_unam.py indice [desde_pag]
                      python3 harvest_tesis_unam.py fichas
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA = Path.home() / "workspace/aijusticia/engine/data"
MANIFEST = DATA / "unam_tesis_manifest.jsonl"
FICHAS = DATA / "unam_tesis_fichas.jsonl"
BASE = "https://repositorio.unam.mx"
COL = "b0dZK5"  # colección Tesis
PAGS_TOTAL = 900  # margen sobre 878
UA = {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def nueva_sesion(browser):
    ctx = browser.new_context(locale="es-MX", ignore_https_errors=True,
                              viewport={"width": 1300, "height": 900}, **UA)
    page = ctx.new_page()
    page.goto(f"{BASE}/contenidos", timeout=90000, wait_until="networkidle")
    time.sleep(5)
    return ctx, page


def buscar_pagina(browser, ctx_page, n, intentos=4):
    """Devuelve HTML de la página n de resultados (renovando sesión si falla)."""
    ctx, page = ctx_page
    url = f"{BASE}/contenidos?c={COL}&d=false&t=search_0&i={n}&v=1&as=0&q=derecho"
    for k in range(intentos):
        try:
            page.goto(url, timeout=90000, wait_until="domcontentloaded")
            time.sleep(7 + k * 3)
            html = page.content()
            if len(html) > 50_000 and "ficha/" in html:
                return html, ctx_page
        except Exception:
            pass
        # sesión nueva y backoff
        try:
            ctx.close()
        except Exception:
            pass
        time.sleep(8 + k * 10)
        ctx_page = nueva_sesion(browser)
        ctx, page = ctx_page
    return None, ctx_page


def indice(desde=1):
    hechos = set()
    if MANIFEST.exists():
        hechos = {json.loads(l)["slug"] for l in open(MANIFEST)}
        print(f"resume: {len(hechos)} slugs ya en manifiesto", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx_page = nueva_sesion(browser)
        with open(MANIFEST, "a") as out:
            vacias = 0
            for n in range(desde, PAGS_TOTAL + 1):
                html, ctx_page = buscar_pagina(browser, ctx_page, n)
                if not html:
                    vacias += 1
                    print(f"  [pag {n}] VACIA ({vacias} seguidas)", flush=True)
                    if vacias >= 8:
                        print("backend caído, pausa larga...", flush=True)
                        time.sleep(300)
                        vacias = 0
                    continue
                vacias = 0
                fichas = sorted(set(re.findall(r'ficha/([a-z0-9-]+-\d+)', html)))
                nuevas = 0
                for slug in fichas:
                    if slug not in hechos:
                        hechos.add(slug)
                        out.write(json.dumps({"slug": slug}) + "\n")
                        nuevas += 1
                out.flush()
                print(f"  [pag {n}] {len(fichas)} fichas (+{nuevas} nuevas, total {len(hechos)})", flush=True)
                time.sleep(4)
        ctx_page[0].close()
        browser.close()
    print(f"INDICE COMPLETO: {len(hechos)} tesis", flush=True)


def fichas_run():
    slugs = [json.loads(l)["slug"] for l in open(MANIFEST)]
    hechos = set()
    if FICHAS.exists():
        hechos = {json.loads(l)["slug"] for l in open(FICHAS)}
    print(f"manifiesto {len(slugs)}, hechos {len(hechos)}", flush=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx, page = nueva_sesion(browser)
        # calentar una busqueda primero (la ficha requiere contexto)
        page.goto(f"{BASE}/contenidos?c={COL}&d=false&t=search_0&i=1&v=1&as=0&q=derecho",
                  timeout=90000, wait_until="domcontentloaded")
        time.sleep(8)
        n = ok = 0
        with open(FICHAS, "a") as out:
            for slug in slugs:
                n += 1
                if slug in hechos:
                    continue
                rec = {"slug": slug}
                try:
                    page.goto(f"{BASE}/contenidos/ficha/{slug}", timeout=60000,
                              wait_until="domcontentloaded")
                    time.sleep(4)
                    fh = page.content()
                    rec["html_len"] = len(fh)
                    # PDF directo o visor
                    pdfs = sorted(set(re.findall(r'https?://[^"\'>\s]{10,140}\.pdf[^"\'>\s]*', fh)))
                    rec["pdfs"] = pdfs[:5]
                    # titulo y metadata visible
                    m = re.search(r'<title>([^<]{5,200})</title>', fh)
                    rec["titulo"] = m.group(1).split(' - ')[0] if m else slug
                    ok += 1
                except Exception as e:
                    rec["err"] = str(e)[:60]
                    # renovar sesion
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    time.sleep(10)
                    ctx, page = nueva_sesion(browser)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                hechos.add(slug)
                if n % 50 == 0:
                    out.flush()
                    print(f"  {n}/{len(slugs)} ok={ok}", flush=True)
                time.sleep(1.5)
        ctx.close()
        browser.close()
    print(f"FICHAS COMPLETAS: {ok}", flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "indice":
        indice(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
    else:
        fichas_run()
