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
    OR strpos(texto, 'Ã©') > 0 OR strpos(texto, 'Ã­') > 0 OR strpos(texto, 'Ã³') > 0
    OR strpos(texto, 'Ãº') > 0 OR strpos(texto, 'Ã±') > 0 OR strpos(texto, 'Ã¡') > 0
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


def _schema(cur) -> dict:
    """Detecta diferencias entre DBs: 182 tiene chunks.id y texto_search
    GENERATED; 162 no tiene chunks.id y texto_search es columna mantenida."""
    cur.execute("""
        SELECT table_name, column_name, is_generated
        FROM information_schema.columns
        WHERE table_name IN ('documentos_chunks', 'documentos')
          AND column_name IN ('id', 'texto_search')
    """)
    cols = {(t, c): g for t, c, g in cur.fetchall()}
    return {
        "chunk_id": ("documentos_chunks", "id") in cols,
        "chunk_search_generated":
            cols.get(("documentos_chunks", "texto_search")) == "ALWAYS",
        "doc_search_generated":
            cols.get(("documentos", "texto_search")) == "ALWAYS",
    }


def procesar_tabla_chunks(cur, esquema: dict) -> None:
    t0 = time.time()
    n_scan = n_fix = 0

    if esquema["chunk_id"]:
        # 182: paginar por id
        cur.execute("SELECT coalesce(max(id), 0) FROM documentos_chunks")
        max_id = cur.fetchone()[0]
        print(f"chunks (por id): max_id={max_id:,}", flush=True)
        rangos = [("id", lo, lo + PASO) for lo in range(0, max_id + 1, PASO)]
        lo = 0
        while lo <= max_id:
            hi = lo + PASO
            cur.execute(f"""
                SELECT id, texto FROM documentos_chunks
                WHERE id > %s AND id <= %s AND ({SUCIO_SQL})
            """, (lo, hi))
            filas = cur.fetchall()
            fixes = [(limpiar(t), cid) for cid, t in filas
                     if (n := limpiar(t)) and n != t]
            n_scan += len(filas)
            if fixes:
                for n, cid in fixes:
                    if esquema["chunk_search_generated"]:
                        cur.execute(
                            "UPDATE documentos_chunks SET texto = %s WHERE id = %s",
                            (n, cid))
                    else:
                        cur.execute(
                            "UPDATE documentos_chunks SET texto = %s, "
                            "texto_search = to_tsvector('spanish', %s) WHERE id = %s",
                            (n, n, cid))
                conn.commit()
                n_fix += len(fixes)
                print(f"  [{hi:>12,}] scanned={n_scan:,} fixed={n_fix:,} "
                      f"({time.time()-t0:.0f}s)", flush=True)
            lo = hi
    else:
        # 162: keyset por (documento_id, ordinal)
        cur.execute("""
            SELECT documento_id, ordinal, texto FROM documentos_chunks
            WHERE ({sucio})
            ORDER BY documento_id, ordinal
            LIMIT 200000
        """.format(sucio=SUCIO_SQL))
        filas = cur.fetchall()
        fixes = []
        for did, ordinal, texto in filas:
            nuevo = limpiar(texto)
            if nuevo and nuevo != texto:
                fixes.append((nuevo, did, ordinal))
        n_scan = len(filas)
        if fixes:
            for n, did, ordinal in fixes:
                if esquema["chunk_search_generated"]:
                    cur.execute(
                        "UPDATE documentos_chunks SET texto = %s "
                        "WHERE documento_id = %s AND ordinal = %s",
                        (n, did, ordinal))
                else:
                    cur.execute(
                        "UPDATE documentos_chunks SET texto = %s, "
                        "texto_search = to_tsvector('spanish', %s) "
                        "WHERE documento_id = %s AND ordinal = %s",
                        (n, n, did, ordinal))
            conn.commit()
            n_fix = len(fixes)
        print(f"  scanned={n_scan:,} fixed={n_fix:,} "
              f"({time.time()-t0:.0f}s)", flush=True)
    print(f"CHUNKS LISTO: scanned={n_scan:,} fixed={n_fix:,} en {time.time()-t0:.0f}s", flush=True)


def procesar_documentos(cur, esquema_doc: dict) -> None:
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
                if esquema_doc["doc_search_generated"]:
                    cur.execute(
                        "UPDATE documentos SET texto=%s, titulo=%s WHERE id=%s",
                        (nuevo_x if nuevo_x != texto else texto,
                         nuevo_t if nuevo_t != titulo else titulo, did))
                else:
                    cur.execute(
                        "UPDATE documentos SET texto=%s, titulo=%s, "
                        "titulo_search=to_tsvector('spanish', %s) WHERE id=%s",
                        (nuevo_x if nuevo_x != texto else texto,
                         nuevo_t if nuevo_t != titulo else titulo,
                         (nuevo_t or ""), did))
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
        with conn.cursor() as cur:
            esquema = _schema(cur)
            print("schema:", esquema, flush=True)
        # chunks primero (lo que ve la recuperación), luego docs
        with conn.cursor() as cur:
            procesar_tabla_chunks(cur, esquema)
        conn.commit()
        with conn.cursor() as cur:
            procesar_documentos(cur, esquema)
        conn.commit()
    print("LIMPIEZA COMPLETA", flush=True)
