"""Persistencia del corpus en PostgreSQL + pgvector.

Funciones:
    - upsert_documento: inserta o actualiza un documento (idempotente por dedup_key)
    - chunk_and_index: parte un documento en pasajes, genera embeddings y los indexa
    - get_documento / count_documentos: lectura
"""

from __future__ import annotations

import logging
import re
from contextlib import contextmanager
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector

from ai_justicia.config import settings
from ai_justicia.corpus.models import Chunk, Documento
from ai_justicia.retrieval.embeddings import embed_texts

logger = logging.getLogger(__name__)

# Tamaño objetivo de chunk en caracteres (~100-200 tokens para español jurídico).
# Los artículos cortos quedan en un solo chunk; los largos se parten por artículo.
CHUNK_TARGET_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150


@contextmanager
def get_conn(vector: bool = False) -> Iterator[psycopg.Connection]:
    """Conexión a Postgres. Si vector=True, registra el adaptador pgvector."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        if vector:
            register_vector(conn)
        yield conn


def upsert_documento(doc: Documento) -> int:
    """Inserta o actualiza un documento. Devuelve su id. Idempotente por (fuente, dedup_key)."""
    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO documentos (
                    fuente, entidad, materia, tipo, titulo, texto,
                    registro_sjf, fecha_reforma, fecha_publicacion, fecha_vigencia,
                    derogado, jerarquia, vinculante, url_origen, raw, dedup_key
                ) VALUES (
                    %(fuente)s, %(entidad)s, %(materia)s, %(tipo)s, %(titulo)s, %(texto)s,
                    %(registro_sjf)s, %(fecha_reforma)s, %(fecha_publicacion)s, %(fecha_vigencia)s,
                    %(derogado)s, %(jerarquia)s, %(vinculante)s, %(url_origen)s, %(raw)s, %(dedup_key)s
                )
                ON CONFLICT (fuente, dedup_key) DO UPDATE SET
                    texto = EXCLUDED.texto,
                    fecha_reforma = EXCLUDED.fecha_reforma,
                    fecha_publicacion = EXCLUDED.fecha_publicacion,
                    fecha_vigencia = EXCLUDED.fecha_vigencia,
                    derogado = EXCLUDED.derogado,
                    jerarquia = EXCLUDED.jerarquia,
                    vinculante = EXCLUDED.vinculante,
                    raw = EXCLUDED.raw,
                    updated_at = now()
                RETURNING id
                """,
                {
                    "fuente": doc.fuente.value,
                    "entidad": doc.entidad,
                    "materia": doc.materia.value if doc.materia else None,
                    "tipo": doc.tipo,
                    "titulo": doc.titulo,
                    "texto": doc.texto,
                    "registro_sjf": doc.registro_sjf,
                    "fecha_reforma": doc.fecha_reforma,
                    "fecha_publicacion": doc.fecha_publicacion,
                    "fecha_vigencia": doc.fecha_vigencia,
                    "derogado": doc.derogado,
                    "jerarquia": doc.jerarquia,
                    "vinculante": doc.vinculante,
                    "url_origen": doc.url_origen,
                    "raw": psycopg.types.json.Json(doc.raw) if doc.raw else None,
                    "dedup_key": doc.dedup_key,
                },
            )
            row = cur.fetchone()
            conn.commit()
            return row[0]


def chunk_documento(doc: Documento) -> list[str]:
    """Parte el texto de un documento en pasajes para indexar.

    Estrategia jurídica: si el texto tiene marcadores de artículo (Artículo X.),
    parte por artículo; si es muy largo, parte por párrafos con solapamiento.
    Documentos cortos (tesis breve) quedan en un solo chunk.
    """
    texto = doc.texto.strip()
    if len(texto) <= CHUNK_TARGET_CHARS:
        return [texto] if texto else []

    # Intentar partir por "Artículo N." (patrón común en leyes)
    articulos = re.split(r"(?=^Artículo\s+\d+[\.\s])", texto, flags=re.MULTILINE)
    articulos = [a.strip() for a in articulos if a.strip()]

    chunks: list[str] = []
    for art in articulos:
        if len(art) <= CHUNK_TARGET_CHARS:
            chunks.append(art)
        else:
            # Partir por párrafos con solapamiento
            chunks.extend(_split_with_overlap(art, CHUNK_TARGET_CHARS, CHUNK_OVERLAP_CHARS))

    return chunks


def _split_with_overlap(text: str, size: int, overlap: int) -> list[str]:
    """Parte texto en ventanas de `size` chars con `overlap` de solapamiento."""
    chunks = []
    start = 0
    while start < len(text):
        end = start + size
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def chunk_and_index(doc: Documento, doc_id: int) -> int:
    """Parte un documento en chunks, genera embeddings y los indexa en pgvector.

    Devuelve el número de chunks indexados. Borra los chunks previos del documento.
    """
    textos = chunk_documento(doc)
    if not textos:
        return 0

    logger.info("Indexando doc %d: %d chunks", doc_id, len(textos))
    embeddings = embed_texts(textos)  # lote único (para dev, el corpus es chico)

    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            # Borrar chunks previos (reindexación)
            cur.execute("DELETE FROM documentos_chunks WHERE documento_id = %s", (doc_id,))

            rows = [
                (doc_id, i, texto, emb)
                for i, (texto, emb) in enumerate(zip(textos, embeddings, strict=True))
            ]
            cur.executemany(
                """
                INSERT INTO documentos_chunks (documento_id, ordinal, texto, embedding)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (documento_id, ordinal) DO UPDATE SET
                    texto = EXCLUDED.texto,
                    embedding = EXCLUDED.embedding
                """,
                [(r[0], r[1], r[2], r[3]) for r in rows],
            )
        conn.commit()
    return len(rows)


