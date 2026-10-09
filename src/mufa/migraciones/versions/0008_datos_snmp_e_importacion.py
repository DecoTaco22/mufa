"""datos del equipo por snmp, importacion de ips y vlans, interfaces vigiladas

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-06 05:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: str | Sequence[str] | None = "0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("estado_equipos", schema=None) as batch_op:
        for columna, largo in (
            ("ubicacion", 255),
            ("serie", 120),
            ("modelo", 120),
            ("version", 120),
        ):
            batch_op.add_column(
                sa.Column(columna, sa.String(length=largo), server_default="", nullable=False)
            )
    with op.batch_alter_table("direcciones_ip", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("interfaz", sa.String(length=255), server_default="", nullable=False)
        )
    op.create_table(
        "vlans_en_equipo",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("vlan_id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("interfaz", sa.String(length=255), nullable=False),
        sa.Column("nombre_en_equipo", sa.String(length=255), nullable=False),
        sa.Column("visto", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vlan_id"], ["vlans.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("vlan_id", "equipo_id", "interfaz", name="uq_vlan_equipo_interfaz"),
    )
    with op.batch_alter_table("vlans_en_equipo", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_vlans_en_equipo_vlan_id"), ["vlan_id"], unique=False)
    op.create_table(
        "interfaces_vigiladas",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("if_index", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("umbral_saturacion", sa.Integer(), nullable=False),
        sa.Column("minutos_saturacion", sa.Integer(), nullable=False),
        sa.Column("operativa", sa.Boolean(), nullable=True),
        sa.Column("saturada_desde", sa.DateTime(timezone=True), nullable=True),
        sa.Column("aviso_saturacion", sa.Boolean(), nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("equipo_id", "if_index", name="uq_vigilada_equipo_if"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("interfaces_vigiladas")
    with op.batch_alter_table("vlans_en_equipo", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_vlans_en_equipo_vlan_id"))
    op.drop_table("vlans_en_equipo")
    with op.batch_alter_table("direcciones_ip", schema=None) as batch_op:
        batch_op.drop_column("interfaz")
    with op.batch_alter_table("estado_equipos", schema=None) as batch_op:
        for columna in ("version", "modelo", "serie", "ubicacion"):
            batch_op.drop_column(columna)
