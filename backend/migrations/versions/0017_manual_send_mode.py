"""Forma de envio das ofertas avulsas (Configurações) e escolha por publicação."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0017_manual_send_mode"
down_revision = "0016_send_mode"
branch_labels = None
depends_on = None

def _cols(table):
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}

def upgrade():
    cols = _cols("automation_rules")
    with op.batch_alter_table("automation_rules") as batch:
        if "send_mode" not in cols:
            batch.add_column(sa.Column("send_mode", sa.String(10), nullable=False, server_default="preview"))
        if "watermark_text" not in cols:
            batch.add_column(sa.Column("watermark_text", sa.String(80), nullable=False, server_default=""))
        if "watermark_handle" not in cols:
            batch.add_column(sa.Column("watermark_handle", sa.String(60), nullable=False, server_default=""))
    if "send_mode_choice" not in _cols("publications"):
        with op.batch_alter_table("publications") as batch:
            batch.add_column(sa.Column("send_mode_choice", sa.String(10), nullable=True))

def downgrade():
    with op.batch_alter_table("publications") as batch:
        batch.drop_column("send_mode_choice")
    with op.batch_alter_table("automation_rules") as batch:
        for name in ("watermark_handle", "watermark_text", "send_mode"):
            batch.drop_column(name)
