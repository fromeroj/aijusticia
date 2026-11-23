#!/usr/bin/env python3
"""Limpieza profunda del corpus (texto de documentos, títulos y chunks).

Qué arregla:
  - palabras partidas por guion de línea  ("palabra-\\nbra" → "palabra")
  - saltos de línea triples+, espacios múltiples, tabs
  - números de página / "Página N de M" / encabezados de pie sueltos
  - caracteres de control y nulos (artefactos de antiword/strings/unrtf)
  - mojibake latino (Ã© → é, etc.)
  - encabezados de artículo en minúsculas → "Artículo N"
  - títulos con espaciado roto

Modos:
  (por defecto)  INCREMENTAL: sólo documentos actualizados en las últimas
                 --ventana-dias (2 por defecto). Es el que corre cada noche:
                 tras un barrido completo, lo único que puede estar sucio es
                 lo recién ingestado o re-ingerido.
  --completo     BARRIDO de toda la tabla. Reanudable: guarda el avance en
                 /opt/aijusticia/.estado_limpieza y lo borra al terminar. Semanal.
  --desde-id / --hasta-id / --sin-ventana / --solo     acotar (pruebas puntuales)

Dos reglas que este script respeta y que su versión anterior violaba:
  1. MEMORIA ACOTADA. Nunca hace fetchall() de textos largos: los documentos se
     leen uno por uno y los chunks en páginas keyset pequeñas. (10-23 nov 2026:
     la fase documentos cargaba de golpe un rango de ~17K tesis UNAM → 10.5GB de
     RSS → el kernel mató procesos con toda la máquina asfixiada.)
  2. CONVERGENCIA. Un barrido que reescanea desde el principio sin guardar avance
     nunca termina (la versión anterior rescaneaba las mismas 200K filas cada
     noche y arreglaba 0).

FTS (texto_search / titulo_search) es GENERATED en producción → se reindexa solo;
si en otra DB la columna existe y NO es generada, se recalcula al escribir.
Embeddings NO se regeneran (cambio cosmético).

Uso (en 162, siempre desde el mantenimiento nocturno, que le pone tope de memoria
y de tiempo):
  limpieza_profunda.py                     # incremental 48h  (cada noche)
  limpieza_profunda.py --completo          # barrido completo reanudable (semanal)
"""
from __future__ import annotations

import argparse
import os
import re
import resource
import sys
import time
import unicodedata

sys.path.insert(0, "/opt/aijusticia/engine")
from ai_justicia.config import settings
import psycopg

PASO_IDS = 2000          # documentos por página (en memoria sólo los ids)
PAGINA_CHUNKS = 2000     # filas de chunks traídas a la vez (paginación keyset)
LOTE_DOCS_CHUNKS = 100   # documentos por consulta de chunks en modo incremental
DIR_ESTADO = "/opt/aijusticia/.estado_limpieza"

# --- prefiltros SQL: sólo patrones que limpiar() realmente cambia -------------
# ({t} se sustituye por la columna; sin '%' para poder usar los %s de psycopg.
# Las llaves de los cuantificadores van dobles: esta cadena pasa por .format())
SUCIO_SQL = """(
    {t} ~ '[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f]'
    OR {t} ~ '-\\n'
    OR {t} ~ '\\n\\n\\n'
    OR {t} ~ '   '
    OR {t} ~ '^[ \\t\\n]+'
    OR {t} ~ '(?im)^\\s*p[áa]g(?:ina|\\.)?\\s+\\d+(?:\\s+(?:de|of)\\s+\\d+)?\\s*$'
    OR {t} ~ '\\n\\d{{1,4}}\\n'
    OR strpos({t}, 'Ã©') > 0 OR strpos({t}, 'Ã­') > 0 OR strpos({t}, 'Ã³') > 0
    OR strpos({t}, 'Ãº') > 0 OR strpos({t}, 'Ã±') > 0 OR strpos({t}, 'Ã¡') > 0
)"""
TITULO_SUCIO = r"\s\s|^\s|[\t]"

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


# --- estado de avance del barrido completo -----------------------------------

def _leer_estado(nombre: str):
    try:
        return tuple(int(x) for x in open(os.path.join(DIR_ESTADO, nombre)).read().split())
    except (OSError, ValueError):
        return None


def _guardar_estado(nombre: str, valores: tuple) -> None:
    os.makedirs(DIR_ESTADO, exist_ok=True)
    tmp = os.path.join(DIR_ESTADO, nombre + ".tmp")
    with open(tmp, "w") as f:
        f.write(" ".join(str(v) for v in valores))
    os.replace(tmp, os.path.join(DIR_ESTADO, nombre))


def _borrar_estado(nombre: str) -> None:
    try:
        os.remove(os.path.join(DIR_ESTADO, nombre))
    except OSError:
        pass


# --- consultas auxiliares ----------------------------------------------------

def _ventana(opts) -> tuple[str, list]:
    """Filtro por fecha: ninguno en barrido completo / --sin-ventana."""
    if opts.completo or opts.sin_ventana:
        return "true", []
    return "updated_at > now() - (%s || ' days')::interval", [str(opts.ventana_dias)]


