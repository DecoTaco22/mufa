"""respaldos y monitoreo

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-05 00:23:09.454480

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "estado_equipos",
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("en_linea", sa.Boolean(), nullable=False),
        sa.Column("ultimo_sondeo", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ultimo_en_linea", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=False),
        sa.Column("sys_nombre", sa.String(length=255), nullable=False),
        sa.Column("sys_descripcion", sa.Text(), nullable=False),
        sa.Column("sys_object_id", sa.String(length=255), nullable=False),
        sa.Column("marca_detectada", sa.String(length=32), nullable=False),
        sa.Column("uptime_segundos", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("equipo_id"),
    )
    op.create_table(
        "muestras_interfaz",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("momento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("if_index", sa.Integer(), nullable=False),
        sa.Column("nombre", sa.String(length=255), nullable=False),
        sa.Column("operativa", sa.Boolean(), nullable=False),
        sa.Column("velocidad_mbps", sa.Integer(), nullable=True),
        sa.Column("octetos_entrada", sa.BigInteger(), nullable=False),
        sa.Column("octetos_salida", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("muestras_interfaz", schema=None) as batch_op:
        batch_op.create_index("ix_muestras_equipo_momento", ["equipo_id", "momento"], unique=False)

    op.create_table(
        "respaldos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipo_id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=True),
        sa.Column("origen", sa.String(length=16), nullable=False),
        sa.Column("creado", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmado", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hash_normalizado", sa.String(length=64), nullable=False),
        sa.Column("tamano", sa.Integer(), nullable=False),
        sa.Column("contenido_cifrado", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["equipo_id"], ["equipos.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("respaldos", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_respaldos_equipo_id"), ["equipo_id"], unique=False)

    # Equipos que ya existían: quedan sin monitoreo SNMP hasta configurarlo.
    with op.batch_alter_table("equipos", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("snmp_version", sa.String(length=4), nullable=False, server_default="")
        )
        batch_op.add_column(
            sa.Column(
                "snmp_protocolo_auth", sa.String(length=8), nullable=False, server_default="sha256"
            )
        )
        batch_op.add_column(
            sa.Column(
                "snmp_protocolo_priv", sa.String(length=8), nullable=False, server_default="aes"
            )
        )
        batch_op.add_column(
            sa.Column("snmp_puerto", sa.Integer(), nullable=False, server_default="161")
        )
        batch_op.add_column(sa.Column("snmp_comunidad_cifrada", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("snmp_usuario", sa.String(length=64), nullable=False, server_default="")
        )
        batch_op.add_column(sa.Column("snmp_auth_cifrada", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("snmp_priv_cifrada", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("equipos", schema=None) as batch_op:
        batch_op.drop_column("snmp_priv_cifrada")
        batch_op.drop_column("snmp_auth_cifrada")
        batch_op.drop_column("snmp_usuario")
        batch_op.drop_column("snmp_comunidad_cifrada")
        batch_op.drop_column("snmp_puerto")
        batch_op.drop_column("snmp_protocolo_priv")
        batch_op.drop_column("snmp_protocolo_auth")
        batch_op.drop_column("snmp_version")

    with op.batch_alter_table("respaldos", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_respaldos_equipo_id"))

    op.drop_table("respaldos")
    with op.batch_alter_table("muestras_interfaz", schema=None) as batch_op:
        batch_op.drop_index("ix_muestras_equipo_momento")

    op.drop_table("muestras_interfaz")
    op.drop_table("estado_equipos")
