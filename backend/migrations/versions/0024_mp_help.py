"""Listas escolares: WhatsApp e mensagem para ajudar quem não tem conta no Mercado Pago."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0024_mp_help"
down_revision = "0023_listing_regular_price"
branch_labels = None
depends_on = None

def upgrade():
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("automation_rules")}
    with op.batch_alter_table("automation_rules") as batch:
        if "mp_help_whatsapp" not in cols:
            batch.add_column(sa.Column("mp_help_whatsapp", sa.String(20), nullable=False, server_default=""))
        if "mp_help_message" not in cols:
            batch.add_column(sa.Column("mp_help_message", sa.Text, nullable=False, server_default=""))

def downgrade():
    with op.batch_alter_table("automation_rules") as batch:
        batch.drop_column("mp_help_message")
        batch.drop_column("mp_help_whatsapp")
