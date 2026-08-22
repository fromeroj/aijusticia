"""Cliente de embeddings para el índice vectorial.

Usa el modelo `text-embedding-nomic-embed-text-v1.5` servido por LM Studio.
Misma API OpenAI-compatible que el cliente LLM, endpoint /v1/embeddings.
"""

from __future__ import annotations

import logging

from ai_justicia.llm.client import get_llm_client

logger = logging.getLogger(__name__)

# Tamaño de lote para no saturar el servidor (nomic es ligero pero igual)
EMBED_BATCH_SIZE = 32


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Genera embeddings para una lista de textos (en lotes).

    Devuelve una lista de vectores en el mismo orden que la entrada.
    Dimensión: 768 (nomic-embed-text-v1.5).
    """
    if not texts:
        return []

    client = get_llm_client()
    all_embeddings: list[list[float]] = []

    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        batch = texts[start : start + EMBED_BATCH_SIZE]
        logger.debug("Embedding batch %d-%d / %d", start, start + len(batch), len(texts))
        all_embeddings.extend(client.embed(batch))

    return all_embeddings


def embed_query(text: str) -> list[float]:
    """Embedding de una consulta única."""
    return embed_texts([text])[0]
