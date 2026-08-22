"""Etapas 2 y 3 del pipeline: recuperación híbrida + reranking jurídico.

Etapa 2: recuperación híbrida (BM25 + vectorial) con filtros derivados del
análisis de consulta. Si la calidad cae bajo el umbral, se reformula la consulta
y se reintenta una vez antes de declarar evidencia insuficiente (reformulate-and-retry).

Etapa 3: reranking jurídico (jerarquía art. 133, vinculante vs persuasivo, vigencia).
"""

from __future__ import annotations

import logging

from ai_justicia.config import settings
from ai_justicia.pipeline.query_analysis import AnalisisConsulta, expandir_consulta
from ai_justicia.retrieval.fts_index import busqueda_hibrida_fts_vectorial as busqueda_hibrida
from ai_justicia.retrieval.reranker import rerankear
from ai_justicia.retrieval.vector_index import Filtros, Resultado

logger = logging.getLogger(__name__)


def recuperar_y_rerankear(
    consulta: str,
    analisis: AnalisisConsulta,
) -> list[Resultado]:
    """Ejecuta etapas 1.5 + 2 + 3: normalización, híbrido con retry, luego reranking.

    Devuelve los `rerank_top_k` pasajes finales.
    """
    filtros = _filtros_desde_analisis(analisis)

    # Etapa 1.5: Normalizar la consulta a terminología jurídica
    # "mi ex no me deja ver a mi hija" → "régimen de visitas patria potestad código civil"
    # Esto mejora DRÁSTICAMENTE el FTS: los términos jurídicos coinciden con las leyes.
    from ai_justicia.pipeline.query_analysis import normalizar_consulta_juridica
    consulta_normalizada = normalizar_consulta_juridica(consulta, materia=analisis.materia)
    if consulta_normalizada != consulta:
        logger.info("Consulta normalizada: %s → %s", consulta[:50], consulta_normalizada[:60])

    # Expandir la consulta con términos del dominio para desambiguar
    # La expansión SOLO se usa para vectorial (búsqueda semántica).
    consulta_expandida = expandir_consulta(analisis, consulta)
    if consulta_expandida != consulta:
        logger.info("Consulta expandida (vectorial): %s → %s", consulta[:50], consulta_expandida[:80])

    # Búsqueda híbrida: FTS con consulta NORMALIZADA, vectorial con expandida
    from ai_justicia.retrieval.fts_index import busqueda_fts, busqueda_vectorial, _normalizar, PESO_FTS, PESO_VECTORIAL
    from ai_justicia.retrieval.vector_index import Resultado as Res

    fts_resultados = busqueda_fts(consulta_normalizada, filtros=filtros, top_k=settings.retrieval_top_k * 2)
    vec_resultados = busqueda_vectorial(consulta_expandida, filtros=filtros, top_k=settings.retrieval_top_k * 2)

    # Filtrar FTS: solo mantener resultados con score >= 30% del top score.
    # Esto elimina coincidencias débiles de una sola palabra (ej: "autorizado"
    # apareciendo en Ley de Navegación Marítima).
    if fts_resultados:
        max_score = max(r.score for r in fts_resultados)
        fts_filtrados = [r for r in fts_resultados if r.score >= max_score * 0.25]
    else:
        fts_filtrados = []

    fts_n = _normalizar(fts_filtrados)
    vec_n = _normalizar(vec_resultados)

    # Fusionar: FTS prioridad, vectorial solo boost
    fusion: dict[int, Res] = {}
    for r in fts_n:
        fusion[r.chunk_id] = Res(**{**r.__dict__, "score": PESO_FTS * r.score})
    permitir_vec_only = len(fts_n) < settings.retrieval_top_k
    for r in vec_n:
        base = fusion.get(r.chunk_id)
        if base is not None:
            base.score += PESO_VECTORIAL * r.score
        elif permitir_vec_only:
            fusion[r.chunk_id] = Res(**{**r.__dict__, "score": PESO_VECTORIAL * r.score})

    resultados = sorted(fusion.values(), key=lambda x: x.score, reverse=True)[:settings.retrieval_top_k]

    # Reformulate-and-retry si la calidad es baja
    if _calidad_insuficiente(resultados):
        logger.info("Calidad baja (%.3f < %.3f). Reformulando y reintentando…",
                    resultados[0].score if resultados else 0, settings.retrieval_quality_threshold)
        # Intentar con la consulta expandida (sin filtros estrictos)
        resultados_alt = busqueda_hibrida(consulta_expandida, filtros=filtros, top_k=settings.retrieval_top_k)
        if _calidad_insuficiente(resultados_alt):
            # Segundo intento: quitar filtros estrictos (quizá la materia detectada es muy restrictiva)
            resultados_alt = busqueda_hibrida(consulta_expandida, filtros=None, top_k=settings.retrieval_top_k)
        # Quedarnos con el mejor intento
        if not resultados or (resultados_alt and resultados_alt[0].score > resultados[0].score):
            resultados = resultados_alt

    # Etapa 3: reranking jurídico
    reranked = rerankear(resultados, jurisdiccion=analisis.jurisdiccion)
    return reranked[: settings.rerank_top_k]


def _filtros_desde_analisis(a: AnalisisConsulta) -> Filtros:
    """Construye los filtros de recuperación desde el análisis de consulta."""
    f = Filtros(solo_vigentes=True)
    if a.materia:
        f.materia = a.materia
    # No filtramos por entidad siempre: la ley federal aplica en todo el país.
    # Solo filtramos entidad si la consulta es claramente local y no federal.
    return f


def _calidad_insuficiente(resultados: list[Resultado]) -> bool:
    """True si el mejor score cae bajo el umbral de calidad."""
    if not resultados:
        return True
    return resultados[0].score < settings.retrieval_quality_threshold
