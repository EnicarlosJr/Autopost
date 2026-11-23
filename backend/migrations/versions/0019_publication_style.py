"""Padrão do perfil para mensagem e foto (#publi, selo de desconto) e personalização por campanha."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0019_publication_style"
down_revision = "0018_listing_catalog"
branch_labels = None
depends_on = None

def _cols(table):
    return {c["name"] for c in inspect(op.get_bind()).get_columns(table)}

def upgrade():
    cols = _cols("automation_rules")
    with op.batch_alter_table("automation_rules") as batch:
        if "disclosure_text" not in cols:
            batch.add_column(sa.Column("disclosure_text", sa.String(40), nullable=False, server_default="#publi"))
        if "show_discount" not in cols:
            batch.add_column(sa.Column("show_discount", sa.Boolean, nullable=False, server_default=sa.true()))
    cols = _cols("campaigns")
    added = "custom_style" not in cols
    with op.batch_alter_table("campaigns") as batch:
        if added:
            batch.add_column(sa.Column("custom_style", sa.Boolean, nullable=False, server_default=sa.false()))
        if "message_template" not in cols:
            batch.add_column(sa.Column("message_template", sa.Text, nullable=False, server_default=""))
    if added:
        # Campanhas que já tinham marca d'água própria continuam com ela; as outras passam a usar o padrão do perfil.
        op.get_bind().execute(sa.text("UPDATE campaigns SET custom_style = :yes WHERE watermark_text <> '' OR watermark_handle <> ''"), {"yes": True})

def downgrade():
    with op.batch_alter_table("campaigns") as batch:
        batch.drop_column("message_template")
        batch.drop_column("custom_style")
    with op.batch_alter_table("automation_rules") as batch:
        batch.drop_column("show_discount")
        batch.drop_column("disclosure_text")
