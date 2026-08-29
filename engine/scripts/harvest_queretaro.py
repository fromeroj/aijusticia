#!/usr/bin/env python3
"""Harvesta TODAS las sentencias públicas del Poder Judicial de Querétaro. v2

Descubierto tras debuggeo:
  - El listado (leeSent.php) es GLOBAL ordenado por fecha desc; el parámetro
    de paginación es 'pagina' (NO 'pag'), 10 por página, ~13,700 páginas
    (~137K sentencias). Los filtros de fecha NO se aplican estrictamente.
  - 'pagina' funciona SIN recaptcha (la verificación solo aplica en la UI).
  - PDF: POST crear_token.php?cual=CLAVE -> JWT (60s TTL) -> GET leeDoc.php.

v1 (trimestral, param 'pag') solo vio 246 únicas — bug documentado.
Corre EN EL SERVER (puro HTTP). Uso: python3 harvest_queretaro.py v2
"""
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request

BASE = "https://www.poderjudicialqro.gob.mx/APP_UT69ii"
DIR = "/opt/aijusticia/corpus_downloads/queretaro"
JSONL = f"{DIR}/sentencias_qro.jsonl"
ESTADO = f"{DIR}/estado2.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Referer": f"{BASE}/sentencias-publicas.php"}

import os
os.makedirs(DIR, exist_ok=True)

FIN = 14000  # binario-search: vacío en 14000, lleno en 13500


def http(url, data=None):
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {**UA, "Content-Type": "application/x-www-form-urlencoded"} if data else UA
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return r.read()


def pagina(n):
    """Una página del listado global. Devuelve [{clave, celdas}]."""
    html = http(f"{BASE}/leeSent.php", {"pagina": n}).decode("utf-8", "replace")
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    metas = []
    for row in rows:
        m = re.search(r'abrePDF\("([^"]+)"\)', row)
        if not m:
            continue
        tds = [re.sub(r"<[^>]+>", "", td).strip()[:120]
               for td in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        metas.append({"clave": m.group(1), "celdas": tds})
    return metas


def pdf_de(clave):
    try:
        tok = json.loads(http(f"{BASE}/crear_token.php", {"cual": clave}).decode())["token"]
        return http(f"{BASE}/leeDoc.php?cual=" + urllib.parse.quote(tok))
    except Exception:
        return None


def main():
    hechos = set()
    if os.path.exists(ESTADO):
        hechos = set(json.loads(open(ESTADO).read()))
    print(f"Qro v2: hechos={len(hechos)}, hasta pagina {FIN}", flush=True)
    ok = dup = vac = 0
    with open(JSONL, "a") as out:
        for pg in range(1, FIN + 1):
            for intento in range(3):
                try:
                    metas = pagina(pg)
                    break
                except Exception as e:
                    if intento == 2:
                        metas = []
                        print(f"  [ERR pg {pg}] {str(e)[:50]}", flush=True)
                    time.sleep(3)
            if not metas:
                # fin del universo o página hueca — seguir hasta 2 vacías seguidas
                vac += 1
                if vac >= 20 and pg > 13000:
                    print(f"fin en pg {pg}", flush=True)
                    break
                continue
            vac = 0
            for m in metas:
                if m["clave"] in hechos:
                    dup += 1
                    continue
                data = pdf_de(m["clave"])
                rec = None
                if data and data[:4] == b"%PDF" and len(data) < 40e6:
                    try:
                        from pypdf import PdfReader
                        rd = PdfReader(io.BytesIO(data))
                        texto = "\n".join(p.extract_text() or "" for p in rd.pages[:400])
                        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
                        if len(texto) > 400:
                            c = m["celdas"]
                            rec = {
                                "titulo": f"Sentencia {c[5] if len(c)>5 else ''} {c[2] if len(c)>2 else ''} {c[6] if len(c)>6 else ''} {c[4] if len(c)>4 else ''}".strip()[:300],
                                "materia": c[2] if len(c) > 2 else "",
                                "fecha": c[4] if len(c) > 4 else "",
                                "texto": texto[:2_000_000], "paginas": len(rd.pages),
                                "clave": m["clave"],
                            }
                    except Exception:
                        pass
                if rec:
                    out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    ok += 1
                hechos.add(m["clave"])
            if pg % 50 == 0:
                out.flush()
                open(ESTADO, "w").write(json.dumps(list(hechos)))
                print(f"  pg {pg}/{FIN} ok={ok} conocidas={len(hechos)}", flush=True)
            time.sleep(0.5)
    open(ESTADO, "w").write(json.dumps(list(hechos)))
    print(f"QRO v2 FINAL: {ok} sentencias extraídas", flush=True)


if __name__ == "__main__":
    main()
