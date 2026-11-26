"""Preço para quem não usa Pix nem saldo do Mercado Pago, lido nas páginas de busca e de ofertas."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0023_listing_regular_price"
down_revision = "0022_school_search"
branch_labels = None
depends_on = None

def upgrade():
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("listings")}
    if "regular_price" not in cols:
        with op.batch_alter_table("listings") as batch:
            batch.add_column(sa.Column("regular_price", sa.Numeric(12, 2), nullable=True))

def downgrade():
    with op.batch_alter_table("listings") as batch:
        batch.drop_column("regular_price")
