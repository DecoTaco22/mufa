"""nombre de usuario, email opcional y verificación en dos pasos

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-05

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(sa.Column("usuario", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("totp_secreto_cifrado", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("totp_activo", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("totp_ultimo_paso", sa.Integer(), nullable=False, server_default="0")
        )

    # Usuarios que ya existían: el nombre de usuario sale de la parte local
    # del email; si se repite, se le agrega el id.
    conexion = op.get_bind()
    usados: set[str] = set()
    for id_, email in conexion.execute(sa.text("SELECT id, email FROM usuarios ORDER BY id")):
        base = str(email).split("@")[0].lower()[:24] or "usuario"
        nombre = base if base not in usados else f"{base}{id_}"
        usados.add(nombre)
        conexion.execute(
            sa.text("UPDATE usuarios SET usuario = :nombre WHERE id = :id"),
            {"nombre": nombre, "id": id_},
        )

    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.alter_column("usuario", existing_type=sa.String(length=32), nullable=False)
        batch_op.alter_column("email", existing_type=sa.String(length=254), nullable=True)
        batch_op.create_index(batch_op.f("ix_usuarios_usuario"), ["usuario"], unique=True)


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_usuarios_usuario"))
        batch_op.alter_column("email", existing_type=sa.String(length=254), nullable=False)
        batch_op.drop_column("totp_ultimo_paso")
        batch_op.drop_column("totp_activo")
        batch_op.drop_column("totp_secreto_cifrado")
        batch_op.drop_column("usuario")
