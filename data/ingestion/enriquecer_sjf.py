"""Enriquece tesis del SJF con texto completo del endpoint de detalle.

El backfill inicial usó solo el rubro (título) del search result. Este script
descarga el texto completo (rubro + cuerpo + precedentes) del endpoint de detalle
para cada tesis, actualizando el documento y regenerando su chunk + embedding.

Prioriza tesis vinculantes (jurisprudencia) sobre persuasivas.

Uso:
    # Enriquecer todas las vinculantes (prioridad)
    python scripts/enriquecer_sjf.py --vinculantes

    # Enriquecer un lote de prueba
    python scripts/enriquecer_sjf.py --vinculantes --limite 100

    # Enriquecer TODO (vinculantes + persuasivas)
    python scripts/enriquecer_sjf.py --todas

Reanudable: salta tesis que ya tienen texto largo (>500 chars = ya enriquecidas).
"""

from __future__ import annotations

import argparse
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg

from ai_justicia.config import settings
from ai_justicia.corpus.adapters.sjf import SJFAdapter
from ai_justicia.corpus.clean import limpiar_texto
from ai_justicia.corpus.store import chunk_and_index, get_conn

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger("enriquecer")


def obtener_tesis_a_enriquecer(solo_vinculantes: bool, limite: int | None) -> list[tuple[int, str, str]]:
    """Devuelve [(doc_id, registro_sjf, titulo)] de tesis con texto corto (< 500 chars).

    Filtra las que ya están enriquecidas (texto >= 500 chars = tienen cuerpo completo).
    """
    query = """
        SELECT id, registro_sjf, titulo
        FROM documentos
        WHERE fuente = 'SJF'
          AND registro_sjf IS NOT NULL
          AND LENGTH(texto) < 500
    """
    if solo_vinculantes:
        query += " AND vinculante = TRUE"
    query += " ORDER BY fecha_publicacion ASC, id ASC"
    if limite:
        query += f" LIMIT {limite}"

    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            return cur.fetchall()


def enriquecer_tesis(adapter: SJFAdapter, doc_id: int, registro_sjf: str, titulo: str) -> bool:
    """Descarga el texto completo de una tesis y la actualiza en la DB.

    Devuelve True si se enriqueció, False si falló (404, lag semanal, etc.).
    """
    from ai_justicia.corpus.adapters.base import DocumentoMetadata
    from datetime import date

    meta = DocumentoMetadata(
        id_externo=registro_sjf,
        fuente=adapter.fuente,
        titulo=titulo,
        fecha_publicacion=date.today(),
        registro_sjf=registro_sjf,
        extra={},
    )

    try:
        texto_completo = adapter.obtener_texto(meta)
    except Exception as e:
        logger.debug("Detalle falló para %s: %s", registro_sjf, e)
        return False

    if len(texto_completo) < len(titulo) + 50:
        # El detalle no trajo más texto del que ya teníamos
        return False

    # Actualizar el texto del documento + rechunk + reindexar (con embedding)
    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE documentos SET texto = %s WHERE id = %s", (texto_completo, doc_id))
        conn.commit()

    # Rechunk + embedding
    from ai_justicia.corpus.models import Documento
    with get_conn(vector=True) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT texto FROM documentos WHERE id = %s", (doc_id,))
            row = cur.fetchone()
            if row:
                doc = Documento(
                    fuente=adapter.fuente,
                    titulo=titulo,
                    texto=row[0],
                    registro_sjf=registro_sjf,
                )
    chunk_and_index(doc, doc_id)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Enriquece tesis del SJF con texto completo")
    parser.add_argument("--vinculantes", action="store_true", help="Solo tesis vinculantes (jurisprudencia)")
    parser.add_argument("--todas", action="store_true", help="Todas (vinculantes + persuasivas)")
    parser.add_argument("--limite", type=int, help="Máximo número de tesis a procesar")
    args = parser.parse_args()

    solo_vinculantes = args.vinculantes or not args.todas

    tesis = obtener_tesis_a_enriquecer(solo_vinculantes, args.limite)
    logger.info("=" * 60)
    logger.info("ENRIQUECIMIENTO SJF — %d tesis %s", len(tesis), "vinculantes" if solo_vinculantes else "totales")
    logger.info("=" * 60)

    if not tesis:
        logger.info("✓ No hay tesis para enriquecer (ya tienen texto completo).")
        return

    adapter = SJFAdapter()
    procesadas = 0
    enriquecidas = 0
    fallidas = 0
    inicio = time.time()

    for doc_id, registro_sjf, titulo in tesis:
        ok = enriquecer_tesis(adapter, doc_id, registro_sjf, titulo)
        procesadas += 1
        if ok:
            enriquecidas += 1
        else:
            fallidas += 1

        if procesadas % 100 == 0:
            elapsed = time.time() - inicio
            rate = procesadas / elapsed if elapsed > 0 else 0
            pct = procesadas / len(tesis) * 100
            logger.info(
                "Progreso: %d/%d (%.1f%%) | %d enriquecidas | %d fallidas | %.1f/s | ETA %.0f min",
                procesadas, len(tesis), pct, enriquecidas, fallidas, rate,
                (len(tesis) - procesadas) / rate / 60 if rate > 0 else 0,
            )

    elapsed = time.time() - inicio
    logger.info("=" * 60)
    logger.info("COMPLETADO: %d procesadas, %d enriquecidas, %d fallidas en %.1f min",
                procesadas, enriquecidas, fallidas, elapsed / 60)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
