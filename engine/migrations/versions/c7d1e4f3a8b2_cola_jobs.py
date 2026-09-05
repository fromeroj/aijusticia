"""Tabla cola_jobs para SKIP LOCKED queue

Revision ID: c7d1e4f3a8b2
Revises: b5c9d3e2f7a1
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d1e4f3a8b2"
down_revision = "b5c9d3e2f7a1"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS cola_jobs (
            id BIGSERIAL PRIMARY KEY,
            tipo TEXT NOT NULL,
            payload JSONB DEFAULT '{}',
            prioridad SMALLINT DEFAULT 5,
            estado TEXT DEFAULT 'pendiente',
            worker_id TEXT,
            intentos SMALLINT DEFAULT 0,
            resultado JSONB,
            ultimo_error TEXT,
            creado_en TIMESTAMPTZ DEFAULT now(),
            tomado_en TIMESTAMPTZ,
            terminado_en TIMESTAMPTZ
        );
        CREATE INDEX IF NOT EXISTS idx_cola_pendiente ON cola_jobs(estado, prioridad, creado_en)
            WHERE estado = 'pendiente';
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cola_jobs")
