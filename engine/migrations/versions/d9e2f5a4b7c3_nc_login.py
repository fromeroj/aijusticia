"""actores.nc_login: vincula usuario Nextcloud del despacho con actor del engine

Revision ID: d9e2f5a4b7c3
Revises: c7d1e4f3a8b2
"""
from alembic import op

revision = "d9e2f5a4b7c3"
down_revision = "c7d1e4f3a8b2"


def upgrade() -> None:
    op.execute("""
        ALTER TABLE actores ADD COLUMN IF NOT EXISTS nc_login TEXT;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_actores_nc_login
            ON actores(nc_login) WHERE nc_login IS NOT NULL;
    """)


def downgrade() -> None:
    op.execute("""
        DROP INDEX IF EXISTS idx_actores_nc_login;
        ALTER TABLE actores DROP COLUMN IF EXISTS nc_login;
    """)
