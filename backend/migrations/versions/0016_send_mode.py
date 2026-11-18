"""Envio com foto: forma de envio e marca d'água por campanha; endereço original da foto do produto."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0016_send_mode"
down_revision = "0015_listing_trust"
branch_labels = None
depends_on = None

def _cols(table):
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}

def upgrade():
    cols = _cols("campaigns")
    with op.batch_alter_table("campaigns") as batch:
        if "send_mode" not in cols:
            batch.add_column(sa.Column("send_mode", sa.String(10), nullable=False, server_default="preview"))
        if "watermark_text" not in cols:
            batch.add_column(sa.Column("watermark_text", sa.String(80), nullable=False, server_default=""))
        if "watermark_handle" not in cols:
            batch.add_column(sa.Column("watermark_handle", sa.String(60), nullable=False, server_default=""))
    if "image_source_url" not in _cols("products"):
        with op.batch_alter_table("products") as batch:
            batch.add_column(sa.Column("image_source_url", sa.String(2048), nullable=False, server_default=""))

def downgrade():
    with op.batch_alter_table("products") as batch:
        batch.drop_column("image_source_url")
    with op.batch_alter_table("campaigns") as batch:
        for name in ("watermark_handle", "watermark_text", "send_mode"):
            batch.drop_column(name)
