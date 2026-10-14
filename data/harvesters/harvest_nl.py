#!/usr/bin/env python3
"""Harvesta sentencias públicas del PJ Nuevo León (ASP.NET WebForms).

Grid con __doPostBack('...gdvCivil','Page$N') — 10 filas por página,
70+ páginas por materia. Cada fila: botón ImgBtnSentencia con postback que
abre el PDF (response stream). Manejamos el ViewState/EventValidation con
Playwright.
CORRER EN LA MAC (portal accesible, Playwright). Uso: python3 harvest_nl.py
"""
import io
import json
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA = Path.home() / "workspace/aijusticia/engine/data/nl"
DATA.mkdir(exist_ok=True)
JSONL = DATA / "sentencias_nl.jsonl"
ESTADO = DATA / "estado.json"

MATERIAS = {
    "Civiles.aspx": "Civil",
    "Penales.aspx": "Penal",
    "Familiar.aspx": "Familiar",
    "Mercantil.aspx": "Mercantil",
    "Laboral.aspx": "Laboral",
}


def parsear_filas(html):
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    out = []
    for row in rows:
        if "ImgBtnSentencia" not in row:
            continue
        tds = [re.sub(r"<[^>]+>", "", td).strip()[:100]
               for td in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        out.append(tds)
    return out


def main():
    hechos = set()
    if ESTADO.exists():
        hechos = set(json.loads(ESTADO.read_text()))
    print(f"NL: {len(hechos)} filas ya vistas", flush=True)
    ok = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            locale="es-MX", ignore_https_errors=True, viewport={"width": 1300, "height": 900})
        page = ctx.new_page()
        out = open(JSONL, "a")
        for aspx, materia in MATERIAS.items():
            url = f"https://www.pjenl.gob.mx/SentenciasPublicas/Modulos/{aspx}"
            try:
                page.goto(url, timeout=60000, wait_until="domcontentloaded")
                time.sleep(4)
            except Exception as e:
                print(f"[{materia}] nav err: {str(e)[:50]}", flush=True)
                continue
            pagina = 1
            sin_nuevas = 0
            while True:
                html = page.content()
                filas = parsear_filas(html)
                nuevas = 0
                for tds in filas:
                    clave = f"{materia}|{'|'.join(tds[:8])}"
                    if clave in hechos:
                        continue
                    hechos.add(clave)
                    nuevas += 1
                    out.write(json.dumps({
                        "materia": materia, "celdas": tds,
                    }, ensure_ascii=False) + "\n")
                    ok += 1
                # siguiente pagina via postback
                pagina += 1
                sig = f"Page${pagina}"
                try:
                    page.evaluate(
                        f"""__doPostBack('ctl00$ContentPlaceHolder1$gdv{materia}', '{sig}')""")
                    time.sleep(3.5)
                    # si tras el postback no cambia el contenido, fin
                    if not parsear_filas(page.content()):
                        break
                except Exception:
                    break
                if nuevas == 0:
                    sin_nuevas += 1
                    if sin_nuevas >= 4:
                        # ASP.NET devuelve la ultima pagina para siempre tras el fin
                        break
                else:
                    sin_nuevas = 0
                if pagina % 20 == 0:
                    out.flush()
                    ESTADO.write_text(json.dumps(list(hechos)))
                    print(f"  [{materia}] pg {pagina} filas={len(hechos)}", flush=True)
            print(f"[{materia}] completo: {pagina} páginas", flush=True)
            out.flush()
            ESTADO.write_text(json.dumps(list(hechos)))
        out.close()
        browser.close()
    print(f"NL FINAL: {ok} filas indexadas", flush=True)


if __name__ == "__main__":
    main()
