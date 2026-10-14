"""OLT GPON y sus ONU (mufa Pro)

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-14 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0010"
down_revision: str | Sequence[str] | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "olts",
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("perfil", sa.String(length=16), nullable=False),
        sa.Column("umbral_rx_dbm", sa.Double(), nullable=False),
        sa.Column("ultimo_sondeo", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("equipo_id"),
    )
    op.create_table(
        "onus_gpon",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("pon_if_index", sa.BigInteger(), nullable=False),
        sa.Column("onu_id", sa.Integer(), nullable=False),
        sa.Column("puerto", sa.String(length=64), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("serie", sa.String(length=64), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("causa", sa.String(length=64), nullable=False),
        sa.Column("rx_dbm", sa.Double(), nullable=True),
        sa.Column("tx_dbm", sa.Double(), nullable=True),
        sa.Column("distancia_m", sa.Integer(), nullable=True),
        sa.Column("cambio", sa.DateTime(timezone=True), nullable=False),
        sa.Column("visto", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aviso_senal", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipo_id", "pon_if_index", "onu_id", name="uq_onu_gpon"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("onus_gpon")
    op.drop_table("olts")
