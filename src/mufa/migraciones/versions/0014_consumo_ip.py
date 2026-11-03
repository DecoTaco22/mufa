"""consumo de cada IP de cliente por hora, de NetFlow / IPFIX (Pro)

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-02 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0014"
down_revision: str | Sequence[str] | None = "0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "consumo_ip",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=False),
        sa.Column("hora", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bajada", sa.BigInteger(), nullable=False),
        sa.Column("subida", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ip", "hora", name="uq_consumo_ip"),
    )
    with op.batch_alter_table("consumo_ip", schema=None) as batch_op:
        batch_op.create_index("ix_consumo_ip_hora", ["hora"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("consumo_ip", schema=None) as batch_op:
        batch_op.drop_index("ix_consumo_ip_hora")
    op.drop_table("consumo_ip")
