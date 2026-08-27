#!/usr/bin/env python3
"""SIVEPJ harvester v2 — exprime el TSJCDMX al maximo.

Mejoras v2:
- 4 shards por modulo de materia
- probe de juzgados vacios: si (2024,T04) y (2022,T02) dan 0, se salta el juzgado
- años en orden descendente (datos nuevos primero)
- JSONL + estado por shard (resume)

Correr EN LA MAC. Uso: python3 harvest_sivepj2.py <shard> <nshards>
"""
import io
import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

DATA = Path.home() / "workspace/aijusticia/engine/data"
BASE = "http://sivepj.poderjudicialcdmx.gob.mx:819/consulta/"
ANIOS = [str(a) for a in range(2026, 2018, -1)]
TRIMESTRES = ["T01", "T02", "T03", "T04"]
PROBES = [("2024", "T04"), ("2022", "T02")]


def extraer_pdf(context, url):
    try:
        r = context.request.get(url, timeout=90000)
        if not r.ok:
            return 0, ""
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(r.body()))
        return len(rd.pages), "\n".join(pg.extract_text() or "" for pg in rd.pages)
    except Exception:
        return 0, ""


def query(page, juz, anio, trim, wait=4.0):
    """Ejecuta una consulta; devuelve filas [{celdas, pdf}]."""
    for intento in (1, 2):
        try:
            try:
                page.locator(".modal:visible .modal-footer button").last.click(timeout=1200)
                time.sleep(0.4)
            except Exception:
                pass
            page.select_option("#juzgado", juz)
            page.select_option("#anio", anio)
            page.select_option("#trimestre", trim)
            time.sleep(0.5)
            page.click("#buscarSentencia", timeout=12000)
            time.sleep(wait)
            return page.evaluate("""() => {
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
        except Exception as e:
            if intento == 2:
                print(f"    [ERR] {juz} {anio} {trim}: {str(e)[:40]}", flush=True)
                return []
            time.sleep(3)


def main():
    shard, nshards = int(sys.argv[1]), int(sys.argv[2])
    jsonl = DATA / f"sivepj_sentencias_{shard}.jsonl"
    estado = DATA / f"sivepj_estado2_{shard}.json"
    hechos = set(tuple(x) for x in json.loads(estado.read_text())) if estado.exists() else set()
    vacios_path = DATA / f"sivepj_vacios_{shard}.json"
    vacios = set(tuple(x) for x in json.loads(vacios_path.read_text())) if vacios_path.exists() else set()
    # compat: heredar combos hechos de la v1 (mismos significados)
    viejo = DATA / f"sivepj_estado_{shard}.json"
    if viejo.exists():
        hechos |= set(tuple(x) for x in json.loads(viejo.read_text()))

    n_ok = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36",
            locale="es-MX", ignore_https_errors=True, viewport={"width": 1300, "height": 1000})
        page = ctx.new_page()
        page.goto(BASE, timeout=60000, wait_until="domcontentloaded")
        time.sleep(6)
        try:
            page.locator(".modal:visible .modal-footer button").last.click(timeout=8000)
            time.sleep(1)
        except Exception:
            pass
        page.check("#esSentencia")
        page.select_option("#materia", "PC")  # placeholder
        time.sleep(2)

        materias_all = page.eval_on_selector_all(
            "#materia option", "els => els.map(e => e.value).filter(v => v)")
        materias = [m for i, m in enumerate(materias_all) if i % nshards == shard]
        print(f"[shard {shard}] materias: {materias}", flush=True)

        out = open(jsonl, "a")
        for mat in materias:
            page.select_option("#materia", mat)
            time.sleep(3)
            juzgados = page.eval_on_selector_all(
                "#juzgado option", "els => els.map(e => e.value).filter(v => v)")
            print(f"[{mat}] {len(juzgados)} juzgados ({len(vacios)} vacios conocidos)", flush=True)
            for juz in juzgados:
                if (mat, juz) in vacios:
                    continue
                # probe de juzgado vacio (solo si no hay combos hechos de el)
                if not any(c[0] == mat and c[1] == juz for c in hechos):
                    probes = [query(page, juz, a, t) for a, t in PROBES]
                    if not any(probes):
                        vacios.add((mat, juz))
                        (DATA / f"sivepj_vacios_{shard}.json").write_text(json.dumps([list(x) for x in vacios]))
                        print(f"  [vacio] {juz}", flush=True)
                        continue
                nuevas = 0
                for anio in ANIOS:
                    for trim in TRIMESTRES:
                        combo = (mat, juz, anio, trim)
                        if combo in hechos:
                            continue
                        filas = query(page, juz, anio, trim)
                        for f in filas or []:
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
                            nuevas += 1
                        hechos.add(combo)
                        estado.write_text(json.dumps([list(x) for x in hechos]))
                        if filas:
                            print(f"  {juz} {anio} {trim}: {len(filas)} (ok={n_ok})", flush=True)
                        time.sleep(0.4)
                out.flush()
                if nuevas:
                    print(f"  [{juz}] +{nuevas} sentencias", flush=True)
        out.close()
        browser.close()
    print(f"[shard {shard}] FINAL: {n_ok} sentencias nuevas", flush=True)


if __name__ == "__main__":
    main()
