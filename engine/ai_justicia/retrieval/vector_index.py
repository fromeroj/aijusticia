"""Recuperación vectorial en pgvector.

Búsqueda por similitud coseno sobre documentos_chunks, con filtros por
fuente, entidad, materia, vigencia y jerarquía (los metadatos del documento padre).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import numpy as np
from pgvector.psycopg import register_vector

from ai_justicia.corpus.store import get_conn
from ai_justicia.retrieval.embeddings import embed_query

logger = logging.getLogger(__name__)


@dataclass
class Filtros:
    """Filtros de recuperación (alimentados por el análisis de consulta, etapa 1)."""
    fuente: str | None = None          # 'DOF' | 'LeyesBiblio' | 'SJF' | ...
    entidad: str | None = None         # entidad federativa; None = federal
    materia: str | None = None
    fecha_vigencia_min: date | None = None  # solo documentos vigentes a partir de esta fecha
    solo_vigentes: bool = True         # excluir derogados
    jerarquia_max: int | None = None   # tope de jerarquía (ej. solo leyes y superiores)


@dataclass
class Resultado:
    """Un pasaje recuperado con su score y metadatos para el reranker."""
    chunk_id: int
    documento_id: int
    texto: str
    score: float                       # similitud (vectorial o fusionada)
    # Metadatos del documento padre (para reranking jurídico y verificación)
    fuente: str = ""
    titulo: str = ""
    materia: str | None = None
    entidad: str | None = None
    jerarquia: int = 100
    vinculante: bool = True
    registro_sjf: str | None = None
    fecha_reforma: date | None = None
    fecha_publicacion: date | None = None
    fecha_vigencia: date | None = None
    derogado: bool = False


def busqueda_vectorial(query: str, filtros: Filtros | None = None, top_k: int = 10) -> list[Resultado]:
    """Búsqueda vectorial por similitud coseno en pgvector.

    Joinea con documentos para traer los metadatos que el reranker necesita.
    """
    filtros = filtros or Filtros()
    query_emb = np.array(embed_query(query), dtype=np.float32)

    where_clauses = []
    params: list = []
    # El primer %s (en SELECT, para el score) y el segundo %s (en ORDER BY)
    # requieren el embedding; el de ORDER BY se añade tras los filtros.
    params.append(query_emb)  # para SELECT
    if filtros.fuente:
        where_clauses.append("d.fuente = %s")
        params.append(filtros.fuente)
    if filtros.entidad:
        where_clauses.append("d.entidad = %s")
        params.append(filtros.entidad)
    if filtros.materia:
        where_clauses.append("d.materia = %s")
        params.append(filtros.materia)
    if filtros.solo_vigentes:
        where_clauses.append("d.derogado = FALSE")
    if filtros.jerarquia_max is not None:
        where_clauses.append("d.jerarquia <= %s")
        params.append(filtros.jerarquia_max)

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    params.append(query_emb)  # para ORDER BY
    params.append(top_k)      # para LIMIT

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
    # El operador <=> es distancia coseno en pgvector; score = 1 - distancia

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
