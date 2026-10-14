#!/usr/bin/env python3
"""Descarga leyes de estados criticos via Playwright (Cloudflare bypass).

Puebla: docman categories (gid 22,23,24,25) con limit=0
Guerrero: leyes-ordinarias/organicas/codigos (.php con PDFs)

Salida: engine/data/leyes_<estado>.jsonl {titulo, tipo, texto, url}
"""
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT_DIR = Path.home() / "workspace/aijusticia/engine/data"

PUEBLA_GIDS = {24: ("Constitución", "constitucion"), 23: ("Codigos", "codigo"),
               25: ("Leyes", "ley"), 22: ("Reglamentos", "reglamento")}
GUERRERO_CATS = {"leyes-ordinarias": "ley", "leyes-organicas": "ley-organica", "codigos": "codigo"}


def titulo_de_url(url: str) -> str:
    last = url.rstrip("/").split("/")[-1]
    last = re.sub(r"\.(pdf|docx?)$", "", last, flags=re.I)
    last = re.sub(r"[\d]{2,}.*$", "", last)  # fechas pegadas al final
    return last.replace("-", " ").replace("_", " ").strip()[:250]


def pdf_text(data: bytes) -> str:
    import io
    from pypdf import PdfReader
    try:
        r = PdfReader(io.BytesIO(data))
        return "\n".join(pg.extract_text() or "" for pg in r.pages)
    except Exception:
        return ""


def docx_text(data: bytes) -> str:
    import io
    import docx
    d = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in d.paragraphs if p.text.strip())


def descargar(page, urls_tipos, estado, max_mb=25):
    """urls_tipos: [(url, tipo, titulo_override)]. Devuelve records."""
    recs, ok, err = [], 0, 0
    for url, tipo, titulo in urls_tipos:
        try:
            resp = page.context.request.get(url, timeout=60000)
            if not resp.ok:
                err += 1
                print(f"  [ERR {resp.status}] {titulo[:60]}")
                continue
            body = resp.body()
            if len(body) > max_mb * 1e6 or len(body) < 2000:
                err += 1
                continue
            if url.lower().endswith(".docx") or body[:2] == b"PK":
                texto = docx_text(body)
            else:
                texto = pdf_text(body)
            if len(texto) < 300:
                err += 1
                print(f"  [vacio] {titulo[:60]}")
                continue
            recs.append({"titulo": titulo, "tipo": tipo, "texto": texto, "url": url})
            ok += 1
            print(f"  [ok] {titulo[:60]} ({len(texto)//1000}K chars)")
        except Exception as e:
            err += 1
            print(f"  [ERR] {titulo[:50]}: {str(e)[:60]}")
        time.sleep(0.3)
    print(f"\n[{estado}] ok={ok} err={err}")
    return recs


def puebla(page):
    print("===== PUEBLA", flush=True)
    urls = []
    for gid, (nombre, tipo) in PUEBLA_GIDS.items():
        url = (f"https://www.congresopuebla.gob.mx/index.php?option=com_docman"
               f"&task=cat_view&gid={gid}&limit=0&limitstart=0")
        for intento in range(3):
            try:
                page.goto(url, timeout=45000, wait_until="domcontentloaded")
                if "just a moment" in page.title().lower():
                    time.sleep(8)
                    continue
                break
            except Exception as e:
                print(f"  [nav err] {e}")
                time.sleep(5)
        time.sleep(2)
        links = page.eval_on_selector_all(
            "a[href]", "els => els.map(e => e.href + '\\t' + (e.innerText||'').trim())")
        for l in links:
            if "doc_download" in l and "gid=" in l:
                href, _, texto = l.partition("\t")
                # limpiar gid duplicado del link interno
                m = re.search(r"gid=(\d+)", href)
                if m:
                    href = (f"https://www.congresopuebla.gob.mx/index.php"
                            f"?option=com_docman&task=doc_download&gid={m.group(1)}")
                titulo = texto.strip()[:250] if len(texto.strip()) > 5 else titulo_de_url(href)
                urls.append((href, tipo, titulo))
        print(f"  gid={gid} ({nombre}): {len(urls)} acumulado", flush=True)
    vistos, limpios = set(), []
    for u, t, ti in urls:
        k = re.search(r"gid=(\d+)", u).group(1)
        if k not in vistos:
            vistos.add(k)
            limpios.append((u, t, ti))
    return descargar(page, limpios, "Puebla")


def guerrero(page):
    print("===== GUERRERO", flush=True)
    urls = []
    for cat, tipo in GUERRERO_CATS.items():
        try:
            page.goto(f"https://congresogro.gob.mx/legislacion/{cat}.php",
                      timeout=40000, wait_until="domcontentloaded")
            time.sleep(2)
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            pdfs = sorted({l for l in links if l.lower().endswith(".pdf")})
            for u in pdfs:
                urls.append((u, tipo, titulo_de_url(u)))
            print(f"  {cat}: {len(pdfs)} PDFs", flush=True)
        except Exception as e:
            print(f"  [ERR {cat}] {e}")
    return descargar(page, urls, "Guerrero")


def main():
    OUT_DIR.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            locale="es-MX", ignore_https_errors=True)
        page = ctx.new_page()
        for estado, fn in (("Puebla", puebla), ("Guerrero", guerrero)):
            recs = fn(page)
            out = OUT_DIR / f"leyes_{estado.lower()}.jsonl"
            with open(out, "w") as f:
                for r in recs:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            ntok = sum(len(r["texto"]) for r in recs) // 4
            print(f"[{estado}] {len(recs)} leyes ~{ntok:,} tokens -> {out}", flush=True)
        browser.close()


if __name__ == "__main__":
    main()
