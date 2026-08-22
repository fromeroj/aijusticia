"""Explora estados JS-rendered con Playwright para extraer enlaces a PDFs.

Para cada estado:
1. Carga la página con Playwright (espera a que JS renderice)
2. Extrae todos los href con .pdf/.doc
3. Reporta el conteo

Uso:
    python scripts/explore_js_states.py
"""

import asyncio
import re
from playwright.async_api import async_playwright

STATES = {
    "Chiapas": "https://web.congresochiapas.gob.mx/trabajo-legislativo/legislacion-vigente",
    "Sonora": "https://congresoson.gob.mx/leyes",
    "Sinaloa": "https://www.congresosinaloa.gob.mx/leyes-estatales/",
    "San Luis Potosí": "http://congresosanluis.gob.mx/legislacion/leyes",
    "Zacatecas": "https://www.congresozac.gob.mx/65/inicio",
    "Veracruz": "https://www.legisver.gob.mx/",
}


async def explore_state(playwright, name: str, url: str):
    browser = await playwright.chromium.launch(headless=True)
    context = await browser.new_context(ignore_https_errors=True)
    page = await context.new_page()

    print(f"\n{'='*60}")
    print(f"  {name}: {url}")
    print(f"{'='*60}")

    try:
        await page.goto(url, wait_until="networkidle", timeout=30000)
        await page.wait_for_timeout(3000)  # extra time for JS

        title = await page.title()
        print(f"  Title: {title}")

        # Extraer todos los enlaces a PDFs/DOCs
        links = await page.evaluate("""
            () => {
                const results = [];
                document.querySelectorAll('a').forEach(a => {
                    const href = a.href;
                    const text = a.textContent.trim();
                    if (href && href.match(/\\.(pdf|doc|docx)/i)) {
                        results.push({ href, text: text.substring(0, 60) });
                    }
                });
                return results;
            }
        """)

        # Deduplicar por href
        unique = {}
        for l in links:
            if l["href"] not in unique:
                unique[l["href"]] = l

        pdfs = [l for l in unique.values() if l["href"].lower().endswith(".pdf")]
        docs = [l for l in unique.values() if l["href"].lower().endswith((".doc", ".docx"))]

        print(f"  PDFs únicos: {len(pdfs)}")
        print(f"  DOCs únicos: {len(docs)}")

        for l in list(unique.values())[:5]:
            print(f"    [{l['text'][:40]:<40}] {l['href'][:80]}")
        if len(unique) > 5:
            print(f"    ... y {len(unique)-5} más")

        # Si hay 0, buscar en iframes
        if len(unique) == 0:
            frames = page.frames
            print(f"  Iframes: {len(frames)}")
            for frame in frames[1:]:  # skip main
                try:
                    frame_links = await frame.evaluate("""
                        () => {
                            const results = [];
                            document.querySelectorAll('a').forEach(a => {
                                const href = a.href;
                                if (href && href.match(/\\.(pdf|doc|docx)/i)) {
                                    results.push({ href, text: a.textContent.trim().substring(0, 60) });
                                }
                            });
                            return results;
                        }
                    """)
                    if frame_links:
                        print(f"  Iframe '{frame.url[:50]}': {len(frame_links)} PDF/DOC links")
                        for l in frame_links[:3]:
                            print(f"    [{l['text'][:40]}] {l['href'][:80]}")
                except:
                    pass

        return {"state": name, "url": url, "pdfs": len(pdfs), "docs": len(docs), "links": list(unique.values())[:20]}

    except Exception as e:
        print(f"  ERROR: {e}")
        return {"state": name, "url": url, "error": str(e)}
    finally:
        await browser.close()


async def main():
    results = []
    async with async_playwright() as p:
        for name, url in STATES.items():
            result = await explore_state(p, name, url)
            results.append(result)

    print("\n" + "="*60)
    print("RESUMEN")
    print("="*60)
    for r in results:
        if "error" in r:
            print(f"  ❌ {r['state']:<20} ERROR: {r['error'][:50]}")
        else:
            print(f"  {'✅' if r['pdfs']+r['docs'] > 0 else '❌'} {r['state']:<20} {r['pdfs']} PDFs, {r['docs']} DOCs")

asyncio.run(main())
