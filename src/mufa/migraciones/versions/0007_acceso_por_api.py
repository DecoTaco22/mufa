"""acceso por api de routeros y alcance de equipos sin snmp

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-06 03:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0007"
down_revision: str | Sequence[str] | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("equipos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("acceso", sa.String(length=8), server_default="ssh", nullable=False)
        )
    with op.batch_alter_table("estado_equipos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("alcanzable", sa.Boolean(), server_default=sa.false(), nullable=False)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("estado_equipos", schema=None) as batch_op:
        batch_op.drop_column("alcanzable")
    with op.batch_alter_table("equipos", schema=None) as batch_op:
        batch_op.drop_column("acceso")
