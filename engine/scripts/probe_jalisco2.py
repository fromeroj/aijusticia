"""Probe detallado: prueba 3 tocas y muestra el cuerpo de la respuesta."""
from playwright.sync_api import sync_playwright
import json

FRONT = "https://publicacionsentencias.stjjalisco.gob.mx/sentencias"
BACK = "https://publica-sentencias-backend.stjjalisco.gob.mx"
SITE_KEY = "6LeVK48tAAAAABtfSIPLusp-4cMthtofl497dZvX"
DIR = "/Users/fabianromero/workspace/aijusticia/engine/data/jalisco"

FETCH_JS = """
async (tocaId) => {
  const token = await grecaptcha.execute('%s', {action: 'visitor_verify'});
  const r = await fetch('%s/toca/' + tocaId + '/file?modo=descargar',
                        {headers: {'X-Recaptcha-Token': token}});
  const t = await r.text();
  return {status: r.status, body: t.slice(0, 200)};
}
""" % (SITE_KEY, BACK)

ids = []
for line in open(DIR + "/ids.jsonl"):
    d = json.loads(line)
    if d.get("file"):
        ids.append(d)
    if len(ids) >= 3:
        break

p = sync_playwright().start()
browser = p.chromium.launch(headless=False, channel="chrome", args=["--disable-blink-features=AutomationControlled"])
ctx = browser.new_context(
    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
    viewport={"width": 1280, "height": 800},
)
page = ctx.new_page()
page.goto(FRONT, timeout=90000, wait_until="domcontentloaded")
page.wait_for_timeout(12000)

for d in ids:
    try:
        res = page.evaluate(FETCH_JS, str(d["id"]))
        print(d["id"], d["file"], "->", res["status"], res["body"][:150].replace("\n", " "))
    except Exception as e:
        print(d["id"], "EXC:", str(e)[:150])
    page.wait_for_timeout(500)

browser.close()
p.stop()
