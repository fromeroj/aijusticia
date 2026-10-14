#!/usr/bin/env python3
"""Harvesta leyes consolidadas de Justia Mexico (PDFs oficiales en docs.mexico.justia.com).

Cubre estados con cobertura pobre en sus portales oficiales.
CORRER EN LA MAC (Playwright para el listado; los PDFs via HTTP directo).
"""
import io
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path.home() / "workspace/aijusticia/engine/data"
PDF_BASE = "https://docs.mexico.justia.com/estatales/{est}/leyes/{slug}.pdf"
LIST_URL = "https://mexico.justia.com/estatales/{est}/leyes/"

ESTADOS = {
    "col": "Colima",
    "slp": "San Luis Potosí",
    "mor": "Morelos",
    "roo": "Quintana Roo",
    "ags": "Aguascalientes",
    "chi": "Chihuahua",
    "qro": "Querétaro",
}

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def listar(page, slug_estado):
    leyes = {}
    url = LIST_URL.format(est=slug_estado)
    for intento in range(4):
        page.goto(url, timeout=45000, wait_until="domcontentloaded")
        for _ in range(14):
            t = page.title().lower()
            if "just a moment" not in t and "un momento" not in t and "attention" not in t:
                break
            time.sleep(6)
        time.sleep(2)
        n = len(page.eval_on_selector_all("a[href*='/leyes/']", "els => els.map(e => e.href)"))
        if n > 3:
            break
        print(f"  [challenge/retry {intento+1}]...", flush=True)
        time.sleep(10)
    pag = 1
    while True:
        links = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href + '\\t' + (e.innerText||'').trim())")
        nuevos = 0
        canon = slug_estado
        for l in links:
            m = re.search(r"/estatales/([^/]+)/leyes/([^/]+)/?", l.split("\t")[0])
            if m and m.group(2):
                canon = m.group(1)
                break
        for l in links:
            href, _, texto = l.partition("\t")
            if f"/estatales/{canon}/leyes/" in href and href.rstrip("/").split("/")[-1]:
                ley_slug = href.rstrip("/").split("/")[-1]
                if ley_slug not in leyes and len(texto) > 3:
                    leyes[ley_slug] = texto[:250]
                    nuevos += 1
        slug_estado = canon
        # paginacion
        siguiente = None
        for l in links:
            href = l.split("\t")[0]
            if f"?page={pag+1}" in href:
                siguiente = href
                break
        if not siguiente or pag > 30:
            break
        pag += 1
        page.goto(siguiente, timeout=40000, wait_until="domcontentloaded")
        time.sleep(1.5)
    return leyes, slug_estado


def bajar_pdf(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=90, context=CTX) as r:
        return r.read()


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            locale="es-MX")
        page = ctx.new_page()

        import os
        primer = True
        for slug, nombre in ESTADOS.items():
            if not primer:
                time.sleep(180)  # pausa anti rate-limit entre estados
            primer = False
            print(f"\n===== {nombre}", flush=True)
            try:
                leyes, canon = listar(page, slug)
            except Exception as e:
                print(f"  [ERR listado] {e}")
                continue
            print(f"  {len(leyes)} leyes listadas (canon={canon})", flush=True)
            recs, ok, err = [], 0, 0
            for ley_slug, titulo in sorted(leyes.items()):
                url = PDF_BASE.format(est=canon, slug=ley_slug)
                try:
                    data = bajar_pdf(url)
                    from pypdf import PdfReader
                    r = PdfReader(io.BytesIO(data))
                    texto = "\n".join(pg.extract_text() or "" for pg in r.pages)
                    if len(texto) < 400:
                        err += 1
                        continue
                    recs.append({"titulo": titulo, "tipo": "ley", "texto": texto, "url": url})
                    ok += 1
                except Exception as e:
                    err += 1
                    print(f"  [ERR] {titulo[:40]}: {str(e)[:50]}")
                time.sleep(0.25)
            out = OUT_DIR / f"leyes_justia_{slug}.jsonl"
            with open(out, "w") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            ntok = sum(len(r["texto"]) for r in recs) // 4
            print(f"[{nombre}] ok={ok} err={err} ~{ntok:,} tokens -> {out}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
