"""potencia diaria de cada ONU y aviso de señal que se degrada (OLT GPON, Pro)

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-02 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0013"
down_revision: str | Sequence[str] | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "potencia_onu_diaria",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("onu_id", sa.Integer(), nullable=False),
        sa.Column("dia", sa.Date(), nullable=False),
        sa.Column("muestras", sa.Integer(), nullable=False),
        sa.Column("suma_rx", sa.Double(), nullable=False),
        sa.Column("min_rx", sa.Double(), nullable=False),
        sa.ForeignKeyConstraint(["onu_id"], ["onus_gpon.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("onu_id", "dia", name="uq_potencia_onu_diaria"),
    )
    with op.batch_alter_table("potencia_onu_diaria", schema=None) as batch_op:
        batch_op.create_index("ix_potencia_onu_diaria_dia", ["dia"], unique=False)
    with op.batch_alter_table("onus_gpon", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("aviso_tendencia", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("onus_gpon", schema=None) as batch_op:
        batch_op.drop_column("aviso_tendencia")
    with op.batch_alter_table("potencia_onu_diaria", schema=None) as batch_op:
        batch_op.drop_index("ix_potencia_onu_diaria_dia")
    op.drop_table("potencia_onu_diaria")
