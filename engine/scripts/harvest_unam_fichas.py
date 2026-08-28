#!/usr/bin/env python3
"""Fase fichas de tesis UNAM: descubre cuáles tienen PDF y lo extrae.

Del manifiesto (43,423 slugs), abre cada ficha con sesión caliente,
busca link de PDF/digitalización, y si existe extrae el texto.
Muestreo configurable — correr con muestra N para estimar disponibilidad.
CORRER EN LA MAC. Uso: python3 harvest_unam_fichas.py [total|muestra N]
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA = Path.home() / "workspace/aijusticia/engine/data"
MANIFEST = DATA / "unam_tesis_manifest.jsonl"
OUT = DATA / "unam_tesis_fichas.jsonl"
BASE = "https://repositorio.unam.mx"
UA = {"user_agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"}


def nueva_sesion(browser):
    ctx = browser.new_context(locale="es-MX", ignore_https_errors=True,
                              viewport={"width": 1300, "height": 900}, **UA)
    page = ctx.new_page()
    page.goto(f"{BASE}/contenidos", timeout=90000, wait_until="networkidle")
    time.sleep(5)
    return ctx, page


def main():
    modo = sys.argv[1] if len(sys.argv) > 1 else "muestra"
    slugs = [json.loads(l)["slug"] for l in open(MANIFEST)]
    if modo == "muestra":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        paso = max(1, len(slugs) // n)
        slugs = slugs[::paso][:n]
    hechos = set()
    if OUT.exists():
        hechos = {json.loads(l)["slug"] for l in open(OUT)}
    print(f"fichas a procesar: {len(slugs)} ({len(hechos)} ya hechas)", flush=True)

    ok_pdf = ok_meta = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx, page = nueva_sesion(browser)
        with open(OUT, "a") as out:
            for i, slug in enumerate(slugs, 1):
                if slug in hechos:
                    continue
                rec = {"slug": slug}
                try:
                    page.goto(f"{BASE}/contenidos/ficha/{slug}", timeout=60000,
                              wait_until="domcontentloaded")
                    time.sleep(3.5)
                    fh = page.content()
                    rec["len"] = len(fh)
                    m = re.search(r"<title>([^<]{5,180})</title>", fh)
                    rec["titulo"] = m.group(1).split(" - ")[0] if m else slug
                    # links de pdf
                    pdfs = sorted(set(re.findall(r'https?://[^"\'>\s]{10,150}\.pdf[^"\'>\s]*|/contenidos/[^"\'>\s]*\.(?:pdf|bitstream)[^"\'>\s]*', fh)))
                    rec["pdfs"] = pdfs[:4]
                    if pdfs:
                        ok_pdf += 1
                        # intentar descargar el primero por el contexto
                        try:
                            r = ctx.request.get(pdfs[0] if pdfs[0].startswith("http") else BASE + pdfs[0], timeout=90000)
                            data = r.body()
                            if data[:4] == b"%PDF":
                                import io
                                from pypdf import PdfReader
                                rd = PdfReader(io.BytesIO(data))
                                texto = "\n".join(pg.extract_text() or "" for pg in rd.pages[:600])
                                texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
                                rec["texto"] = texto[:3_000_000]
                                rec["paginas"] = len(rd.pages)
                        except Exception as e:
                            rec["dl_err"] = str(e)[:60]
                    else:
                        ok_meta += 1
                except Exception as e:
                    rec["err"] = str(e)[:80]
                    try:
                        ctx.close()
                    except Exception:
                        pass
                    time.sleep(8)
                    ctx, page = nueva_sesion(browser)
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                hechos.add(slug)
                if i % 10 == 0:
                    out.flush()
                    print(f"  {i}/{len(slugs)} con_pdf={ok_pdf} sin_pdf={ok_meta}", flush=True)
        ctx.close()
        browser.close()
    print(f"FINAL: {ok_pdf} con PDF, {ok_meta} solo metadatos de {len(slugs)}", flush=True)


if __name__ == "__main__":
    main()
