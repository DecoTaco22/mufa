"""trafico diario por interfaz, para el historial largo y la capacidad

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-13 06:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: str | Sequence[str] | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "trafico_diario",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("if_index", sa.Integer(), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("velocidad_mbps", sa.Integer(), nullable=True),
        sa.Column("muestras", sa.Integer(), nullable=False),
        sa.Column("prom_entrada", sa.Double(), nullable=False),
        sa.Column("prom_salida", sa.Double(), nullable=False),
        sa.Column("p95_entrada", sa.Double(), nullable=False),
        sa.Column("p95_salida", sa.Double(), nullable=False),
        sa.Column("max_entrada", sa.Double(), nullable=False),
        sa.Column("max_salida", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipo_id", "if_index", "dia", name="uq_trafico_diario"),
    )
    with op.batch_alter_table("trafico_diario", schema=None) as batch_op:
        batch_op.create_index("ix_trafico_diario_dia", ["dia"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("trafico_diario", schema=None) as batch_op:
        batch_op.drop_index("ix_trafico_diario_dia")
    op.drop_table("trafico_diario")
