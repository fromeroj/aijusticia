"""Ingesta unificada — corre todos los adapters del corpus.

Uso:
    python scripts/ingest_all.py                      # todos los adapters (incremental)
    python scripts/ingest_all.py --fuentes SJF,DOF    # solo fuentes específicas
    python scripts/ingest_all.py --solo-listar        # solo listar, no descargar
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ai_justicia.corpus.adapters.base import metadata_a_documento
from ai_justicia.corpus.models import Fuente
from ai_justicia.corpus.store import batch_upsert_documentos, count_documentos, count_chunks_sin_embedding
from ai_justicia.corpus.watermark import guardar_watermark, leer_watermark

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("ingest_all")


def get_adapter(fuente: str):
    """Factory: devuelve el adapter para una fuente."""
    if fuente == "SJF":
        from ai_justicia.corpus.adapters.sjf import SJFAdapter
        return SJFAdapter()
    if fuente == "DOF":
        from ai_justicia.corpus.adapters.dof import DOFAdapter
        return DOFAdapter()
    if fuente == "LeyesBiblio":
        from ai_justicia.corpus.adapters.leyes_biblio import LeyesBiblioAdapter
        return LeyesBiblioAdapter()
    if fuente == "Edomex":
        from ai_justicia.corpus.adapters.edomex import EdomexAdapter
        return EdomexAdapter()
    if fuente == "NuevoLeon":
        from ai_justicia.corpus.adapters.nuevo_leon import NuevoLeonAdapter
        return NuevoLeonAdapter()
    if fuente == "Jalisco":
        from ai_justicia.corpus.adapters.jalisco import JaliscoAdapter
        return JaliscoAdapter()
    raise ValueError(f"Adapter desconocido: {fuente}")


def ingestar_adapter(nombre: str, solo_listar: bool = False) -> int:
    """Corre un adapter específico. Devuelve número de documentos procesados."""
    logger.info("=" * 50)
    logger.info("INGESTANDO: %s", nombre)
    logger.info("=" * 50)

    try:
        adapter = get_adapter(nombre)
    except Exception as e:
        logger.error("No se pudo crear adapter %s: %s", nombre, e)
        return 0

    # Watermark para incremental
    watermark = leer_watermark(nombre)
    logger.info("Watermark %s: %s", nombre, watermark or "(nunca)")

    procesados = 0
    docs_buffer = []

    for meta in adapter.listar_desde(watermark):
        if solo_listar:
            logger.info("  [LISTAR] %s: %s", meta.id_externo, meta.titulo[:60])
            procesados += 1
            continue

        # Obtener texto
        try:
            texto = adapter.obtener_texto(meta)
        except Exception as e:
            logger.warning("  ✗ Error obteniendo texto de %s: %s", meta.id_externo, e)
            continue

        if len(texto) < 50:
            continue

        meta.extra["_texto_usable"] = texto
        docs_buffer.append(meta)
        procesados += 1

        # Flush cada 50 documentos
        if len(docs_buffer) >= 50:
            docs = [metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo)) for m in docs_buffer]
            batch_upsert_documentos(docs)
            logger.info("  → %d docs ingresados (total DB: %d)", procesados, count_documentos())
            docs_buffer = []

    # Flush final
    if docs_buffer and not solo_listar:
        docs = [metadata_a_documento(m, m.extra.get("_texto_usable", m.titulo)) for m in docs_buffer]
        batch_upsert_documentos(docs)

    if procesados > 0 and not solo_listar:
        guardar_watermark(nombre, date.today())

    logger.info("✓ %s: %d documentos procesados", nombre, procesados)
    return procesados


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingesta unificada del corpus")
    parser.add_argument("--fuentes", type=str, default="SJF,DOF,LeyesBiblio,Edomex,NuevoLeon,Jalisco",
                        help="Fuentes separadas por coma (default: todas)")
    parser.add_argument("--solo-listar", action="store_true", help="Solo listar, no descargar")
    parser.add_argument("--embeddings", action="store_true", help="Generar embeddings después")
    args = parser.parse_args()

    fuentes = [f.strip() for f in args.fuentes.split(",")]
    inicio = time.time()

    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   INGESTA UNIFICADA — AI Justicia            ║")
    logger.info("╚══════════════════════════════════════════════╝")
    logger.info("Fuentes: %s", ", ".join(fuentes))
    logger.info("Documentos actuales en DB: %d", count_documentos())

    total_procesados = 0
    for fuente in fuentes:
        try:
            n = ingestar_adapter(fuente, solo_listar=args.solo_listar)
            total_procesados += n
        except Exception as e:
            logger.error("Error en %s: %s", fuente, e)

    elapsed = time.time() - inicio
    logger.info("")
    logger.info("╔══════════════════════════════════════════════╗")
    logger.info("║   INGESTA COMPLETADA                         ║")
    logger.info("╚══════════════════════════════════════════════╝")
    logger.info("Total procesados: %d en %.1f min", total_procesados, elapsed / 60)
    logger.info("Total en DB: %d documentos", count_documentos())

    if args.embeddings and not args.solo_listar:
        pendientes = count_chunks_sin_embedding()
        if pendientes > 0:
            logger.info("Generando embeddings para %d chunks pendientes...", pendientes)
            from ai_justicia.corpus.store import indexar_chunks_pendientes
            indexar_chunks_pendientes(lote=64)
            logger.info("✓ Embeddings completados")


if __name__ == "__main__":
    main()
