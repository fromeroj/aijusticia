#!/usr/bin/env python3
"""Limpieza profunda del corpus (texto de documentos, títulos y chunks).

Qué arregla (los problemas medidos en producción):
  - palabras partidas por guion de línea  ("palabra-\nbra" → "palabra")
  - saltos de línea triples+, espacios múltiples, tabs
  - números de página / "Página N de M" / encabezados de pie sueltos
  - caracteres de control y nulos (artefactos de antiword/strings/unrtf)
  - mojibake latino (Ã© → é, etc.)
  - encabezados de artículo en minúsculas → "Artículo N"
  - títulos con espaciado roto

Solo toca filas que de verdad cambian (prefilter SQL barato + comparación).
FTS (texto_search / titulo_search) es columna GENERATED → se reindexa sola.
Embeddings NO se regeneran (cambio de texto es cosmético; los vectores
siguen siendo válidos para recuperación semántica).

Uso (server): nohup .venv/bin/python scripts/limpieza_profunda.py > /tmp/limpieza.log 2>&1 &
"""
from __future__ import annotations

import re
import sys
import time
import unicodedata

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
import psycopg

PASO = 20_000

# --- prefiltros SQL (baratos, usan seq scan una vez por rango) ---
SUCIO_SQL = """
    texto ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'
    OR texto ~ '-\\n'
    OR texto ~ '\\n\\n\\n'
    OR texto ~ '   '
    OR texto ~ '\\n[ \\t]+'
    OR texto ~ '^[ \\t\\n]+'
    OR texto ~ '(?i)p[áa]gina\\s+\\d+'
    OR texto ~ '\\n\\d{1,4}\\n'
    OR texto LIKE '%Ã©%' OR texto LIKE '%Ã­%' OR texto LIKE '%Ã³%'
    OR texto LIKE '%Ãº%' OR texto LIKE '%Ã±%' OR texto LIKE '%Ã¡%'
"""

# --- normalización en Python ---
RE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
RE_PAGINA = re.compile(r"(?im)^\s*(?:p[áa]g(?:ina|\.)?\s+\d+(?:\s+(?:de|of)\s+\d+)?)\s*$")
RE_PAGINA_NUM = re.compile(r"(?m)^\s*\d{1,4}\s*$")
RE_GUION = re.compile(r"(\w)-\n(\w)")
RE_ESPACIOS = re.compile(r"[ \t]{2,}")
RE_SALTOS = re.compile(r"\n{3,}")
RE_LINEA_SP = re.compile(r"(?m)[ \t]+$")
RE_MOJIBAKE = re.compile(r"Ã[a-zA-Z]|[ÃÂ][\u0080-\u00bf¡¿°®¯´µ¶§]")
MOJI = {
    "Ã¡": "á", "Ã©": "é", "Ã­": "í", "Ã³": "ó", "Ãº": "ú",
    "Ã±": "ñ", "Ã¼": "ü", "Ã\u0081": "Á", "Ã‰": "É", "Ã\x8d": "Í",
    "Ã“": "Ó", "Ãš": "Ú", "Ã‘": "Ñ", "â€œ": '"', "â€\x9d": '"',
    "â€™": "'", "â€˜": "'", "â€“": "—", "â€”": "—", "Â«": "«", "Â»": "»",
    "Â¿": "¿", "Â¡": "¡", "Â°": "°", "Â´": "´", "Â·": "·",
}
RE_ART_MIN = re.compile(r"(?m)^art[íi]culo\s+(\d+)")


def limpiar(t: str) -> str:
    if not t:
        return t
    # mojibake conocido primero (sobre el texto crudo)
    for k, v in MOJI.items():
        if k in t:
            t = t.replace(k, v)
    if RE_MOJIBAKE.search(t):
        t = RE_MOJIBAKE.sub(" ", t)
    t = RE_CONTROL.sub("", t)
    t = unicodedata.normalize("NFC", t)
    t = t.replace("\ufffd", "")
    t = RE_PAGINA.sub("", t)
    t = RE_PAGINA_NUM.sub("", t)
    t = RE_GUION.sub(r"\1\2", t)          # palabra-\nbra → palabra
    t = RE_ESPACIOS.sub(" ", t)
    t = RE_LINEA_SP.sub("", t)
    t = RE_SALTOS.sub("\n\n", t)
    t = RE_ART_MIN.sub(r"Artículo \1", t)
    return t.strip("\n").strip() if t != t.strip("\n") else t


