"""Recuperación híbrida: PostgreSQL FTS (preciso) + Vectorial (semántico).

Estrategia:
  1. FTS a nivel chunk con ts_rank_cd — busca coincidencias exactas de términos
     legales con stemming en español. Soporta filtros estructurales (materia, entidad).
  2. Vectorial (pgvector) — busca similitud semántica para conceptos que no
     coinciden literalmente (sinónimos, paráfrasis).
  3. Fusión: normalizar scores, combinar con pesos, deduplicar por chunk_id.
     FTS tiene más peso (precisión legal > ambigüedad semántica).

El FTS requiere un índice GIN sobre el tsvector de los chunks. Se crea al
indexar (ver asegurar_indice_fts()).
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import date

import numpy as np

from ai_justicia.config import settings

# ── Construcción de la tsquery con ponderación por rareza ─────────────────
# Problema que resuelve: con OR puro, una sentencia penal llena de "días" y
# "fechas" le gana al artículo del estatuto que contiene el término
# DISCRIMINATIVO de la consulta ("aguinaldo"). Solución: medir la frecuencia
# de cada término en el corpus (DF) y EXIGIR (&) los 1-2 más raros, dejando
# el resto como OR de apoyo.

_DF_CACHE: dict[str, int] = {}
_DF_RARO = 5_000           # tope de conteo: solo separa raro-vs-común barato


def _df(palabra: str) -> int:
    """Chunks que contienen la palabra, ACOTADO a 50_001 (cached).

    Un count(*) exacto sobre una palabra común ("días") matchea millones de
    chunks vía GIN y tarda minutos. Solo necesitamos el ORDEN de rareza:
    contar con tope 5001 da el número exacto para raras y se corta rápido
    para comunes (~200ms una vez por palabra, luego cache en el worker).
    """
    if palabra not in _DF_CACHE:
        if len(_DF_CACHE) > 20_000:
            _DF_CACHE.clear()
        try:
            with get_conn() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT count(*) FROM (SELECT 1 FROM documentos_chunks "
                        "WHERE texto_search @@ to_tsquery('spanish', %s) "
                        f"LIMIT {_DF_RARO + 1}) sub",
                        (palabra,))
                    _DF_CACHE[palabra] = cur.fetchone()[0]
        except Exception:
            _DF_CACHE[palabra] = 1_000_000  # falla ⇒ asumir común
    return _DF_CACHE[palabra]


def _construir_tsquery(palabras: list[str]) -> str:
    """(2 más raros &) & (resto |) — SIEMPRE requiere los 2 de menor DF.

    Un OR puro sobre términos comunes matchea millones de chunks (queries de
    minutos); requerir los 2 menos frecuentes acota el conjunto sin perder
    casi nada de recall (el resto queda como OR de apoyo).
    """
    if len(palabras) <= 2:
        return " | ".join(palabras)
    dfs = {p: _df(p) for p in palabras}
    ordenados = sorted(palabras, key=lambda p: dfs[p])
    requeridos = " & ".join(ordenados[:2])
    apoyo = ordenados[2:]
    if not apoyo:
        return requeridos
    return f"( {requeridos} ) & ( {' | '.join(apoyo)} )"
from ai_justicia.corpus.store import get_conn
from ai_justicia.retrieval.embeddings import embed_query
from ai_justicia.retrieval.reranker import rerankear
from ai_justicia.retrieval.vector_index import Filtros, Resultado

logger = logging.getLogger(__name__)

# Pesos de fusión: FTS mucho más fuerte (precisión legal), vectorial como respaldo
PESO_FTS = 0.75
PESO_VECTORIAL = 0.25


def asegurar_indice_fts() -> None:
    """Crea el índice GIN para FTS en documentos_chunks si no existe."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            # Añadir columna tsvector si no existe
            cur.execute("""
                ALTER TABLE documentos_chunks
                ADD COLUMN IF NOT EXISTS texto_search tsvector
                GENERATED ALWAYS AS (to_tsvector('spanish', texto)) STORED
            """)
            # Crear índice GIN
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_chunks_fts
                ON documentos_chunks USING GIN (texto_search)
            """)
        conn.commit()
    logger.info("Índice FTS (GIN) asegurado en documentos_chunks")


def busqueda_fts(
    query: str,
    filtros: Filtros | None = None,
    top_k: int = 10,
) -> list[Resultado]:
    """Búsqueda full-text a nivel chunk (dos fases + localizador de artículos).

    Fase 1 (barata): ts_rank_cd plano sobre el cuerpo → top 200.
    Fase 2 (cara): sobre ese pool, rank con título A-weight, multiplicador de
    fuente, penalización de basura/tablas y boost de estatuto.

    Localizador: si la consulta cita "artículo N", los chunks que EMPIEZAN con
    ese artículo (columna indexada articulo_num) entran al pool GARANTIZADOS
    vía UNION — el rank plano los dejaría fuera porque un artículo limpio
    pierde contra tablas con repetición densa de términos.
    """
    filtros = filtros or Filtros()

    where_clauses = []
    filtros_params: list = []

    if filtros.fuente:
        where_clauses.append("d.fuente = %s")
        filtros_params.append(filtros.fuente)
    if filtros.entidad:
        where_clauses.append("d.entidad = %s")
        filtros_params.append(filtros.entidad)
    if filtros.materia:
        # Filtro preferencial: la materia detectada + documentos sin materia
        # (la mayoría del SJF no tiene materia; excluirlos la perdería).
        where_clauses.append("(d.materia = %s OR d.materia IS NULL)")
        filtros_params.append(filtros.materia)
    if filtros.solo_vigentes:
        where_clauses.append("d.derogado = FALSE")
    if filtros.jerarquia_max is not None:
        where_clauses.append("d.jerarquia <= %s")
        filtros_params.append(filtros.jerarquia_max)

    where_sql = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

    stop = {
        "el", "la", "los", "las", "de", "del", "en", "y", "a", "que", "es", "un", "una",
        "mi", "si", "no", "al", "lo", "me", "se", "su", "para", "con", "por",
        "como", "más", "pero", "o", "u", "ni", "tan", "muy", "ya", "hay", "fue", "ser",
        "derecho", "derechos", "ley", "leyes", "artículo", "articulos", "cosa",
        "tengo", "hacer", "puedo", "qué", "cómo", "como", "dónde", "donde",
        "cuál", "cual", "cuándo", "cuando",
    }
    import re as _re
    clean_query = _re.sub(r"[¿?¡!.,;:()\"']", " ", query.lower())
    # números de artículo ("87", "1914") son términos ultra-discriminativos
    palabras = [w for w in clean_query.split()
                if w not in stop and (len(w) > 2 or w.isdigit())]

    or_query = _construir_tsquery(palabras)
    estricta = or_query != " | ".join(palabras)
    arts_citados = _re.findall(r"art[ií]culo\s+(\d{1,4})", clean_query)[:2]

    # UNION dirigido a los artículos citados (columna indexada)
    art_union = ""
    art_boost_sql = ""
    if arts_citados:
        art_union = (
            " UNION SELECT c.documento_id, c.ordinal, c.texto, c.texto_search, c.articulo_num, 1.0 AS base "
            "FROM documentos_chunks c JOIN documentos d ON d.id = c.documento_id "
            "WHERE c.articulo_num = ANY(%s)" + where_sql)
        art_boost_sql = (
            "CASE WHEN t.articulo_num = ANY(ARRAY[" + ",".join(arts_citados) + "]) "
            "THEN 12.0 ELSE 1.0 END * ")

    sql = f"""
        WITH top200 AS (
            SELECT c.documento_id, c.ordinal, c.texto, c.texto_search, c.articulo_num,
                   ts_rank_cd(c.texto_search, to_tsquery('spanish', %s)) AS base
            FROM documentos_chunks c
            JOIN documentos d ON d.id = c.documento_id
            WHERE c.texto_search @@ to_tsquery('spanish', %s)
            {where_sql}
            ORDER BY base DESC
            LIMIT 200
        ), pool AS (
            SELECT * FROM top200 {{ART_UNION}}
        )
        SELECT
            (t.documento_id * 1000000 + t.ordinal) AS chunk_id, t.documento_id, t.texto,
            __ART__ts_rank_cd(setweight(d.titulo_search, 'A') || t.texto_search,
                       to_tsquery('spanish', %s)) *
            CASE
                WHEN d.fuente = 'LeyesBiblio' THEN 1.5
                WHEN d.fuente = 'SJF' THEN 1.2
                WHEN d.fuente = 'DOF' THEN 1.1
                WHEN d.fuente IN ('GacetaEstatal', 'GacetaCDMX') THEN 0.7
                ELSE 1.0
            END *
            CASE
                WHEN t.texto ILIKE '%%CÁMARA DE DIPUTADOS%%' THEN 0.05
                WHEN t.texto ILIKE '%%Secretaría de Servicios%%' THEN 0.05
                WHEN t.texto ILIKE '%%Nuevo Código publicado%%' THEN 0.05
                WHEN t.texto ILIKE '%%DECRETO%%' AND t.texto ILIKE '%%reform%%' THEN 0.05
                WHEN t.texto ILIKE '%%ARTICULO PRIMERO%%' THEN 0.05
                WHEN t.texto ILIKE '%%ARTICULO SEGUNDO%%' THEN 0.05
                WHEN t.texto ILIKE '%%ARTICULO TERCERO%%' THEN 0.05
                WHEN t.texto ILIKE '%%Publicado en el Diario Oficial%%' AND length(t.texto) < 600 THEN 0.1
                WHEN t.texto ILIKE '%%DISPOSICIONES TRANSITORIAS%%' THEN 0.1
                WHEN t.texto ILIKE '%%Rúbrica%%' AND length(t.texto) < 500 THEN 0.1
                WHEN t.texto ILIKE '%%Presidente Constitucional%%' THEN 0.05
                WHEN length(t.texto) < 80 THEN 0.3
                -- tablas/nóminas: densidad numérica = no es texto normativo
                WHEN length(regexp_replace(t.texto, '[^0-9]', '', 'g'))::float
                     / greatest(length(t.texto), 1) > 0.12 THEN 0.08
                ELSE 1.0
            END *
            -- artículo de estatuto (texto normativo)
            CASE WHEN t.texto ~ '^\\s*Art[ií]culo\\s+[0-9]+' THEN 1.45 ELSE 1.0 END AS rank,
            d.fuente, d.titulo, d.materia, d.entidad, d.jerarquia, d.vinculante,
            d.registro_sjf, d.fecha_reforma, d.fecha_publicacion, d.fecha_vigencia, d.derogado
        FROM pool t
        JOIN documentos d ON d.id = t.documento_id
        ORDER BY rank DESC
        LIMIT %s
    """
    sql = sql.replace("{ART_UNION}", art_union).replace("__ART__", art_boost_sql)

    if arts_citados:
        # orden de placeholders: rank_int, match_int(+filtros), union ANY(+filtros), rank_ext, limit
        params = ([or_query] + filtros_params + [or_query]
                  + [[int(a) for a in arts_citados]] + filtros_params
                  + [or_query, top_k])
    else:
        params = [or_query] + filtros_params + [or_query, or_query, top_k]

    def _params_para(oq: str) -> list:
        if arts_citados:
            return ([oq] + filtros_params + [oq]
                    + [[int(a) for a in arts_citados]] + filtros_params
                    + [oq, top_k])
        return [oq] + filtros_params + [oq, oq, top_k]

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
            # la query estricta (2 más raros con &) no matcheó nada → OR puro
            if not rows and estricta:
                cur.execute(sql, _params_para(" | ".join(palabras)))
                rows = cur.fetchall()

    return [
        Resultado(
            chunk_id=r[0], documento_id=r[1], texto=r[2], score=float(r[3]),
            fuente=r[4], titulo=r[5], materia=r[6], entidad=r[7], jerarquia=r[8],
            vinculante=r[9], registro_sjf=r[10], fecha_reforma=r[11],
            fecha_publicacion=r[12], fecha_vigencia=r[13], derogado=r[14],
        )
        for r in rows
    ]


def busqueda_vectorial(
    query: str,
    filtros: Filtros | None = None,
    top_k: int = 10,
) -> list[Resultado]:
    """Búsqueda vectorial (pgvector) con filtros — la vía semántica."""
    filtros = filtros or Filtros()
    query_emb = np.array(embed_query(query), dtype=np.float32)

    where_clauses = []
    params: list = [query_emb]
    if filtros.fuente:
        where_clauses.append("d.fuente = %s")
        params.append(filtros.fuente)
    if filtros.entidad:
        where_clauses.append("d.entidad = %s")
        params.append(filtros.entidad)
    if filtros.materia:
        # Filtro "preferencial": incluye la materia detectada Y documentos
        # sin materia asignada (NULL). La mayoría de los 150K SJF no tienen
        # materia, y excluirlos perdería toda la jurisprudencia.
        where_clauses.append("(d.materia = %s OR d.materia IS NULL)")
        params.append(filtros.materia)
    if filtros.solo_vigentes:
        where_clauses.append("d.derogado = FALSE")
    if filtros.jerarquia_max is not None:
        where_clauses.append("d.jerarquia <= %s")
        params.append(filtros.jerarquia_max)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(query_emb)
    params.append(top_k)

    sql = f"""
        SELECT
            c.id AS chunk_id, c.documento_id, c.texto,
            1 - (c.embedding <=> %s) AS score,
            d.fuente, d.titulo, d.materia, d.entidad, d.jerarquia, d.vinculante,
            d.registro_sjf, d.fecha_reforma, d.fecha_publicacion, d.fecha_vigencia, d.derogado
        FROM documentos_chunks c
        JOIN documentos d ON d.id = c.documento_id
        {where_sql}
        ORDER BY c.embedding <=> %s
        LIMIT %s
    """

    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    return [
        Resultado(
            chunk_id=r[0], documento_id=r[1], texto=r[2], score=float(r[3]),
            fuente=r[4], titulo=r[5], materia=r[6], entidad=r[7], jerarquia=r[8],
            vinculante=r[9], registro_sjf=r[10], fecha_reforma=r[11],
            fecha_publicacion=r[12], fecha_vigencia=r[13], derogado=r[14],
        )
        for r in rows
    ]


def _normalizar(resultados: list[Resultado]) -> list[Resultado]:
    """Normaliza scores al rango [0, 1] (min-max)."""
    if not resultados:
        return resultados
    scores = [r.score for r in resultados]
    lo, hi = min(scores), max(scores)
    rango = hi - lo
    if rango == 0:
        return [Resultado(**{**r.__dict__, "score": 1.0}) for r in resultados]
    return [Resultado(**{**r.__dict__, "score": (r.score - lo) / rango}) for r in resultados]


def busqueda_hibrida_fts_vectorial(
    query: str,
    filtros: Filtros | None = None,
    top_k: int = 8,
) -> list[Resultado]:
    """Fusión FTS + vectorial: lo mejor de ambos mundos.

    1. FTS recupera pasajes con coincidencias exactas de términos legales.
    2. Vectorial recupera pasajes semánticamente similares.
    3. Se fusionan por chunk_id, promediando scores ponderados.
    4. FILTRO DE RELEVANCIA: solo se incluyen resultados que tienen coincidencia
       FTS (los vectorial-only se descartan si hay suficientes resultados FTS).
       Esto evita que leyes irrelevantes ("Navegación Marítima") se cuelen por
       similitud semántica ambigua.
    """
    fts_resultados = busqueda_fts(query, filtros=filtros, top_k=top_k * 2)
    vec_resultados = busqueda_vectorial(query, filtros=filtros, top_k=top_k * 2)

    fts_n = _normalizar(fts_resultados)
    vec_n = _normalizar(vec_resultados)

    # Fusionar por chunk_id
    fusion: dict[int, Resultado] = {}

    # FTS: siempre entran (son coincidencias exactas de términos)
    for r in fts_n:
        s = PESO_FTS * r.score
        fusion[r.chunk_id] = Resultado(**{**r.__dict__, "score": s})

    # Vectorial: solo AÑADE score a los que ya están vía FTS.
    # Los vectorial-only se descartan: para texto legal, la coincidencia exacta
    # de términos es más confiable que la similitud semántica ambigua.
    # Excepción: si FTS devuelve muy pocos resultados, permitir vectorial-only.
    permitir_vectorial_only = len(fts_n) < top_k

    for r in vec_n:
        base = fusion.get(r.chunk_id)
        if base is not None:
            # Dual-signal: FTS + vectorial → boost de confianza
            base.score += PESO_VECTORIAL * r.score
        elif permitir_vectorial_only:
            # No hay suficientes FTS, permitir vectorial-only como fallback
            fusion[r.chunk_id] = Resultado(**{**r.__dict__, "score": PESO_VECTORIAL * r.score})

    final = sorted(fusion.values(), key=lambda x: x.score, reverse=True)[:top_k]
    logger.debug(
        "FTS+Vec '%s': fts=%d, vec=%d, fusionado=%d",
        query[:40], len(fts_n), len(vec_n), len(final),
    )
    return final
