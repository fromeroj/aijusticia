"""CRUD para source_health e ingestion_runs.

Funciones:
    - crear_run: inserta una fila de ejecución (status='running')
    - completar_run: actualiza la fila con resultados
    - obtener_health: lee el estado de una fuente
    - actualizar_health: recalcula el estado de salud
    - listar_sources_health: tabla para el dashboard
    - listar_runs: historial de ejecuciones
"""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

import psycopg

from ai_justicia.config import settings

logger = logging.getLogger(__name__)


def crear_run(
    fuente: str,
    entidad: str | None,
    trigger: str = "scheduled",
    watermark_before: date | None = None,
) -> int:
    """Crea una fila de ingestion_runs con status='running'. Devuelve el ID."""
    ent = entidad or "Federal"
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ingestion_runs (fuente, entidad, trigger, status, watermark_before)
                VALUES (%s, %s, %s, 'running', %s)
                RETURNING id
                """,
                (fuente, ent, trigger, watermark_before),
            )
            run_id = cur.fetchone()[0]
        conn.commit()
    return run_id


def completar_run(
    run_id: int,
    status: str,
    documentos_fetched: int = 0,
    documentos_new: int = 0,
    documentos_updated: int = 0,
    documentos_errored: int = 0,
    http_status_codes: list[int] | None = None,
    listing_page_hash: str | None = None,
    hash_changed: bool = False,
    error_message: str | None = None,
    error_count: int = 0,
    watermark_after: date | None = None,
    chunks_indexed: int | None = None,
) -> None:
    """Completa una fila de ingestion_runs con los resultados."""
    duration_sql = "EXTRACT(EPOCH FROM (now() - started_at)) * 1000"
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE ingestion_runs SET
                    completed_at = now(),
                    duration_ms = {duration_sql}::INT,
                    status = %s,
                    documentos_fetched = %s,
                    documentos_new = %s,
                    documentos_updated = %s,
                    documentos_errored = %s,
                    http_status_codes = %s,
                    listing_page_hash = %s,
                    hash_changed = %s,
                    error_message = %s,
                    error_count = %s,
                    watermark_after = %s,
                    chunks_indexed = %s
                WHERE id = %s
                """,
                (
                    status, documentos_fetched, documentos_new, documentos_updated,
                    documentos_errored, http_status_codes or [], listing_page_hash,
                    hash_changed, error_message, error_count, watermark_after,
                    chunks_indexed, run_id,
                ),
            )
        conn.commit()


def obtener_health(fuente: str, entidad: str | None = None) -> dict | None:
    """Lee el estado de salud de una fuente."""
    ent = entidad or "Federal"
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT fuente, entidad, tipo, adapter_class, enabled, cron_expr,
                          expected_min_results, last_run_at, last_success_at,
                          consecutive_failures, consecutive_empty, health_status,
                          watermark, total_documentos, listing_page_hash,
                          rolling_avg_results
                   FROM source_health WHERE fuente = %s AND entidad = %s""",
                (fuente, ent),
            )
            cols = [d[0] for d in cur.description]
            row = cur.fetchone()
            return dict(zip(cols, row, strict=True)) if row else None


def actualizar_health(
    fuente: str,
    entidad: str | None,
    health_status: str,
    consecutive_failures: int,
    consecutive_empty: int,
    last_run_at: datetime,
    last_success_at: datetime | None,
    watermark: date | None,
    total_documentos: int,
    listing_page_hash: str | None = None,
    rolling_avg_results: float | None = None,
) -> None:
    """Actualiza el estado de salud de una fuente."""
    ent = entidad or "Federal"
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE source_health SET
                    health_status = %s,
                    consecutive_failures = %s,
                    consecutive_empty = %s,
                    last_run_at = %s,
                    last_success_at = %s,
                    watermark = %s,
                    total_documentos = %s,
                    listing_page_hash = COALESCE(%s, listing_page_hash),
                    rolling_avg_results = COALESCE(%s, rolling_avg_results)
                WHERE fuente = %s AND entidad = %s
                """,
                (
                    health_status, consecutive_failures, consecutive_empty,
                    last_run_at, last_success_at, watermark, total_documentos,
                    listing_page_hash, rolling_avg_results,
                    fuente, ent,
                ),
            )
        conn.commit()


def listar_sources_health() -> list[dict]:
    """Lista todas las fuentes con su estado de salud (para el dashboard)."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT fuente, entidad, tipo, adapter_class, enabled,
                          cron_expr, expected_min_results, last_run_at,
                          last_success_at, consecutive_failures, consecutive_empty,
                          health_status, watermark, total_documentos,
                          portal_url, portal_verify_tls
                   FROM source_health ORDER BY fuente, entidad"""
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]


def listar_runs(fuente: str, entidad: str | None = None, limit: int = 50) -> list[dict]:
    """Lista el historial de ejecuciones de una fuente."""
    ent = entidad or "Federal"
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, fuente, entidad, started_at, completed_at, duration_ms,
                          trigger, status, documentos_fetched, documentos_new,
                          documentos_updated, documentos_errored, hash_changed,
                          error_message, error_count, watermark_before, watermark_after
                   FROM ingestion_runs
                   WHERE fuente = %s AND entidad = %s
                   ORDER BY started_at DESC LIMIT %s""",
                (fuente, ent, limit),
            )
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row, strict=True)) for row in cur.fetchall()]
