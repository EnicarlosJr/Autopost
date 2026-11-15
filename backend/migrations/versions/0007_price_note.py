"""Condição do preço exibido (por exemplo, "no Pix")."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0007_price_note"
down_revision = "0006_publication_flow"
branch_labels = None
depends_on = None

def upgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("products")}
    if "price_note" not in columns:
        op.add_column("products", sa.Column("price_note", sa.String(60), nullable=False, server_default=""))

def downgrade():
    columns = {c["name"] for c in inspect(op.get_bind()).get_columns("products")}
    if "price_note" in columns:
        op.drop_column("products", "price_note")
