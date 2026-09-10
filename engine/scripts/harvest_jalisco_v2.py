#!/usr/bin/env python3
"""Harvesta IDs de sentencias Jalisco v2 — Playwright propio, no CDP.

Estrategia: lanza Chromium headless, navega al sitio (reCAPTCHA corre),
extrae IDs via fetch desde la página con credentials:include.
Cuando el backend hace rate limit: reload página → nueva cookie _vt → sigue.

Corre EN LA MAC. Uso:
    cd ~/workspace/aijusticia/engine
    .venv/bin/python scripts/harvest_jalisco_v2.py [--from-page N]
"""
import json
import sys
import time
from pathlib import Path

DIR = Path(__file__).resolve().parent.parent / "data" / "jalisco"
IDS = DIR / "ids.jsonl"
BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx"
FRONT = "https://publicacionsentencias.stjjalisco.gob.mx/sentencias"

# página de inicio (argumento o auto-detectar por IDs ya cosechados)
FROM_PAGE = 1
if "--from-page" in sys.argv:
    FROM_PAGE = int(sys.argv[sys.argv.index("--from-page") + 1])
else:
    existing = set()
    if IDS.exists():
        for line in IDS.read_text().strip().split("\n"):
            try:
                existing.add(json.loads(line)["id"])
            except Exception:
                pass
    FROM_PAGE = len(existing) // 10 + 1  # aproximación
    print(f"IDs existentes: {len(existing)} → reanudando desde página {FROM_PAGE}")

DIR.mkdir(parents=True, exist_ok=True)

from playwright.sync_api import sync_playwright

def cosechar(page, desde, max_pages=30, delay_ms=800):
    """Cosecha IDs desde la página activa via fetch con credentials."""
    ids = []
    last_ok = desde - 1
    limited = False
    for pg in range(desde, desde + max_pages):
        resultado = page.evaluate(
            """async ([pg]) => {
                const r = await fetch('%s/tocas?page=' + pg, {credentials: 'include'});
                const d = await r.json();
                if (d.status !== 'ok') return null;
                return d.data.tocas.data.map(t => ({id: t.id, toca: t.toca}));
            }""" % BACK,
            [pg],
        )
        if resultado is None:
            limited = True
            break
        last_ok = pg
        ids.extend(resultado)
        time.sleep(delay_ms / 1000)
    return ids, last_ok, limited

def main():
    p = sync_playwright().start()
    browser = p.chromium.launch(headless=False)
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        viewport={"width": 1280, "height": 800},
    )
    page = ctx.new_page()

    pagina_actual = FROM_PAGE
    total_nuevos = 0
    ids_vistos = set()
    if IDS.exists():
        for line in IDS.read_text().strip().split("\n"):
            try:
                ids_vistos.add(json.loads(line)["id"])
            except Exception:
                pass

    print(f"Iniciando: {len(ids_vistos)} IDs existentes, desde página {pagina_actual}")
    t0 = time.time()

    try:
        while pagina_actual <= 8475:
            # ir al sitio → reCAPTCHA → _vt nueva
            page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
            time.sleep(12)  # esperar grecaptcha

            # cosechar hasta rate limit
            ids, last_ok, limited = cosechar(page, pagina_actual, max_pages=25, delay_ms=600)

            nuevos = [t for t in ids if t["id"] not in ids_vistos]
            if nuevos:
                with open(IDS, "a") as f:
                    for t in nuevos:
                        f.write(json.dumps(t) + "\n")
                for t in nuevos:
                    ids_vistos.add(t["id"])

            total_nuevos += len(nuevos)
            pagina_actual = last_ok + 1
            elapsed = time.time() - t0
            rate = total_nuevos / max(elapsed / 60, 0.1)
            eta_min = (84745 - len(ids_vistos)) / max(rate, 1)
            print(f"  pág {last_ok}: +{len(nuevos)} (total {len(ids_vistos)})"
                  f" | {rate:.0f}/min | ETA {eta_min:.0f}min | limited: {limited}")

            if not limited:
                # llegamos al final
                break
            time.sleep(2)

    except KeyboardInterrupt:
        print(f"\nInterrumpido en página {pagina_actual}. Reanudar con --from-page {pagina_actual}")
    finally:
        browser.close()
        p.stop()
        print(f"\nFINAL: +{total_nuevos} nuevos IDs | total {len(ids_vistos)} | "
              f"páginas hasta {pagina_actual - 1} | {time.time() - t0:.0f}s")

if __name__ == "__main__":
    main()
