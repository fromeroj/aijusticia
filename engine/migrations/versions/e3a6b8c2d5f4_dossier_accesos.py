"""M1: grants de acceso a dossiers + M2 prep (bufetes.tipo) + A7 (frase_salt)

- dossier_accesos: el dossier pertenece a quien lo crea; abogados/despachos
  acceden por grants revocables (historial = auditoría LFPDPPP).
- bufetes.tipo: 'individual' (abogado de una persona) | 'firma'.
- actores.frase_salt + frase_hash_saltado: verificación con sal por actor;
  frase_hash queda como índice determinístico SOLO para lookup.

Revision ID: e3a6b8c2d5f4
Revises: d9e2f5a4b7c3
"""
from alembic import op

revision = "e3a6b8c2d5f4"
down_revision = "d9e2f5a4b7c3"


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS dossier_accesos (
            id BIGSERIAL PRIMARY KEY,
            dossier_id UUID NOT NULL REFERENCES dossiers(id),
            actor_id UUID REFERENCES actores(id),
            bufete_id UUID REFERENCES bufetes(id),
            rol TEXT NOT NULL DEFAULT 'lectura'
                CHECK (rol IN ('lectura', 'edicion')),
            otorgado_por UUID NOT NULL REFERENCES actores(id),
            creado_en TIMESTAMPTZ NOT NULL DEFAULT now(),
            revocado_en TIMESTAMPTZ,
            CHECK (actor_id IS NOT NULL OR bufete_id IS NOT NULL),
            CHECK (NOT (actor_id IS NOT NULL AND bufete_id IS NOT NULL))
        );
        CREATE INDEX IF NOT EXISTS idx_accesos_dossier
            ON dossier_accesos(dossier_id) WHERE revocado_en IS NULL;
        CREATE INDEX IF NOT EXISTS idx_accesos_actor
            ON dossier_accesos(actor_id) WHERE revocado_en IS NULL;
        CREATE INDEX IF NOT EXISTS idx_accesos_bufete
            ON dossier_accesos(bufete_id) WHERE revocado_en IS NULL;

        ALTER TABLE bufetes ADD COLUMN IF NOT EXISTS tipo TEXT NOT NULL DEFAULT 'firma';

        ALTER TABLE actores ADD COLUMN IF NOT EXISTS frase_salt TEXT;
        ALTER TABLE actores ADD COLUMN IF NOT EXISTS frase_hash_saltado TEXT;
    """)


def downgrade() -> None:
    op.execute("""
        DROP TABLE IF EXISTS dossier_accesos;
        ALTER TABLE bufetes DROP COLUMN IF EXISTS tipo;
        ALTER TABLE actores DROP COLUMN IF EXISTS frase_salt;
        ALTER TABLE actores DROP COLUMN IF EXISTS frase_hash_saltado;
    """)
