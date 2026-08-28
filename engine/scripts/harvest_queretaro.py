#!/usr/bin/env python3
"""Harvesta TODAS las sentencias públicas del Poder Judicial de Querétaro.

Cadena validada (puro HTTP, corre en el server):
  POST leeSent.php (fecINI/fecFIN + pagination offset) -> filas con clave estructural
  POST crear_token.php?cual=CLAVE -> JWT (expira en ~60s, renueva por PDF)
  GET  leeDoc.php?cual=JWT -> PDF binario

Clave: ORGANO|MATERIA|TIPO|AÑO(2d)|NUM|?  ej: OPJN01|P|E|25|22|1
Corre EN EL SERVER. Uso: python3 harvest_queretaro.py [año_inicio]
"""
import io
import json
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.poderjudicialqro.gob.mx/APP_UT69ii"
DIR = "/opt/aijusticia/corpus_downloads/queretaro"
JSONL = f"{DIR}/sentencias_qro.jsonl"
ESTADO = f"{DIR}/estado.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Referer": f"{BASE}/sentencias-publicas.php"}

import os
os.makedirs(DIR, exist_ok=True)


def http(url, data=None, is_json=False):
    if data is not None and is_json:
        body = json.dumps(data).encode()
        headers = {**UA, "Content-Type": "application/json"}
    elif data is not None:
        body = urllib.parse.urlencode(data).encode()
        headers = {**UA, "Content-Type": "application/x-www-form-urlencoded"}
    else:
        body, headers = None, UA
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=60, context=CTX) as r:
        return r.read()


def listar(fec_ini, fec_fin, offset):
    """Una página del listado (10 filas). Devuelve [(clave, fila_html), ...]"""
    # el frontend manda FormData; urlencode con los campos del form funciona igual
    data = {k: v for k, v in [("fecINI", fec_ini), ("fecFIN", fec_fin),
                              ("pag", offset)]}
    html = http(f"{BASE}/leeSent.php", data).decode("utf-8", "replace")
    filas = re.findall(r'abrePDF\("([^"]+)"\)', html)
    # metadata de cada fila: celdas
    rows = re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S)
    metas = []
    for row in rows:
        if "abrePDF" not in row:
            continue
        tds = [re.sub(r"<[^>]+>", "", td).strip() for td in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        clave = re.search(r'abrePDF\("([^"]+)"\)', row).group(1)
        metas.append({"clave": clave, "celdas": [c[:120] for c in tds]})
    return metas


def pdf(clave):
    tok = http(f"{BASE}/crear_token.php", {"cual": clave}).decode()
    token = json.loads(tok)["token"]
    return http(f"{BASE}/leeDoc.php?cual=" + urllib.parse.quote(token))


def procesar(meta, anio):
    try:
        data = pdf(meta["clave"])
        if data[:4] != b"%PDF":
            return None
        from pypdf import PdfReader
        rd = PdfReader(io.BytesIO(data))
        texto = "\n".join(pg.extract_text() or "" for pg in rd.pages)
        texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
        if len(texto) < 400:
            return None
        c = meta["celdas"]
        # celdas: [descarga, periodo, materia, delito/tipo, fecha, expediente, organo, ...]
        titulo = f"Sentencia {c[5] if len(c) > 5 else ''} {c[2] if len(c) > 2 else ''} {c[6] if len(c) > 6 else ''} {c[4] if len(c) > 4 else ''}".strip()
        return {"titulo": titulo[:300], "materia": c[2] if len(c) > 2 else "",
                "anio": anio, "texto": texto, "paginas": len(rd.pages),
                "clave": meta["clave"]}
    except Exception:
        return None


def main():
    anio0 = int(sys.argv[1]) if len(sys.argv) > 1 else 2008
    hechos = set()
    if os.path.exists(ESTADO):
        hechos = set(json.loads(open(ESTADO).read()))
    print(f"Querétaro desde {anio0}, hechos: {len(hechos)}", flush=True)
    ok = dup = vac = 0
    with open(JSONL, "a") as out:
        for anio in range(2026, anio0 - 1, -1):
            # barrido por trimestre (rangos mas cortos = paginacion manejable)
            for mes_ini, mes_fin in ((1, 3), (4, 6), (7, 9), (10, 12)):
                fec_ini = f"{anio}-{mes_ini:02d}-01"
                fec_fin = f"{anio}-{mes_fin:02d}-31"
                offset = 0
                while True:
                    try:
                        metas = listar(fec_ini, fec_fin, offset)
                    except Exception as e:
                        print(f"  [ERR] {fec_ini} off={offset}: {str(e)[:50]}", flush=True)
                        time.sleep(4)
                        break
                    if not metas:
                        break
                    nuevas = 0
                    for m in metas:
                        if m["clave"] in hechos:
                            dup += 1
                            continue
                        rec = procesar(m, anio)
                        if rec:
                            out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                            ok += 1
                            nuevas += 1
                        else:
                            vac += 1
                        hechos.add(m["clave"])
                    out.flush()
                    open(ESTADO, "w").write(json.dumps(list(hechos)))
                    offset += 10
                    if nuevas == 0 and offset > 30:  # solo dups: fin del rango
                        break
                    time.sleep(0.6)
                print(f"  {fec_ini}~{fec_fin}: acumulado ok={ok}", flush=True)
    open(ESTADO, "w").write(json.dumps(list(hechos)))
    print(f"FINAL QRO: ok={ok} vacios={vac} dups={dup}", flush=True)


if __name__ == "__main__":
    main()
