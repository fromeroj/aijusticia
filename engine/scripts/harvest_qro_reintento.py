#!/usr/bin/env python3
"""Fase reintento PDF Querétaro: las ~93K claves conocidas (estado2.json) cuyo
PDF falló en la pasada 1 (14K exitosas). Reintento con backoff y pausas.

Corre EN EL SERVER. Uso: python3 harvest_qro_reintento.py
"""
import io
import json
import re
import ssl
import time
import urllib.parse
import urllib.request

BASE = "https://www.poderjudicialqro.gob.mx/APP_UT69ii"
DIR = "/opt/aijusticia/corpus_downloads/queretaro"
JSONL = f"{DIR}/sentencias_qro.jsonl"
CLAVES_OK = f"{DIR}/claves_ok.json"
ESTADO = f"{DIR}/estado_reintento.json"

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
      "Referer": f"{BASE}/sentencias-publicas.php"}

import os
os.makedirs(DIR, exist_ok=True)


def http(url, data=None, timeout=60):
    body = urllib.parse.urlencode(data).encode() if data else None
    headers = {**UA, "Content-Type": "application/x-www-form-urlencoded"} if data else UA
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout, context=CTX) as r:
        return r.read()


def pdf_de(clave):
    tok = json.loads(http(f"{BASE}/crear_token.php", {"cual": clave}).decode())["token"]
    return http(f"{BASE}/leeDoc.php?cual=" + urllib.parse.quote(tok), timeout=120)


def procesar(clave):
    for intento in range(3):
        try:
            data = pdf_de(clave)
            if data[:4] != b"%PDF" or len(data) > 40e6:
                return None
            from pypdf import PdfReader
            rd = PdfReader(io.BytesIO(data))
            texto = "\n".join(p.extract_text() or "" for p in rd.pages[:400])
            texto = texto.encode("utf-8", errors="ignore").decode("utf-8")
            if len(texto) < 400:
                return None
            return texto, len(rd.pages)
        except Exception:
            time.sleep(1.5 * (intento + 1))
    return None


def main():
    # claves ya extraídas (en JSONL)
    ok_claves = set()
    if os.path.exists(CLAVES_OK):
        ok_claves = set(json.loads(open(CLAVES_OK).read()))
    else:
        for line in open(JSONL):
            ok_claves.add(json.loads(line)["clave"])
        open(CLAVES_OK, "w").write(json.dumps(list(ok_claves)))
    todas = set(json.loads(open(f"{DIR}/estado2.json").read()))
    pendientes = sorted(todas - ok_claves)
    hechos = set()
    if os.path.exists(ESTADO):
        hechos = set(json.loads(open(ESTADO).read()))
    pendientes = [c for c in pendientes if c not in hechos]
    print(f"Qro reintento: {len(pendientes)} claves sin PDF ({len(ok_claves)} ya ok)", flush=True)

    import concurrent.futures as cf
    import threading
    lock = threading.Lock()
    ok = fail = 0
    with open(JSONL, "a") as out:
        with cf.ThreadPoolExecutor(max_workers=1) as ex:
            for i, (clave, res) in enumerate(zip(pendientes, ex.map(procesar, pendientes))):
                if res:
                    texto, npag = res
                    partes = clave.split("|")
                    anio = 2000 + int(partes[3]) if len(partes) > 3 and partes[3].isdigit() and len(partes[3]) == 2 else None
                    with lock:
                        out.write(json.dumps({
                            "titulo": f"Sentencia {clave}",
                            "materia": "", "fecha": f"{anio}" if anio else "",
                            "texto": texto[:2_000_000], "paginas": npag, "clave": clave,
                        }, ensure_ascii=False) + "\n")
                    ok += 1
                else:
                    fail += 1
                hechos.add(clave)
                if (i + 1) % 100 == 0:
                    out.flush()
                    open(ESTADO, "w").write(json.dumps(list(hechos)))
                    print(f"  {i+1}/{len(pendientes)} ok={ok} fail={fail}", flush=True)
    open(ESTADO, "w").write(json.dumps(list(hechos)))
    print(f"REINTENTO FINAL: +{ok} PDFs, {fail} fallidos definitivos", flush=True)


if __name__ == "__main__":
    main()