def _rango(opts, col: str) -> tuple[str, list]:
    """`col >= desde [AND col <= hasta]` como sufijo del WHERE."""
    sql, params = f" AND {col} >= %s", [opts.desde_id]
    if opts.hasta_id is not None:
        sql += f" AND {col} <= %s"
        params.append(opts.hasta_id)
    return sql, params


def sucio_sql(col: str) -> str:
    """Prefiltro SQL para una columna. Único punto donde se aplica .format()."""
    return SUCIO_SQL.format(t=col)


def _columna(cur, tabla: str, columna: str) -> bool | None:
    """True si existe y es GENERATED, False si existe y es manual, None si no existe."""
    cur.execute("""SELECT is_generated FROM information_schema.columns
                   WHERE table_name = %s AND column_name = %s""", (tabla, columna))
    fila = cur.fetchone()
    return None if not fila else fila[0] == "ALWAYS"


# --- documentos --------------------------------------------------------------

def procesar_documentos(conn, cur, opts, titulo_manual: bool) -> dict:
    """Un documento a la vez; commit por página. Nunca hay más de UN texto en memoria."""
    t0 = time.time()
    estado = "docs_full.txt"
    ultimo = opts.desde_id
    previo = _leer_estado(estado) if opts.completo else None
    if previo:
        ultimo = max(ultimo, previo[0])
        print(f"docs: reanudando barrido desde id {ultimo:,}", flush=True)
    ventana_sql, ventana_params = _ventana(opts)
    rango_sql, rango_params = _rango(opts, "id")
    res = {"ids": 0, "texto": 0, "titulos": 0}
    sql_ids = f"""
        SELECT id FROM documentos
        WHERE id > %s
        {rango_sql}
          AND ({ventana_sql})
          AND ((texto IS NOT NULL AND ({sucio_sql('texto')}))
               OR (titulo IS NOT NULL AND titulo ~ %s))
        ORDER BY id
        LIMIT %s"""
    while True:
        cur.execute(sql_ids, [ultimo, *rango_params, *ventana_params, TITULO_SUCIO, PASO_IDS])
        ids = [r[0] for r in cur.fetchall()]
        if not ids:
            break
        for did in ids:
            cur.execute("SELECT titulo, texto FROM documentos WHERE id = %s", (did,))
            fila = cur.fetchone()
            if not fila:
                continue
            titulo, texto = fila
            if texto:
                nuevo_x = limpiar(texto)
                if nuevo_x != texto:
                    cur.execute("UPDATE documentos SET texto = %s WHERE id = %s", (nuevo_x, did))
                    res["texto"] += 1
            if titulo:
                nuevo_t = titulo_limpio(titulo)
                if nuevo_t != titulo:
                    if titulo_manual:
                        cur.execute("UPDATE documentos SET titulo = %s, "
                                    "titulo_search = to_tsvector('spanish', %s) WHERE id = %s",
                                    (nuevo_t, nuevo_t, did))
                    else:
                        cur.execute("UPDATE documentos SET titulo = %s WHERE id = %s", (nuevo_t, did))
                    res["titulos"] += 1
        conn.commit()
        ultimo = ids[-1]
        res["ids"] += len(ids)
        if opts.completo:
            _guardar_estado(estado, (ultimo,))
        if res["ids"] // 20000 != (res["ids"] - len(ids)) // 20000:
            print(f"  docs: revisados={res['ids']:,} texto={res['texto']:,} "
                  f"titulos={res['titulos']:,} ({time.time()-t0:.0f}s)", flush=True)
        if len(ids) < PASO_IDS:
            break
    if opts.completo and opts.hasta_id is None:
        _borrar_estado(estado)
    print(f"DOCS LISTO: scanned={res['ids']:,} texto={res['texto']:,} titulos={res['titulos']:,} "
          f"en {time.time()-t0:.0f}s", flush=True)
    return res


# --- chunks ------------------------------------------------------------------

def _pagina_chunks(cur, cond_extra: str, params_extra: list, ultimo: tuple) -> list:
    sql = f"""
        SELECT c.documento_id, c.ordinal, c.texto
        FROM documentos_chunks c
        WHERE (c.documento_id > %s OR (c.documento_id = %s AND c.ordinal > %s))
          AND ({sucio_sql('c.texto')})
          {cond_extra}
        ORDER BY c.documento_id, c.ordinal
        LIMIT %s"""
    cur.execute(sql, [ultimo[0], ultimo[0], ultimo[1], *params_extra, PAGINA_CHUNKS])
    return cur.fetchall()


