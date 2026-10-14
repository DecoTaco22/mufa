"""avisos al equipo: contactos, guardias e incidentes (mufa Pro)

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-14 08:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: str | Sequence[str] | None = "0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "contactos_noc",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=120), nullable=False),
        sa.Column("telegram_chat", sa.String(length=64), nullable=True),
        sa.Column("codigo", sa.String(length=32), nullable=False),
        sa.Column("supervisor", sa.Boolean(), nullable=False),
        sa.Column("activo", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("codigo"),
    )
    op.create_table(
        "guardias",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contacto_id", sa.Integer(), nullable=False),
        sa.Column("dias", sa.String(length=7), nullable=False),
        sa.Column("desde", sa.String(length=5), nullable=False),
        sa.Column("hasta", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["contacto_id"], ["contactos_noc.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "incidentes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("evento_id", sa.Integer(), nullable=True),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("objeto", sa.String(length=255), nullable=False),
        sa.Column("titulo", sa.String(length=255), nullable=False),
        sa.Column("detalle", sa.JSON(), nullable=False),
        sa.Column("estado", sa.String(length=16), nullable=False),
        sa.Column("nivel", sa.Integer(), nullable=False),
        sa.Column("tomado_por_id", sa.Integer(), nullable=True),
        sa.Column("tomado", sa.DateTime(timezone=True), nullable=True),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resuelto", sa.DateTime(timezone=True), nullable=True),
        sa.Column("mensajes", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["evento_id"], ["eventos.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tomado_por_id"], ["contactos_noc.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("incidentes", schema=None) as batch_op:
        batch_op.create_index("ix_incidentes_estado", ["estado"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("incidentes", schema=None) as batch_op:
        batch_op.drop_index("ix_incidentes_estado")
    op.drop_table("incidentes")
    op.drop_table("guardias")
    op.drop_table("contactos_noc")
