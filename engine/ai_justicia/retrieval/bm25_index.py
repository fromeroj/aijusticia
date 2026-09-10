"""Índice BM25 en memoria (capa léxica del índice híbrido).

BM25 es clave para coincidencia exacta de números de artículo, registros y frases
normativas — cosas que el vectorial semántico puede perder. Se carga desde
documentos_chunks al iniciar y se reconstruye tras cada ingesta.

En producción con corpus grande, esto migraría a Postgres con pg_trgm o a
Elasticsearch; aquí usamos rank_bm25 en memoria (suficiente para el corpus MX).
"""

from __future__ import annotations

import logging
import re
from typing import Sequence

from rank_bm25 import BM25Okapi

from ai_justicia.corpus.store import get_conn
from ai_justicia.retrieval.vector_index import Resultado

logger = logging.getLogger(__name__)


def tokenize(text: str) -> list[str]:
    """Tokenizador ligero para español jurídico: minúsculas, sin puntuación, sin stopwords mínimas."""
    text = text.lower()
    # Conservar números (importantes: "artículo 14", "registro 2024156789")
    tokens = re.findall(r"[a-záéíóúñü]+|\d+", text)
    # Stopwords mínimas (no queremos matar términos jurídicos)
    stop = {"de", "la", "el", "en", "y", "a", "los", "las", "del", "se", "que", "con", "por", "para"}
    return [t for t in tokens if t not in stop]


class BM25Index:
    """Índice BM25 en memoria sobre los chunks del corpus."""

    def __init__(self) -> None:
        self._bm25: BM25Okapi | None = None
        self._chunks: list[dict] = []   # metadata paralela: {chunk_id, documento_id, texto}
        self._tokenized: list[list[str]] = []
        self._loaded = False

    def load(self) -> None:
        """Carga todos los chunks desde la DB y construye el índice."""
        with get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT (c.documento_id * 1000000 + c.ordinal) AS chunk_id,
                           c.documento_id, c.texto,
                           d.fuente, d.titulo, d.materia, d.entidad, d.jerarquia,
                           d.vinculante, d.registro_sjf, d.fecha_reforma,
                           d.fecha_publicacion, d.fecha_vigencia, d.derogado
                    FROM documentos_chunks c
                    JOIN documentos d ON d.id = c.documento_id
                    WHERE d.derogado = FALSE
                    ORDER BY c.documento_id, c.ordinal
                    """
                )
                rows = cur.fetchall()

        self._chunks = [
            {
                "chunk_id": r[0], "documento_id": r[1], "texto": r[2],
                "fuente": r[3], "titulo": r[4], "materia": r[5], "entidad": r[6],
                "jerarquia": r[7], "vinculante": r[8], "registro_sjf": r[9],
                "fecha_reforma": r[10], "fecha_publicacion": r[11],
                "fecha_vigencia": r[12], "derogado": r[13],
            }
            for r in rows
        ]
        self._tokenized = [tokenize(c["texto"]) for c in self._chunks]
        self._bm25 = BM25Okapi(self._tokenized) if self._tokenized else BM25Okapi([["dummy"]])
        self._loaded = True
        logger.info("BM25 cargado: %d chunks", len(self._chunks))

    @property
    def loaded(self) -> bool:
        return self._loaded

    def search(self, query: str, top_k: int = 10) -> list[Resultado]:
        """Búsqueda BM25. Devuelve Resultados ordenados por score (desc)."""
        if not self._loaded:
            self.load()
        if not self._chunks:
            return []

        tokenized_query = tokenize(query)
        scores = self._bm25.get_scores(tokenized_query)

        # Top-k por score
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        resultados = []
        for idx, score in ranked:
            if score <= 0:
                continue  # BM25 score 0 = sin coincidencia léxica
            c = self._chunks[idx]
            resultados.append(Resultado(
                chunk_id=c["chunk_id"], documento_id=c["documento_id"], texto=c["texto"],
                score=float(score),
                fuente=c["fuente"], titulo=c["titulo"], materia=c["materia"],
                entidad=c["entidad"], jerarquia=c["jerarquia"], vinculante=c["vinculante"],
                registro_sjf=c["registro_sjf"], fecha_reforma=c["fecha_reforma"],
                fecha_publicacion=c["fecha_publicacion"], fecha_vigencia=c["fecha_vigencia"],
                derogado=c["derogado"],
            ))
        return resultados


# Singleton
_bm25_index: BM25Index | None = None


def get_bm25_index() -> BM25Index:
    global _bm25_index
    if _bm25_index is None:
        _bm25_index = BM25Index()
        _bm25_index.load()
    return _bm25_index


def reload_bm25_index() -> BM25Index:
    """Fuerza recarga del índice (tras ingesta)."""
    global _bm25_index
    _bm25_index = BM25Index()
    _bm25_index.load()
    return _bm25_index