def _procesar_pagina(conn, cur, filas: list, res: dict, recalcular_search: bool) -> None:
    fixes = []
    for did, ordinal, texto in filas:
        nuevo = limpiar(texto) if texto else texto
        if nuevo and nuevo != texto:
            fixes.append((nuevo, did, ordinal))
    for nuevo, did, ordinal in fixes:
        if recalcular_search:
            cur.execute("UPDATE documentos_chunks SET texto = %s, "
                        "texto_search = to_tsvector('spanish', %s) "
                        "WHERE documento_id = %s AND ordinal = %s", (nuevo, nuevo, did, ordinal))
        else:
            cur.execute("UPDATE documentos_chunks SET texto = %s "
                        "WHERE documento_id = %s AND ordinal = %s", (nuevo, did, ordinal))
    conn.commit()
    res["scanned"] += len(filas)
    res["fixed"] += len(fixes)


def procesar_chunks(conn, cur, opts, recalcular_search: bool) -> dict:
    t0 = time.time()
    res = {"scanned": 0, "fixed": 0}

    if opts.completo:
        estado = "chunks_full.txt"
        guardado = _leer_estado(estado)
        ultimo = guardado or (opts.desde_id, -1)
        if guardado:
            print(f"chunks: reanudando barrido desde {ultimo}", flush=True)
        rango_sql, rango_params = _rango(opts, "c.documento_id")
        while True:
            filas = _pagina_chunks(cur, rango_sql, rango_params, ultimo)
            if not filas:
                break
            _procesar_pagina(conn, cur, filas, res, recalcular_search)
            ultimo = (filas[-1][0], filas[-1][1])
            _guardar_estado(estado, ultimo)
            if res["scanned"] // 100000 != (res["scanned"] - len(filas)) // 100000:
                print(f"  chunks: revisados={res['scanned']:,} arreglados={res['fixed']:,} "
                      f"({time.time()-t0:.0f}s)", flush=True)
            if len(filas) < PAGINA_CHUNKS:
                break                 # ya no hay más filas sucias detrás
        if opts.hasta_id is None:
            _borrar_estado(estado)
            print("BARRIDO COMPLETO DE CHUNKS TERMINADO", flush=True)
    else:
        # incremental: sólo chunks de documentos actualizados en la ventana
        ventana_sql, ventana_params = _ventana(opts)
        rango_sql, rango_params = _rango(opts, "id")
        cur.execute(f"SELECT id FROM documentos WHERE ({ventana_sql}){rango_sql} ORDER BY id",
                    [*ventana_params, *rango_params])
        ids = [r[0] for r in cur.fetchall()]
        print(f"chunks incrementales: {len(ids):,} documentos en la ventana", flush=True)
        for i in range(0, len(ids), LOTE_DOCS_CHUNKS):
            lote = ids[i:i + LOTE_DOCS_CHUNKS]
            ultimo = (lote[0], -1)
            while True:
                filas = _pagina_chunks(cur, "AND c.documento_id = ANY(%s)", [lote], ultimo)
                if not filas:
                    break
                _procesar_pagina(conn, cur, filas, res, recalcular_search)
                ultimo = (filas[-1][0], filas[-1][1])
                if len(filas) < PAGINA_CHUNKS:
                    break             # fin de los chunks sucios de este lote

    print(f"CHUNKS LISTO: scanned={res['scanned']:,} fixed={res['fixed']:,} "
          f"en {time.time()-t0:.0f}s", flush=True)
    return res


# --- main --------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Limpieza profunda del corpus")
    ap.add_argument("--completo", action="store_true",
                    help="barrido de toda la tabla (reanudable)")
    ap.add_argument("--ventana-dias", type=int, default=2,
                    help="días hacia atrás del modo incremental (default: 2)")
    ap.add_argument("--sin-ventana", action="store_true",
                    help="ignorar la fecha de actualización (sólo para pruebas acotadas)")
    ap.add_argument("--desde-id", type=int, default=0, help="id de documento inicial")
    ap.add_argument("--hasta-id", type=int, default=None, help="id de documento final")
    ap.add_argument("--solo", choices=["docs", "chunks"], default=None,
                    help="procesar sólo documentos o sólo chunks")
    opts = ap.parse_args()
    if opts.sin_ventana and opts.desde_id == 0 and opts.hasta_id is None and not opts.completo:
        ap.error("--sin-ventana sin rango de ids recorrería toda la tabla: usa --completo o acota con ids")

    t0 = time.time()
    with psycopg.connect(settings.psycopg_dsn) as conn:
        cur = conn.cursor()
        titulo = _columna(cur, "documentos", "titulo_search")
        search = _columna(cur, "documentos_chunks", "texto_search")
        nombre = lambda c: "generada" if c else ("manual" if c is False else "ausente")  # noqa: E731
        print(f"esquema: documentos.titulo_search={nombre(titulo)} · "
              f"documentos_chunks.texto_search={nombre(search)}", flush=True)
        if opts.solo != "chunks":
            procesar_documentos(conn, cur, opts, titulo is False)
        if opts.solo != "docs":
            procesar_chunks(conn, cur, opts, search is False)
    pico = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    print(f"LIMPIEZA COMPLETA en {time.time()-t0:.0f}s · memoria pico {pico} MB", flush=True)


if __name__ == "__main__":
    main()
