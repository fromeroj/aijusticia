#!/usr/bin/env python3
"""Harvesta TODAS las sentencias públicas del TSJCDMX via SIVEPJ.

CORRER EN LA MAC (IP mexicana). Días de ejecución — diseñado para resume.

Flujo: materia -> juzgados -> (juzgado × año × trimestre) -> filas con
metadata + URLs firmadas a PDF (gestordocumental). Se descarga cada PDF,
se extrae texto inline y se appendea al JSONL. Los PDFs NO se conservan
(serian ~300GB); solo el texto (~20GB esperado).

Estado: engine/data/sivepj_estado.json (combinaciones hechas).
Salida: engine/data/sivepj_sentencias.jsonl (append, una por linea).
"""
import io
import json
import re
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA = Path.home() / "workspace/aijusticia/engine/data"
import sys
_shard = sys.argv[1] if len(sys.argv) > 1 else "0"
JSONL = DATA / f"sivepj_sentencias_{_shard}.jsonl"
ESTADO = DATA / f"sivepj_estado_{_shard}.json"
BASE = "http://sivepj.poderjudicialcdmx.gob.mx:819/consulta/"

MATERIAS = None  # se descubren al cargar
ANIOS = [str(a) for a in range(2019, 2027)]
TRIMESTRES = ["T01", "T02", "T03", "T04"]


def cargar_estado():
    if ESTADO.exists():
        return set(tuple(x) for x in json.loads(ESTADO.read_text()))
    return set()


def guardar_estado(hechos):
    ESTADO.write_text(json.dumps([list(x) for x in hechos]))


def extraer_pdf(context, url):
    try:
        r = context.request.get(url, timeout=90000)
        if not r.ok:
            return 0, ""
        data = r.body()
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages)
        return len(rd.pages), texto
    except Exception:
        return 0, ""


def main():
    DATA.mkdir(exist_ok=True)
    hechos = cargar_estado()
    print(f"estado: {len(hechos)} combinaciones ya hechas", flush=True)
    n_total = n_ok = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            locale="es-MX", ignore_https_errors=True, viewport={"width": 1300, "height": 1000})
        page = ctx.new_page()
        page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
        time.sleep(6)
        # cerrar modal de anuncio legal
        try:
            page.locator(".modal:visible .modal-footer button").last.click(timeout=8000)
            time.sleep(1)
        except Exception:
            pass
        page.check("#esSentencia")

        # descubrir materias y juzgados por materia
        materias = page.eval_on_selector_all(
            "#materia option", "els => els.map(e => e.value).filter(v => v)")
        if len(sys.argv) > 1:
            shard, nshards = int(sys.argv[1]), int(sys.argv[2])
            materias = [m for i, m in enumerate(materias) if i % nshards == shard]
        print(f"materias de este shard: {len(materias)}", flush=True)
        print(f"materias: {len(materias)}", flush=True)

        out = open(JSONL, "a")
        for mat in materias:
            page.select_option("#materia", mat)
            time.sleep(3)
            juzgados = page.eval_on_selector_all(
                "#juzgado option", "els => els.map(e => e.value).filter(v => v)")
            print(f"[{mat}] {len(juzgados)} juzgados", flush=True)
            for juz in juzgados:
                for anio in ANIOS:
                    for trim in TRIMESTRES:
                        combo = (mat, juz, anio, trim)
                        if combo in hechos:
                            continue
                        try:
                            # cerrar modal/overlay que reaparece tras cada query
                            try:
                                page.locator(".modal:visible .modal-footer button").last.click(timeout=1500)
                                time.sleep(0.5)
                            except Exception:
                                pass
                            page.select_option("#juzgado", juz)
                            page.select_option("#anio", anio)
                            page.select_option("#trimestre", trim)
                            time.sleep(0.6)
                            page.click("#buscarSentencia", timeout=15000)
                            time.sleep(4.5)
                        except Exception as e:
                            print(f"  [ERR query] {combo}: {str(e)[:50]}", flush=True)
                            # reintento con force tras cerrar modal
                            try:
                                page.locator(".modal:visible .modal-footer button").last.click(timeout=2000)
                                page.click("#buscarSentencia", force=True, timeout=10000)
                                time.sleep(6)
                            except Exception as e2:
                                print(f"  [ERR retry] {combo}: {str(e2)[:40]}", flush=True)
                                time.sleep(4)
                                continue
                        # filas de resultados
                        filas = page.evaluate("""() => {
                            const trs = document.querySelectorAll('#tValores tr');
                            return Array.from(trs).map(tr => {
                                const tds = tr.querySelectorAll('td');
                                const a = tr.querySelector('a[href*="gestordocumental"]');
                                return {
                                    celdas: Array.from(tds).map(td => td.innerText.trim().slice(0, 120)),
                                    pdf: a ? a.href : null,
                                };
                            }).filter(r => r.pdf);
                        }""")
                        for f in filas:
                            c = f["celdas"]
                            npag, texto = extraer_pdf(ctx, f["pdf"])
                            if len(texto) < 500:
                                continue
                            rec = {
                                "materia": mat, "juzgado": juz, "anio": anio,
                                "tipo_juicio": c[5] if len(c) > 5 else "",
                                "fecha_sentencia": c[6] if len(c) > 6 else "",
                                "organo": c[8] if len(c) > 8 else "",
                                "juez": c[9] if len(c) > 9 else "",
                                "titulo": f"Sentencia {c[7] if len(c) > 7 else ''} {c[8] if len(c) > 8 else ''} ({c[6] if len(c) > 6 else ''})".strip(),
                                "texto": texto, "paginas": npag,
                            }
                            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            n_ok += 1
                        n_total += len(filas)
                        hechos.add(combo)
                        guardar_estado(hechos)
                        out.flush()
                        if filas:
                            print(f"  {juz} {anio} {trim}: {len(filas)} sentencias (total ok={n_ok})", flush=True)
                        time.sleep(1.2)
        out.close()
        browser.close()
    print(f"\nFINAL: {n_total} filas, {n_ok} sentencias con texto", flush=True)


if __name__ == "__main__":
    main()
