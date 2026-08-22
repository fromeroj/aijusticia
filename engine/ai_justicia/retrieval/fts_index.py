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
    """Búsqueda full-text a nivel chunk con ts_rank_cd y filtros estructurales.

    Más precisa que BM25 para texto legal: usa stemming en español y ranking
    por densidad de términos.
    """
    filtros = filtros or Filtros()

    where_clauses = []
    params: list = []

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

    where_sql = (" AND " + " AND ".join(where_clauses)) if where_clauses else ""

    # Usar to_tsquery con OR (|) en vez de plainto_tsquery (AND).
    # En texto legal, cualquier término que coincida es relevante.
    # Ej: "cargo no autorizado tarjeta" → cargo | autoriz | tarjeta
    # Esto encuentra más resultados relevantes que exigir TODAS las palabras.
    # Filtrar stopwords comunes + palabras legales ultra-genéricas que producen ruido.
    # "derecho" aparece en casi todas las leyes → no discrimina.
    # "ley" aparece en todos los títulos → no discrimina.
    stop = {
        # stopwords del español
        "el", "la", "los", "las", "de", "del", "en", "y", "a", "que", "es", "un", "una",
        "mi", "si", "no", "al", "lo", "me", "se", "su", "para", "con", "por", "las",
        "como", "más", "pero", "o", "u", "ni", "tan", "muy", "ya", "hay", "fue", "ser",
        # palabras legales genéricas que no discriminan materia
        "derecho", "derechos", "ley", "leyes", "artículo", "articulos", "cosa",
        "tengo", "hacer", "puedo", "qué", "que", "cómo", "como", "dónde", "donde",
        "cuál", "cual", "cuándo", "cuando", "qué",
    }
    # Limpiar puntuación antes de split
    import re as _re
    clean_query = _re.sub(r"[¿?¡!.,;:()\"']", " ", query.lower())
    palabras = [w for w in clean_query.split() if w not in stop and len(w) > 2]
    or_query = " | ".join(palabras)

    params = [or_query] + params + [or_query, top_k]

    # Multiplicador por fuente + penalización de chunks basura.
    # Los chunks de encabezados, decretos de reforma y transitorios
    # contienen palabras como "Código Civil" pero no artículos sustantivos.
    # Los penalizamos para que no dominate sobre artículos reales.
    sql = f"""
        SELECT
            c.id AS chunk_id, c.documento_id, c.texto,
            ts_rank_cd(c.texto_search, to_tsquery('spanish', %s)) *
            -- Multiplicador por fuente
            CASE
                WHEN d.fuente = 'LeyesBiblio' THEN 1.3
                WHEN d.fuente = 'SJF' THEN 1.2
                WHEN d.fuente = 'DOF' THEN 1.1
                WHEN d.fuente = 'GacetaEstatal' THEN 0.7
                ELSE 1.0
            END *
            -- Penalización de chunks basura (headers, decretos, transitorios)
            CASE
                -- Headers y metadatos institucionales
                WHEN c.texto ILIKE '%%CÁMARA DE DIPUTADOS%%' THEN 0.05
                WHEN c.texto ILIKE '%%Secretaría de Servicios%%' THEN 0.05
                WHEN c.texto ILIKE '%%Nuevo Código publicado%%' THEN 0.05
                -- Decretos de reforma y transitorios
                WHEN c.texto ILIKE '%%DECRETO%%' AND c.texto ILIKE '%%reform%%' THEN 0.05
                WHEN c.texto ILIKE '%%ARTICULO PRIMERO%%' THEN 0.05
                WHEN c.texto ILIKE '%%ARTICULO SEGUNDO%%' THEN 0.05
                WHEN c.texto ILIKE '%%ARTICULO TERCERO%%' THEN 0.05
                WHEN c.texto ILIKE '%%Publicado en el Diario Oficial%%' AND length(c.texto) < 600 THEN 0.1
                WHEN c.texto ILIKE '%%DISPOSICIONES TRANSITORIAS%%' THEN 0.1
                -- Firmas y rúbricas
                WHEN c.texto ILIKE '%%Rúbrica%%' AND length(c.texto) < 500 THEN 0.1
                WHEN c.texto ILIKE '%%Presidente Constitucional%%' THEN 0.05
                -- Chunks muy cortos (fragmentos sin contexto)
                WHEN length(c.texto) < 80 THEN 0.3
                ELSE 1.0
            END AS rank,
            d.fuente, d.titulo, d.materia, d.entidad, d.jerarquia, d.vinculante,
            d.registro_sjf, d.fecha_reforma, d.fecha_publicacion, d.fecha_vigencia, d.derogado
        FROM documentos_chunks c
        JOIN documentos d ON d.id = c.documento_id
        WHERE c.texto_search @@ to_tsquery('spanish', %s)
        {where_sql}
        ORDER BY rank DESC
        LIMIT %s
    """

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()

    # ts_rank_cd devuelve scores muy pequeños (0.001 - 0.1); normalizar después
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