def titulo_limpio(t: str) -> str:
    t2 = re.sub(r"\s+", " ", t or "").replace("\ufffd", "").strip()
    return unicodedata.normalize("NFC", t2)


def procesar_tabla_chunks(cur) -> None:
    t0 = time.time()
    cur.execute("SELECT coalesce(max(id), 0) FROM documentos_chunks")
    max_id = cur.fetchone()[0]
    lo, n_scan, n_fix = 0, 0, 0
    print(f"chunks: max_id={max_id:,}", flush=True)
    while lo <= max_id:
        hi = lo + PASO
        cur.execute(f"""
            SELECT id, texto FROM documentos_chunks
            WHERE id > %s AND id <= %s AND ({SUCIO_SQL})
        """, (lo, hi))
        filas = cur.fetchall()
        n_scan += len(filas)
        fixes = []
        for cid, texto in filas:
            nuevo = limpiar(texto)
            if nuevo and nuevo != texto:
                fixes.append((nuevo, cid))
        if fixes:
            psycopg.execute_values(cur, """
                UPDATE documentos_chunks c SET texto = v.nuevo
                FROM (VALUES %s) AS v(nuevo, id)
                WHERE c.id = v.id
            """, fixes, page_size=500)
            conn.commit()
            n_fix += len(fixes)
            print(f"  [{hi:>12,}] scanned={n_scan:,} fixed={n_fix:,} "
                  f"({time.time()-t0:.0f}s)", flush=True)
        lo = hi
    print(f"CHUNKS LISTO: scanned={n_scan:,} fixed={n_fix:,} en {time.time()-t0:.0f}s", flush=True)


def procesar_documentos(cur) -> None:
    t0 = time.time()
    cur.execute("SELECT coalesce(max(id), 0) FROM documentos")
    max_id = cur.fetchone()[0]
    lo, n_scan, n_fix_txt, n_fix_tit = 0, 0, 0, 0
    print(f"documentos: max_id={max_id:,}", flush=True)
    while lo <= max_id:
        hi = lo + PASO
        cur.execute(f"""
            SELECT id, titulo, texto FROM documentos
            WHERE id > %s AND id <= %s
              AND (texto IS NOT NULL AND ({SUCIO_SQL})
                   OR titulo IS NOT NULL AND titulo ~ '\\s\\s|^[\\s]|[\\t]')
        """, (lo, hi))
        filas = cur.fetchall()
        n_scan += len(filas)
        for did, titulo, texto in filas:
            nuevo_t = titulo_limpio(titulo) if titulo else titulo
            nuevo_x = limpiar(texto) if texto else texto
            if nuevo_x != texto or nuevo_t != titulo:
                cur.execute(
                    "UPDATE documentos SET texto=%s, titulo=%s WHERE id=%s",
                    (nuevo_x if nuevo_x != texto else texto,
                     nuevo_t if nuevo_t != titulo else titulo, did))
                conn.commit()
                if nuevo_x != texto:
                    n_fix_txt += 1
                if nuevo_t != titulo:
                    n_fix_tit += 1
        lo = hi
    print(f"DOCS LISTO: scanned={n_scan:,} texto={n_fix_txt:,} titulos={n_fix_tit:,} "
          f"en {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    with psycopg.connect(settings.psycopg_dsn) as conn:
        # chunks primero (lo que ve la recuperación), luego docs
        with conn.cursor() as cur:
            procesar_tabla_chunks(cur)
        conn.commit()
        with conn.cursor() as cur:
            procesar_documentos(cur)
        conn.commit()
    print("LIMPIEZA COMPLETA", flush=True)
