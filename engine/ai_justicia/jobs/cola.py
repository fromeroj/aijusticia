"""Cola de trabajos con PostgreSQL SKIP LOCKED (sin Redis, sin Celery).

Migra el modelo de pending_jobs a un sistema de cola atómica:
- encolar(): INSERT con estado 'pendiente'
- tomar(): SELECT ... FOR UPDATE SKIP LOCKED LIMIT 1 → atómico entre workers
- completar()/fallar(): UPDATE con resultado

Ventaja sobre polling simple: múltiples workers sin condiciones de carrera.
"""
from __future__ import annotations

import datetime
import json
import uuid

import psycopg

from ai_justicia.config import settings


def _conn():
    return psycopg.connect(
        host=settings.pg_host, port=settings.pg_port, dbname=settings.pg_db,
        user=settings.pg_user, password=settings.pg_password, autocommit=True)


def encolar(tipo: str, payload: dict, prioridad: int = 5) -> int:
    """Encola un trabajo. prioridad 1 = urgente, 5 = normal."""
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO cola_jobs (tipo, payload, prioridad, estado)
               VALUES (%s, %s, %s, 'pendiente') RETURNING id""",
            (tipo, json.dumps(payload, ensure_ascii=False), prioridad))
        return cur.fetchone()[0]


def tomar(worker_id: str, tipos: list[str] | None = None) -> dict | None:
    """Toma el siguiente trabajo pendiente (atómico via SKIP LOCKED).

    Devuelve {id, tipo, payload, intentos} o None si no hay nada.
    """
    with _conn() as conn:
        cur = conn.cursor()
        filtro = "AND tipo = ANY(%s)" if tipos else ""
        params = ([tipos] if tipos else []) + [worker_id]
        cur.execute(
            f"""
            WITH siguiente AS (
                SELECT id FROM cola_jobs
                WHERE estado = 'pendiente' {filtro}
                ORDER BY prioridad ASC, creado_en ASC
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE cola_jobs c
            SET estado = 'procesando',
                worker_id = %s,
                tomado_en = now(),
                intentos = c.intentos + 1
            FROM siguiente
            WHERE c.id = siguiente.id
            RETURNING c.id, c.tipo, c.payload, c.intentos
            """,
            params)
        row = cur.fetchone()
        if not row:
            return None
        return {"id": row[0], "tipo": row[1],
                "payload": row[2] if isinstance(row[2], dict) else (json.loads(row[2]) if row[2] else {}),
                "intentos": row[3]}


def completar(job_id: int, resultado: dict | None = None):
    with _conn() as conn:
        conn.cursor().execute(
            "UPDATE cola_jobs SET estado='completado', resultado=%s, terminado_en=now() WHERE id=%s",
            (json.dumps(resultado, ensure_ascii=False) if resultado else None, job_id))


def fallar(job_id: int, error: str, reintentar: bool = True):
    with _conn() as conn:
        cur = conn.cursor()
        if reintentar:
            cur.execute(
                """UPDATE cola_jobs
                   SET estado = CASE WHEN intentos >= 3 THEN 'fallido' ELSE 'pendiente' END,
                       ultimo_error = %s
                   WHERE id = %s""", (error[:500], job_id))
        else:
            cur.execute(
                "UPDATE cola_jobs SET estado='fallido', ultimo_error=%s, terminado_en=now() WHERE id=%s",
                (error[:500], job_id))


def stats() -> dict:
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT estado, count(*), min(creado_en)::text, max(creado_en)::text
            FROM cola_jobs GROUP BY estado
        """)
        return {r[0]: {"n": r[1], "desde": r[2], "hasta": r[3]} for r in cur.fetchall()}
