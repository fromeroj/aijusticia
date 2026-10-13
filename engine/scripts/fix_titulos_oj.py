#!/usr/bin/env python3
"""Repara los títulos mojibake de OrdenJuridico.

El listing de ordenjuridico.gob.mx sirve windows-1252; el harvester viejo
decodificó utf-8 → títulos con U+FFFD ("Colaboraci�n"). Refresca las 32
páginas de listado y actualiza titulo por registro (ORDJ:<id>).
Uso (server): .venv/bin/python scripts/fix_titulos_oj.py
"""
import re
import sys
import time

sys.path.insert(0, "/opt/aijusticia/engine")
from curl_cffi import requests as creq

from ai_justicia.config import settings
import psycopg

BASE = "https://ordenjuridico.gob.mx"
_FICHA_RE = re.compile(
    r"href\s*=\s*javascript:void\(window\.open\(\"fichaOrdenamiento\.php\?idArchivo=(\d+)&ambito=estatal"
)
_TITULO_RE = re.compile(r">\s*([^<>]{10,300}?)\s*</a>", re.I)


def main():
    s = creq.Session(impersonate="chrome", timeout=60, headers={"Referer": BASE})
    s.get(f"{BASE}/", timeout=30)
    time.sleep(1)

    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor()
        fijados = 0
        for edo in range(1, 33):
            try:
                r = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0", timeout=60)
                t = r.content.decode("windows-1252", errors="replace")
                if "incap_ses" in t or "Loading" in t[:3000]:
                    s.get(f"{BASE}/", timeout=30)
                    time.sleep(3)
                    t = s.get(f"{BASE}/despliegaedo2.php?ordenar=&edo={edo}&idi=&catTipo=0",
                              timeout=60).content.decode("windows-1252", errors="replace")
            except Exception as e:
                print(f"edo {edo}: red {str(e)[:60]}", flush=True)
                continue
            n_edo = 0
            for m in _FICHA_RE.finditer(t):
                id_arch = m.group(1)
                seg = t[m.end(): m.end() + 400]
                mt = _TITULO_RE.search(seg)
                if not mt:
                    continue
                titulo = re.sub(r"\s+", " ", mt.group(1)).strip()
                cur.execute(
                    "UPDATE documentos SET titulo=%s "
                    "WHERE fuente='OrdenJuridico' AND registro_sjf=%s AND titulo LIKE %s",
                    (titulo, f"ORDJ:{id_arch}", "%\ufffd%"))
                fijados += cur.rowcount
                n_edo += cur.rowcount
            conn.commit()
            print(f"edo {edo}: {n_edo} títulos arreglados", flush=True)
        print(f"TOTAL: {fijados} títulos reparados", flush=True)


if __name__ == "__main__":
    main()
