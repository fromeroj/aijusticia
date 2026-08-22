"""Recuperación híbrida: fusión BM25 + vectorial.

La búsqueda híbrida mejora la precisión del anclaje ~20% frente a la puramente
semántica (dato del plan). Aquí normalizamos scores de ambas listas (min-max),
las combinamos con un peso, y deduplicamos por chunk_id manteniendo el score máximo.

Filtros (fuente, jurisdicción, vigencia, jerarquía) se aplican solo a la rama
vectorial (la BM25 carga solo vigentes en memoria).
"""

from __future__ import annotations

import logging

from ai_justicia.retrieval.bm25_index import get_bm25_index
from ai_justicia.retrieval.vector_index import Filtros, Resultado, busqueda_vectorial

logger = logging.getLogger(__name__)

# Peso de cada rama en la fusión (vectorial algo mayor: capta mejor intención semántica)
PESO_VECTORIAL = 0.6
PESO_BM25 = 0.4


def _normalizar(resultados: list[Resultado]) -> list[Resultado]:
    """Normaliza scores al rango [0, 1] (min-max)."""
    if not resultados:
        return resultados
    scores = [r.score for r in resultados]
    lo, hi = min(scores), max(scores)
    rango = hi - lo
    if rango == 0:
        # Todos iguales: asignar 1.0
        return [Resultado(**{**r.__dict__, "score": 1.0}) for r in resultados]
    norm = []
    for r in resultados:
        nr = Resultado(**{**r.__dict__, "score": (r.score - lo) / rango})
        norm.append(nr)
    return norm


def busqueda_hibrida(
    query: str,
    filtros: Filtros | None = None,
    top_k: int = 8,
) -> list[Resultado]:
    """Recupera pasajes combinando BM25 + vectorial.

    Devuelve `top_k` resultados ordenados por score fusionado (desc).
    """
    # Rama vectorial (con filtros)
    vec = busqueda_vectorial(query, filtros=filtros, top_k=top_k * 2)
    # Rama BM25 (sin filtros: ya filtra vigentes al cargar)
    bm25 = get_bm25_index().search(query, top_k=top_k * 2)

    vec_n = _normalizar(vec)
    bm25_n = _normalizar(bm25)

    # Fusionar por chunk_id, sumando scores ponderados
    fusion: dict[int, Resultado] = {}
    for r in vec_n:
        base = fusion.get(r.chunk_id)
        s = PESO_VECTORIAL * r.score
        if base is None:
            fusion[r.chunk_id] = Resultado(**{**r.__dict__, "score": s})
        else:
            base.score += s

    for r in bm25_n:
        base = fusion.get(r.chunk_id)
        s = PESO_BM25 * r.score
        if base is None:
            fusion[r.chunk_id] = Resultado(**{**r.__dict__, "score": s})
        else:
            base.score += s

    final = sorted(fusion.values(), key=lambda x: x.score, reverse=True)[:top_k]
    logger.debug(
        "Híbrido '%s': vectorial=%d, bm25=%d, fusionado=%d",
        query[:40], len(vec_n), len(bm25_n), len(final),
    )
    return final