def count_documentos() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documentos")
            return cur.fetchone()[0]


def count_chunks() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documentos_chunks")
            return cur.fetchone()[0]


def count_chunks_sin_embedding() -> int:
    """Cuenta chunks que aún no tienen embedding (pendientes de Fase 2)."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM documentos_chunks WHERE embedding IS NULL")
            return cur.fetchone()[0]


def upsert_documento_rapido(doc: Documento) -> int:
    """Upsert + chunk SIN generar embeddings. Para backfill masivo (Fase 1).

    Crea el documento y sus chunks con embedding=NULL. Los embeddings se
    generan después con `indexar_chunks_pendientes` (Fase 2).
    Devuelve el doc_id.
    """
    doc_id = upsert_documento(doc)
    textos = chunk_documento(doc)
    if not textos:
        return doc_id

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documentos_chunks WHERE documento_id = %s", (doc_id,))
            # INSERT masivo sin embedding
            cur.executemany(
                """
                INSERT INTO documentos_chunks (documento_id, ordinal, texto, embedding)
                VALUES (%s, %s, %s, NULL)
                ON CONFLICT (documento_id, ordinal) DO UPDATE SET texto = EXCLUDED.texto
                """,
                [(doc_id, i, texto) for i, texto in enumerate(textos)],
            )
        conn.commit()
    return doc_id


def batch_upsert_documentos(documentos: list[Documento]) -> int:
    """Upsert + chunk de un lote de documentos SIN embeddings.

    Usa psycopg `execute_values` para INSERT masivo de alta performance.
    Devuelve el número de documentos procesados.
    """
    if not documentos:
        return 0

    from psycopg import sql

    with get_conn(vector=False) as conn:
        with conn.cursor() as cur:
            for doc in documentos:
                # Upsert documento (RETURNING id para linkear chunks)
                cur.execute(
                    """
                    INSERT INTO documentos (
                        fuente, entidad, materia, tipo, titulo, texto,
                        registro_sjf, fecha_reforma, fecha_publicacion, fecha_vigencia,
                        derogado, jerarquia, vinculante, url_origen, raw, dedup_key
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (fuente, dedup_key) DO UPDATE SET
                        texto = EXCLUDED.texto, updated_at = now()
                    RETURNING id
                    """,
                    (
                        doc.fuente.value, doc.entidad,
                        doc.materia.value if doc.materia else None,
                        doc.tipo, doc.titulo, doc.texto,
                        doc.registro_sjf, doc.fecha_reforma,
                        doc.fecha_publicacion, doc.fecha_vigencia,
                        doc.derogado, doc.jerarquia, doc.vinculante,
                        doc.url_origen,
                        psycopg.types.json.Json(doc.raw) if doc.raw else None,
                        doc.dedup_key,
                    ),
                )
                row = cur.fetchone()
                if not row:
                    continue
                doc_id = row[0]

                # Chunk: la mayoría de tesis del SJF caben en 1 chunk
                textos = chunk_documento(doc)
                if textos:
                    cur.execute("DELETE FROM documentos_chunks WHERE documento_id = %s", (doc_id,))
                    # INSERT simple (1-2 chunks por tesis = rápido)
                    for i, t in enumerate(textos):
                        cur.execute(
                            """INSERT INTO documentos_chunks (documento_id, ordinal, texto, embedding)
                               VALUES (%s, %s, %s, NULL)
                               ON CONFLICT (documento_id, ordinal) DO UPDATE SET texto = EXCLUDED.texto""",
                            (doc_id, i, t),
                        )
            # Commit por lote (no por documento) para performance
            conn.commit()
    return len(documentos)


def indexar_chunks_pendientes(lote: int = 32, max_chunks: int | None = None) -> int:
    """Genera embeddings para chunks que no los tienen (Fase 2).

    Procesa en lotes: lee N chunks sin embedding, genera embeddings vía LM Studio,
    y los actualiza. Reanudable: si se interrumpe, los chunks ya procesados quedan
    con embedding y los demás se procesan la próxima vez.

    Devuelve el número de chunks indexados en esta ejecución.
    """
    from ai_justicia.retrieval.embeddings import embed_texts

    procesados = 0
    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            while True:
                if max_chunks is not None and procesados >= max_chunks:
                    break

                limite = min(lote, max_chunks - procesados) if max_chunks else lote
                cur.execute(
                    """SELECT id, texto FROM documentos_chunks
                       WHERE embedding IS NULL ORDER BY id LIMIT %s""",
                    (limite,),
                )
                rows = cur.fetchall()
                if not rows:
                    break

                ids = [r[0] for r in rows]
                textos = [r[1] for r in rows]

                # Generar embeddings del lote
                embeddings = embed_texts(textos)
                if len(embeddings) != len(textos):
                    logger.error("Mismatch: %d embeddings para %d textos", len(embeddings), len(textos))
                    break

                # Actualizar chunks con embeddings
                import numpy as np
                for chunk_id, emb in zip(ids, embeddings, strict=True):
                    cur.execute(
                        "UPDATE documentos_chunks SET embedding = %s WHERE id = %s",
                        (np.array(emb, dtype=np.float32), chunk_id),
                    )
                conn.commit()
                procesados += len(ids)
                logger.info("Embeddings: %d chunks indexados (lote de %d)", procesados, len(ids))

    return procesados

