#!/usr/bin/env python3
"""Harvesta las 84,371 sentencias del STJ Jalisco — corre EN LA MAC.

Cadena descubierta:
  1. Cookie _vt del navegador persistente (CDP 9223) bypasea el recaptcha
     (ligada a IP: solo funciona desde esta Mac)
  2. GET /tocas?page=N (cookie) -> ids (per_page FIJO en 10; 8,438 páginas)
  3. GET /toca/{id}/file?modo=descargar (cookie) -> {url: S3 firmada}
  4. GET S3 (sin cookie) -> PDF

Auto-refresh: si el backend responde require_recaptcha, re-extrae la cookie
del navegador vivo via CDP.
"""
import concurrent.futures as cf
import io
import json
import re
import ssl
import sys
import time
import urllib.request
from pathlib import Path

BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx"
DIR = Path.home() / "workspace/aijusticia/engine/data/jalisco"
IDS = DIR / "ids.jsonl"
PDFS = DIR / "sentencias_jal.jsonl"
ESTADO_IDS = DIR / "estado_ids.json"
ESTADO_PDF = DIR / "estado_pdf.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}

DIR.mkdir(parents=True, exist_ok=True)
_cookie_cache = {"v": None, "ts": 0}


def cookie(force=False):
    """Cookie _vt fresca desde el navegador persistente (CDP).
    Si force: dispara NUEVA BÚSQUEDA + BUSCAR en la página viva para que
    grecaptcha renueve la _vt (TTL ~30 min)."""
    if not force and _cookie_cache["v"] and time.time() - _cookie_cache["ts"] < 600:
        return _cookie_cache["v"]
    import time as _t
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    browser = p.chromium.connect_over_cdp("http://127.0.0.1:9223")
    ctx = browser.contexts[0]
    if force:
        page = [pg for pg in ctx.pages if "sentencias" in pg.url][-1]
        for _ in range(3):
            try:
                page.click("button:has-text('NUEVA BÚSQUEDA')", timeout=4000)
                _t.sleep(1.5)
            except Exception:
                pass
            try:
                page.click("button:has-text('BUSCAR')", timeout=6000)
                _t.sleep(12)
            except Exception:
                pass
            # verificar dentro de la pagina
            ok = page.evaluate(
                "async () => { const r = await fetch('" + BACK + "/tocas?page=1', {credentials:'include'}); return (await r.json()).status === 'ok'; }")
            if ok:
                break
    cookies = ctx.cookies(BACK)
    p.stop()
    v = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    if not v:
        raise RuntimeError("sin cookies — ¿navegador vivo?")
    _cookie_cache.update(v=v, ts=time.time())
    return v


def fetch(url, use_cookie=True, timeout=60, retries=3):
    for k in range(retries):
        try:
            headers = dict(UA)
            if use_cookie:
                headers["Cookie"] = cookie(force=(k > 0))
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code in (403, 429) and k < retries - 1:
                cookie(force=True)  # refrescar y reintentar
                time.sleep(2 + k * 3)
                continue
            raise
    raise RuntimeError("reintentos agotados")


def fase_ids():
    """Recorre las 8,438 páginas del listado y extrae ids+file paths."""
    hechos = set()
    if ESTADO_IDS.exists():
        hechos = set(json.loads(ESTADO_IDS.read_text()))
    print(f"ids ya conocidos: {len(hechos)}", flush=True)
    # primera llamada: total y last_page
    d = json.loads(fetch(f"{BACK}/tocas?page=1"))
    tocas = d["data"]["tocas"]
    total, last = tocas["total"], tocas["last_page"]
    print(f"universo: {total} sentencias en {last} páginas", flush=True)
    out = open(IDS, "a")
    for pg in range(1, last + 1):
        try:
            d = json.loads(fetch(f"{BACK}/tocas?page={pg}"))
            items = d["data"]["tocas"]["data"]
        except Exception as e:
            print(f"  [ERR pg {pg}] {str(e)[:60]}", flush=True)
            time.sleep(5)
            continue
        nuevos = 0
        for it in items:
            iid = it["id"]
            if iid in hechos:
                continue
            out.write(json.dumps({
                "id": iid, "file": it.get("file"),
                "numero": it.get("numero"), "periodo": it.get("periodo"),
                "materia": (it.get("materia_data") or {}).get("nombre", ""),
                "sala": (it.get("salas_data") or {}).get("nombre", "")[:100],
                "fecha_pub": it.get("fecha_publicacion"),
            }, ensure_ascii=False) + "\n")
            hechos.add(iid)
            nuevos += 1
        if pg % 50 == 0:
            out.flush()
            ESTADO_IDS.write_text(json.dumps(list(hechos)))
            print(f"  pg {pg}/{last} ids={len(hechos)} (+{nuevos})", flush=True)
        time.sleep(0.35)
    out.flush()
    ESTADO_IDS.write_text(json.dumps(list(hechos)))
    print(f"FASE IDS COMPLETA: {len(hechos)}", flush=True)


def _pdf_de(item):
    try:
        d = json.loads(fetch(f"{BACK}/toca/{item['id']}/file?modo=descargar"))
        s3 = d["data"]["url"]
        data = urllib.request.urlopen(
            urllib.request.Request(s3, headers=UA), timeout=120, context=CTX).read()
        if data[:4] != b"%PDF" or len(data) > 50e6:
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages[:500])
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 500:
            return None
        return {
            "titulo": f"Sentencia toca {item.get('numero') or ''}/{item.get('periodo') or ''} {item.get('materia','')} {item.get('sala','')[:60]}".strip(),
            "materia": item.get("materia", ""), "anio": item.get("periodo"),
            "texto": texto[:2_500_000], "paginas": len(rd.pages),
            "url": f"{BACK}/toca/{item['id']}/file",
        }
    except Exception:
        return None


def fase_pdfs():
    items = [json.loads(l) for l in open(IDS)]
    hechos = set()
    if ESTADO_PDF.exists():
        hechos = set(json.loads(ESTADO_PDF.read_text()))
    pend = [i for i in items if i["id"] not in hechos]
    print(f"pdfs pendientes: {len(pend)} de {len(items)}", flush=True)
    n = ok = 0
    out = open(PDFS, "a")
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        for item, res in zip(pend, ex.map(_pdf_de, pend)):
            n += 1
            if res:
                out.write(json.dumps(res, ensure_ascii=False) + "\n")
                ok += 1
            hechos.add(item["id"])
            if n % 100 == 0:
                out.flush()
                ESTADO_PDF.write_text(json.dumps(list(hechos)))
                print(f"  {n}/{len(pend)} ok={ok}", flush=True)
    out.flush()
    ESTADO_PDF.write_text(json.dumps(list(hechos)))
    print(f"FASE PDFS COMPLETA: {ok}", flush=True)


if __name__ == "__main__":
    {"ids": fase_ids, "pdfs": fase_pdfs}[sys.argv[1]]()
