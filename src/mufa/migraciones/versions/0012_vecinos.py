"""vecinos de cada equipo (LLDP, CDP, MikroTik) para el mapa de topología

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-20 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0012"
down_revision: str | Sequence[str] | None = "0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "vecinos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("interfaz", sa.String(length=255), nullable=False),
        sa.Column("remoto_nombre", sa.String(length=255), nullable=False),
        sa.Column("remoto_puerto", sa.String(length=255), nullable=False),
        sa.Column("remoto_ip", sa.String(length=64), nullable=False),
        sa.Column("plataforma", sa.String(length=255), nullable=False),
        sa.Column("fuente", sa.String(length=16), nullable=False),
        sa.Column("visto", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("vecinos", schema=None) as batch_op:
        batch_op.create_index("ix_vecinos_equipo_id", ["equipo_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("vecinos", schema=None) as batch_op:
        batch_op.drop_index("ix_vecinos_equipo_id")
    op.drop_table("vecinos")
