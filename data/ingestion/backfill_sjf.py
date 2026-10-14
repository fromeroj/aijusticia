"""Backfill masivo de tesis del SJF.

Dos fases:
  Fase 1: descargar tesis del feed search → upsert en DB SIN embeddings
  Fase 2: generar embeddings para chunks pendientes (en lotes)

Uso:
    # Fase 1: descargar 150,000 tesis (con progreso y checkpoints)
    python scripts/backfill_sjf.py --objetivo 150000

    # Fase 2: generar embeddings para chunks sin embedding
    python scripts/backfill_sjf.py --embeddings --lote 64

    # Ambas fases seguidas
    python scripts/backfill_sjf.py --objetivo 150000 --embeddings

Reanudable: si se cae, volver a correr continúa desde donde quedó.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.config import settings
from ai_justicia.corpus.adapters.base import metadata_a_documento
from ai_justicia.corpus.adapters.sjf import SJFAdapter
from ai_justicia.corpus.models import Fuente
from ai_justicia.corpus.store import (
    batch_upsert_documentos,
    count_chunks,
    count_chunks_sin_embedding,
    count_documentos,
    indexar_chunks_pendientes,
)
from ai_justicia.corpus.watermark import guardar_watermark

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill")


def fase_descarga(objetivo: int, lote_persistencia: int = 500) -> None:
    """Fase 1: descargar tesis del SJF y persistir sin embeddings."""
    adapter = SJFAdapter(page_size=200)
    total_inicial = count_documentos()
    total_bajar = objetivo

    # Calcular página inicial: si ya tenemos N docs, saltamos las primeras N/200 páginas
    # (el feed es newest-first, y los primeros N/200 páginas ya están en la DB)
    start_page = total_inicial // 200
    logger.info("=" * 60)
    logger.info("FASE 1: DESCARGA DE %d TESIS DEL SJF", total_bajar)
    logger.info("Documentos actuales en DB: %d (start_page=%d)", total_inicial, start_page)
    logger.info("Objetivo: %d | A descargar: %d", total_bajar, total_bajar - total_inicial)
    logger.info("=" * 60)

    if total_inicial >= total_bajar:
        logger.info("✓ Ya hay %d documentos (>= objetivo %d). Saltando Fase 1.", total_inicial, total_bajar)
        return

    buffer: list = []  # buffer de DocumentoMetadata para batch upsert
    procesados = 0
    descartados = 0
    ultima_fecha = None
    inicio = time.time()

    for meta in adapter.listar_desde(max_pages=1000, start_page=start_page):
        # El search slim no trae `texto` (es null); usar el rubro como contenido.
        # El rubro contiene el criterio jurídico completo (media 228 chars).
        texto = meta.extra.get("_texto_slim", "") or meta.titulo
        if len(texto) < 30:
            descartados += 1
            continue

        # Guardar el texto usable en el metadata para el batch_upsert
        meta.extra["_texto_usable"] = texto
        buffer.append(meta)
        if ultima_fecha is None or (meta.fecha_publicacion and meta.fecha_publicacion > ultima_fecha):
            ultima_fecha = meta.fecha_publicacion

        # Flush del buffer cada lote_persistencia items
        if len(buffer) >= lote_persistencia:
            docs = []
            for m in buffer:
                doc = metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo))
                docs.append(doc)
            n = batch_upsert_documentos(docs)
            procesados += n
            buffer.clear()
            elapsed = time.time() - inicio
            rate = procesados / elapsed if elapsed > 0 else 0
            pct = ((total_inicial + procesados) / total_bajar) * 100
            logger.info(
                "Progreso: %d/%d docs (%.1f%%) | %d descartados | %.1f docs/s | ETA %.0f min",
                total_inicial + procesados, total_bajar, pct,
                descartados, rate,
                (total_bajar - total_inicial - procesados) / rate / 60 if rate > 0 else 0,
            )

            # Checkpoint: guardar watermark cada ~5000
            if ultima_fecha and procesados % 5000 < lote_persistencia:
                guardar_watermark(Fuente.SJF, ultima_fecha)

        # Corte al alcanzar objetivo
        if total_inicial + procesados >= total_bajar:
            break

    # Flush final
    if buffer:
        docs = [metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo)) for m in buffer]
        n = batch_upsert_documentos(docs)
        procesados += n

    if ultima_fecha:
        guardar_watermark(Fuente.SJF, ultima_fecha)

    elapsed = time.time() - inicio
    logger.info("=" * 60)
    logger.info("FASE 1 COMPLETADA: %d documentos descargados en %.1f min", procesados, elapsed / 60)
    logger.info("Descartados (texto < 50 chars): %d", descartados)
    logger.info("Total en DB: %d documentos, %d chunks", count_documentos(), count_chunks())
    logger.info("=" * 60)


def fase_embeddings(lote: int = 64) -> None:
    """Fase 2: generar embeddings para chunks sin embedding."""
    pendientes = count_chunks_sin_embedding()
    logger.info("=" * 60)
    logger.info("FASE 2: INDEXACIÓN VECTORIAL")
    logger.info("Chunks sin embedding: %d (lote=%d)", pendientes, lote)
    logger.info("=" * 60)

    if pendientes == 0:
        logger.info("✓ No hay chunks pendientes. Todo indexado.")
        return

    inicio = time.time()
    total = indexar_chunks_pendientes(lote=lote)
    elapsed = time.time() - inicio

    logger.info("=" * 60)
    logger.info("FASE 2 COMPLETADA: %d chunks indexados en %.1f min", total, elapsed / 60)
    logger.info("Rate: %.1f chunks/s", total / elapsed if elapsed > 0 else 0)
    logger.info("Pendientes restantes: %d", count_chunks_sin_embedding())
    logger.info("=" * 60)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill masivo del SJF")
    parser.add_argument("--objetivo", type=int, default=150000, help="Número objetivo de documentos (default 150000)")
    parser.add_argument("--embeddings", action="store_true", help="Ejecutar también Fase 2 (embeddings)")
    parser.add_argument("--solo-embeddings", action="store_true", help="Solo Fase 2 (saltar descarga)")
    parser.add_argument("--lote", type=int, default=64, help="Tamaño de lote para embeddings (default 64)")
    args = parser.parse_args()

    if not args.solo_embeddings:
        fase_descarga(args.objetivo)

    if args.embeddings or args.solo_embeddings:
        fase_embeddings(lote=args.lote)


if __name__ == "__main__":
    main()
