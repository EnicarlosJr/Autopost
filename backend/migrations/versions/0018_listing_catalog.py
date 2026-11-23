"""Produto de catálogo do anúncio, usado para agrupar o mesmo produto vendido por lojas diferentes."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0018_listing_catalog"
down_revision = "0017_manual_send_mode"
branch_labels = None
depends_on = None

def upgrade():
    bind = op.get_bind()
    if "catalog_product_id" not in {c["name"] for c in inspect(bind).get_columns("listings")}:
        with op.batch_alter_table("listings") as batch:
            batch.add_column(sa.Column("catalog_product_id", sa.String(20), nullable=True))
    if "ix_listings_catalog_product_id" not in {i["name"] for i in inspect(bind).get_indexes("listings")}:
        op.create_index("ix_listings_catalog_product_id", "listings", ["catalog_product_id"])

def downgrade():
    op.drop_index("ix_listings_catalog_product_id", table_name="listings")
    with op.batch_alter_table("listings") as batch:
        batch.drop_column("catalog_product_id")
