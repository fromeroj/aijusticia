"""CRUD de pending_jobs en Postgres.

Funciones:
    - crear_job: inserta un job pendiente (lo llama el orchestrator en Caso B)
    - obtener_job: lee un job por id (lo usa GET /jobs/{id})
    - siguiente_pendiente: toma el próximo job pendiente (lo usa el worker)
    - actualizar_estado: cambia el estado + campos (worker)
    - marcar_completado: estado=COMPLETADO + respuesta + traza_reintento
    - marcar_fallido: estado=FALLIDO + error
"""

from __future__ import annotations

import logging
from datetime import datetime

import psycopg

from ai_justicia.config import settings
from ai_justicia.jobs.models import EstadoJob, PendingJob

logger = logging.getLogger(__name__)


def _row_to_job(row: tuple) -> PendingJob:
    return PendingJob(
        id=row[0],
        consulta=row[1],
        traza_id=row[2],
        norma_faltante=row[3],
        fuente=row[4],
        id_externo=row[5],
        estado=EstadoJob(row[6]),
        respuesta=row[7],
        traza_reintento=row[8],
        webhook_url=row[9],
        error=row[10],
        created_at=row[11],
        updated_at=row[12],
        completed_at=row[13],
    )


def crear_job(
    consulta: str,
    norma_faltante: str | None,
    fuente: str | None,
    id_externo: str | None,
    traza_id: int | None = None,
    webhook_url: str | None = None,
) -> int:
    """Crea un job pendiente. Devuelve su id."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO pending_jobs (consulta, traza_id, norma_faltante, fuente, id_externo, webhook_url)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (consulta, traza_id, norma_faltante, fuente, id_externo, webhook_url),
            )
            job_id = cur.fetchone()[0]
        conn.commit()
    logger.info("Job %d creado: norma=%s fuente=%s", job_id, norma_faltante, fuente)
    return job_id


def obtener_job(job_id: int) -> PendingJob | None:
    """Lee un job por id."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT id, consulta, traza_id, norma_faltante, fuente, id_externo,
                          estado, respuesta, traza_reintento, webhook_url, error,
                          created_at, updated_at, completed_at
                   FROM pending_jobs WHERE id = %s""",
                (job_id,),
            )
            row = cur.fetchone()
    return _row_to_job(row) if row else None


def siguiente_pendiente() -> PendingJob | None:
    """Toma atómicamente el próximo job pendiente (FIFO) y lo marca 'descargando'.

    Usa SELECT ... FOR UPDATE SKIP LOCKED para concurrencia segura entre workers.
    """
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE pending_jobs
                SET estado = 'descargando', updated_at = now()
                WHERE id = (
                    SELECT id FROM pending_jobs
                    WHERE estado = 'pendiente'
                    ORDER BY created_at
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                RETURNING id, consulta, traza_id, norma_faltante, fuente, id_externo,
                          estado, respuesta, traza_reintento, webhook_url, error,
                          created_at, updated_at, completed_at
                """
            )
            row = cur.fetchone()
        conn.commit()
    if row is None:
        return None
    logger.info("Worker tomó job %d", row[0])
    return _row_to_job(row)


def actualizar_estado(job_id: int, estado: EstadoJob) -> None:
    """Cambia el estado de un job."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_jobs SET estado = %s, updated_at = now() WHERE id = %s",
                (estado.value, job_id),
            )
        conn.commit()


def marcar_completado(job_id: int, respuesta: str, traza_reintento: int | None = None) -> None:
    """Marca un job como completado con su respuesta final."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """UPDATE pending_jobs
                   SET estado = 'completado', respuesta = %s, traza_reintento = %s,
                       completed_at = now(), updated_at = now()
                   WHERE id = %s""",
                (respuesta, traza_reintento, job_id),
            )
        conn.commit()
    logger.info("Job %d completado (traza_reintento=%s)", job_id, traza_reintento)


def marcar_fallido(job_id: int, error: str) -> None:
    """Marca un job como fallido."""
    with psycopg.connect(settings.psycopg_dsn) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE pending_jobs SET estado = 'fallido', error = %s, updated_at = now() WHERE id = %s",
                (error, job_id),
            )
        conn.commit()
    logger.warning("Job %d fallido: %s", job_id, error)
