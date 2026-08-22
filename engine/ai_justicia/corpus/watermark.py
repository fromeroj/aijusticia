"""Watermark tracker — última fecha procesada por fuente.

Para ingesta incremental: cada adapter sabe "dame todo desde la última vez".
El watermark se persiste en una tabla simple de Postgres.

Uso:
    from ai_justicia.corpus.watermark import leer_watermark, guardar_watermark
    desde = leer_watermark(Fuente.SJF)  # None = nunca corrido
    guardar_watermark(Fuente.SJF, date.today())
"""

from __future__ import annotations

import logging
from datetime import date

from ai_justicia.corpus.models import Fuente
from ai_justicia.corpus.store import get_conn

logger = logging.getLogger(__name__)


def leer_watermark(fuente: Fuente | str) -> date | None:
    """Devuelve la última fecha procesada de una fuente, o None si nunca."""
    f = fuente.value if isinstance(fuente, Fuente) else str(fuente)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "CREATE TABLE IF NOT EXISTS ingestion_watermarks (fuente TEXT PRIMARY KEY, ultima_fecha DATE NOT NULL)"
            )
            cur.execute("SELECT ultima_fecha FROM ingestion_watermarks WHERE fuente = %s", (f,))
            row = cur.fetchone()
            return row[0] if row else None


def guardar_watermark(fuente: Fuente | str, ultima_fecha: date) -> None:
    """Actualiza el watermark de una fuente."""
    f = fuente.value if isinstance(fuente, Fuente) else str(fuente)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_watermarks (fuente, ultima_fecha) VALUES (%s, %s)
                ON CONFLICT (fuente) DO UPDATE SET ultima_fecha = EXCLUDED.ultima_fecha
                """,
                (f, ultima_fecha),
            )
        conn.commit()
    logger.info("Watermark %s → %s", f, ultima_fecha)
