#!/usr/bin/env python3
"""Descarga reglamentos federales de LeyesBiblio (diputados.gob.mx).

Paginas: regley.htm (reglamentos de leyes) y norma/reglamento.htm (reglamentos federales).
WAF bloquea curl -> Playwright. PDFs a traves del contexto del navegador.
"""
import io
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path.home() / "workspace/aijusticia/engine/data/reglamentos_federales.jsonl"
PAGINAS = [
    ("https://www.diputados.gob.mx/LeyesBiblio/regley.htm", "reglamento-ley"),
    ("https://www.diputados.gob.mx/LeyesBiblio/norma/reglamento.htm", "reglamento-federal"),
    ("https://www.diputados.gob.mx/LeyesBiblio/norma/manual.htm", "manual"),
    ("https://www.diputados.gob.mx/LeyesBiblio/norma/estatuto.htm", "estatuto"),
]


def main():
    recs = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            locale="es-MX")
        page = ctx.new_page()
        for url, tipo in PAGINAS:
            print(f"===== {url}", flush=True)
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                time.sleep(2)
            except Exception as e:
                print(f"  [ERR nav] {str(e)[:80]}")
                continue
            links = page.eval_on_selector_all(
                "a[href]", "els => els.map(e => e.href + '\\t' + (e.innerText||'').trim())")
            pdfs = []
            for l in links:
                href, _, texto = l.partition("\t")
                if ".pdf" in href.lower():
                    titulo = re.sub(r"\s+", " ", texto).strip()[:250]
                    if not titulo:
                        titulo = href.rstrip("/").split("/")[-1].replace(".pdf", "").replace("_", " ")[:250]
                    pdfs.append((href, titulo))
            print(f"  {len(pdfs)} PDFs", flush=True)
            ok = err = 0
            for href, titulo in pdfs:
                try:
                    resp = page.context.request.get(href, timeout=60000)
                    if not resp.ok:
                        err += 1
                        continue
                    data = resp.body()
                    from pypdf import PdfReader
                    r = PdfReader(io.BytesIO(data))
                    texto = "\n".join(pg.extract_text() or "" for pg in r.pages)
                    if len(texto) < 400:
                        err += 1
                        continue
                    recs.append({"titulo": titulo, "tipo": tipo, "texto": texto, "url": href})
                    ok += 1
                    print(f"  [ok] {titulo[:55]} ({len(r.pages)}p)")
                except Exception as e:
                    err += 1
                    print(f"  [ERR] {titulo[:40]}: {str(e)[:50]}")
                time.sleep(0.25)
            print(f"  -> ok={ok} err={err}", flush=True)
        browser.close()

    with open(OUT, "w") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    ntok = sum(len(r["texto"]) for r in recs) // 4
    print(f"\nTotal: {len(recs)} reglamentos ~{ntok:,} tokens -> {OUT}")


if __name__ == "__main__":
    main()
