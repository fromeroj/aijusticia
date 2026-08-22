"""Monitoreo de salud de las fuentes (3 detectores).

Se ejecuta después de cada ingestion_run para detectar fallos silenciosos.
"""

from __future__ import annotations

import logging
from datetime import datetime, date

from ai_justicia.ingestion.store import obtener_health, actualizar_health

logger = logging.getLogger(__name__)

ALPHA = 0.1  # factor EWMA


def recalcular_salud(
    fuente: str,
    entidad: str,
    run_status: str,
    documentos_new: int,
    documentos_fetched: int,
    hash_changed: bool,
    watermark_after: date | None,
    total_documentos: int,
    listing_page_hash: str | None,
) -> str:
    """Recalcula el estado de salud de una fuente tras una ejecución.

    Devuelve el nuevo health_status.
    """
    from ai_justicia.corpus.store import get_conn
    import psycopg

    from ai_justicia.config import settings

    health = obtener_health(fuente, entidad)
    if not health:
        logger.warning("No hay source_health para %s/%s", fuente, entidad)
        return "unknown"

    # Leer contadores actuales
    consec_failures = health.get("consecutive_failures", 0)
    consec_empty = health.get("consecutive_empty", 0)
    rolling_avg = health.get("rolling_avg_results", 0) or 0
    expected_min = health.get("expected_min_results", 1)
    last_hash = health.get("listing_page_hash")
    last_success = health.get("last_success_at")

    now = datetime.now()

    # Actualizar EWMA
    if run_status in ("success", "partial"):
        rolling_avg = (ALPHA * documentos_new) + ((1 - ALPHA) * rolling_avg) if rolling_avg > 0 else documentos_new

    # Detector A: empty-result
    if documentos_fetched == 0 and run_status != "failed":
        consec_empty += 1
    else:
        consec_empty = 0

    # Detector de fallos
    if run_status == "failed":
        consec_failures += 1
    else:
        consec_failures = 0

    # Determinar health_status
    if run_status == "success" and consec_empty == 0:
        health_status = "healthy"
        last_success = now
    elif consec_empty >= 2 or consec_failures >= 3:
        health_status = "unhealthy"
    elif consec_empty >= 1 or consec_failures >= 1 or (rolling_avg > 0 and documentos_new < 0.3 * rolling_avg):
        health_status = "degraded"
    else:
        health_status = "healthy"
        if run_status != "failed":
            last_success = now

    # Detector B: page-hash drift (info para log, no cambia status por sí solo)
    if hash_changed and documentos_new < expected_min:
        logger.warning("Hash cambió en %s/%s + rendimiento bajo (%d < %d)",
                       fuente, entidad, documentos_new, expected_min)

    # Actualizar DB
    actualizar_health(
        fuente=fuente,
        entidad=entidad if entidad != "Federal" else None,
        health_status=health_status,
        consecutive_failures=consec_failures,
        consecutive_empty=consec_empty,
        last_run_at=now,
        last_success_at=last_success,
        watermark=watermark_after,
        total_documentos=total_documentos,
        listing_page_hash=listing_page_hash or last_hash,
        rolling_avg_results=rolling_avg if rolling_avg > 0 else None,
    )

    logger.info("Health %s/%s → %s (empty=%d, fail=%d, avg=%.1f)",
                fuente, entidad, health_status, consec_empty, consec_failures, rolling_avg)
    return health_status
