"""Tabla refresh_tokens para JWT rotativo

Revision ID: a3f8b2c1d4e5
Revises: 2b66f5123acf
"""
from alembic import op
import sqlalchemy as sa

revision = "a3f8b2c1d4e5"
down_revision = "2b66f5123acf"


def upgrade() -> None:
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("actor_id", sa.UUID(), nullable=False, index=True),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dispositivo", sa.String(200), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("refresh_tokens")
