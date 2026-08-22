"""Exploración profunda de estados JS-rendered con Playwright.

Navega a las páginas específicas de leyes (no solo la home) y extrae PDFs.
"""
import asyncio
from playwright.async_api import async_playwright

# URLs específicas de leyes por estado (páginas más profundas)
DEEP_URLS = {
    "San Luis Potosí": [
        "http://congresosanluis.gob.mx/legislacion/leyes",
        "http://congresosanluis.gob.mx/leyes",
        "http://congresosanluis.gob.mx/legislacion",
    ],
    "Zacatecas": [
        "https://www.congresozac.gob.mx/65/todojuridico&cat=LEY",
        "https://www.congresozac.gob.mx/65/todojuridico&cat=CODIGO",
        "https://www.congresozac.gob.mx/65/todojuridico&cat=CONSTITUCION",
        "https://www.congresozac.gob.mx/65/leyes",
        "https://www.congresozac.gob.mx/65/marco-juridico",
    ],
    "Veracruz": [
        "https://www.legisver.gob.mx/Inicio.php?p=marco",
        "https://www.legisver.gob.mx/Inicio.php?p=legislacion",
        "https://www.legisver.gob.mx/LeyesEstatales",
        "https://www.legisver.gob.mx/MarcoJuridico",
        "https://www.legisver.gob.mx/consulta-leyes",
    ],
    "Sonora": [
        "https://congresoson.gob.mx/leyes",
        "https://congresoson.gob.mx/marco-juridico",
        "https://congresoson.gob.mx/legislacion",
        "https://congresoson.gob.mx/leyes-y-codigos",
    ],
    "Chiapas": [
        "https://web.congresochiapas.gob.mx/trabajo-legislativo/legislacion-vigente",
        "https://web.congresochiapas.gob.mx/leyes",
        "https://web.congresochiapas.gob.mx/marco-juridico",
        "https://web.congresochiapas.gob.mx/trabajo-legislativo",
    ],
    "Sinaloa": [
        "https://www.congresosinaloa.gob.mx/leyes-estatales/",
        "https://gaceta.congresosinaloa.gob.mx:3000/#/leyes",
        "https://www.congresosinaloa.gob.mx/marco-juridico",
    ],
}


async def try_url(page, name: str, url: str):
    try:
        await page.goto(url, wait_until="networkidle", timeout=20000)
        await page.wait_for_timeout(2000)
        links = await page.evaluate("""
            () => {
                const r = [];
                document.querySelectorAll('a').forEach(a => {
                    if (a.href && a.href.match(/\.(pdf|doc|docx)/i)) {
                        r.push({ href: a.href, text: a.textContent.trim().substring(0, 60) });
                    }
                });
                return r;
            }
        """)
        unique = list({l["href"]: l for l in links}.values())
        return len(unique), unique[:3]
    except Exception as e:
        return -1, [{"error": str(e)[:60]}]


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(ignore_https_errors=True)
        page = await context.new_page()

        for state, urls in DEEP_URLS.items():
            print(f"\n{'='*60}")
            print(f"  {state}")
            print(f"{'='*60}")

            best_count = 0
            best_url = None

            for url in urls:
                count, samples = await try_url(page, state, url)
                if count > 0:
                    print(f"  [{count:>4} PDFs] {url}")
                    for s in samples:
                        print(f"           {s.get('text','')[:40]:<40} → {s.get('href','')[:60]}")
                    if count > best_count:
                        best_count = count
                        best_url = url
                else:
                    print(f"  [    0    ] {url}")

            if best_url:
                print(f"\n  ✅ BEST: {best_url} ({best_count} PDFs)")
            else:
                print(f"\n  ❌ No PDFs found in any URL")

        await browser.close()

asyncio.run(main())
