"""Probe: abre el sitio de Jalisco, espera captcha, vuelca sesión y prueba descarga."""
from playwright.sync_api import sync_playwright
import requests

FRONT = "https://publicacionsentencias.stjjalisco.gob.mx/sentencias"
BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx"

p = sync_playwright().start()
browser = p.chromium.launch(headless=False)
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")
page = ctx.new_page()
page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
page.wait_for_timeout(15000)

ls = page.evaluate("() => Object.fromEntries(Object.entries(localStorage))")
ss = page.evaluate("() => Object.fromEntries(Object.entries(sessionStorage))")
print("localStorage keys:", {k: str(v)[:60] for k, v in ls.items()})
print("sessionStorage keys:", {k: str(v)[:60] for k, v in ss.items()})

# token candidado
token = None
for store in (ls, ss):
    for k, v in store.items():
        if "token" in k.lower():
            token = v.strip('"') if isinstance(v, str) else v
            print("token candidado en", k, ":", str(token)[:80])
if token:
    r = requests.get(f"{BACK}/toca/77056/file", params={"modo": "descargar"},
                     headers={"Authorization": f"Bearer {token}"}, timeout=60)
    print("con bearer:", r.status_code, r.headers.get("content-type"), len(r.content), r.content[:4])

# y probamos fetch in-page (el contexto autenticado del propio app)
res = page.evaluate("""async () => {
  const r = await fetch('https://publica-sentencias-backend.stjjalisco.gob.mx/toca/77056/file?modo=descargar', {credentials: 'include'});
  const b = await r.arrayBuffer();
  const magic = String.fromCharCode(...new Uint8Array(b.slice(0, 5)));
  return {status: r.status, len: b.byteLength, magic};
}""")
print("fetch in-page:", res)

browser.close()
p.stop()
