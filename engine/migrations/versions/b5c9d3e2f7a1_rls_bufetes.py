"""RLS: aislamiento por bufete en tablas de datos de despacho.

Revision ID: b5c9d3e2f7a1
Revises: a3f8b2c1d4e5
"""
from alembic import op
import sqlalchemy as sa

revision = "b5c9d3e2f7a1"
down_revision = "a3f8b2c1d4e5"


# Tablas con bufete_id que deben aislarse por RLS:
# - dossiers (casos de ciudadanos compartidos con despachos — agregar bufete_id)
# - trazas (actividad del sistema, NO aislar)
# - documentos (corpus público, NO aislar)
#
# El RLS funciona con la variable de sesión: SET app.bufete_id = '<uuid>'

RLS_TABLES = ["dossiers"]

BUfETE_FK = """
-- Agregar bufete_id a dossiers (con qué despacho está compartido el caso)
ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS bufete_id UUID REFERENCES bufetes(id);
CREATE INDEX IF NOT EXISTS idx_dossiers_bufete ON dossiers(bufete_id);
"""


def upgrade() -> None:
    # 1) bufete_id en dossiers
    op.execute("ALTER TABLE dossiers ADD COLUMN IF NOT EXISTS bufete_id UUID REFERENCES bufetes(id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_dossiers_bufete ON dossiers(bufete_id)")

    # 2) Activar RLS en las tablas
    for table in RLS_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")

    # 3) Políticas:
    #    - Sin bufete_id en sesión (SET app.bufete_id = ''): acceso público
    #      (ciudadano accede SUS dossiers via actor_id, no via RLS)
    #    - Con bufete_id: solo dossiers de ese bufete
    op.execute("""
        CREATE POLICY dossiers_isolation ON dossiers
        USING (
            current_setting('app.bufete_id', true) IS NULL
            OR current_setting('app.bufete_id', true) = ''
            OR current_setting('app.bufete_id', true) = 'public'
            OR bufete_id::text = current_setting('app.bufete_id', true)
        )
    """)

    # 4) El rol aijusticia necesita BYPASSRLS off pero sí poder leer corpus
    #    (documentos/chunks no tienen RLS, así que se acceden normal)
    op.execute("ALTER ROLE aijusticia NOBYPASSRLS")


def downgrade() -> None:
    for table in RLS_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {table}_isolation ON {table}")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE dossiers DROP COLUMN IF EXISTS bufete_id")
