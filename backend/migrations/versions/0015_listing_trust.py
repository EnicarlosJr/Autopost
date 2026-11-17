"""Sinais de confiabilidade dos anúncios: loja oficial e Full."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0015_listing_trust"
down_revision = "0014_niche_gender"
branch_labels = None
depends_on = None

def upgrade():
    cols = {c["name"] for c in inspect(op.get_bind()).get_columns("listings")}
    with op.batch_alter_table("listings") as batch:
        if "official_store" not in cols:
            batch.add_column(sa.Column("official_store", sa.Boolean, nullable=False, server_default=sa.false()))
        if "fulfillment" not in cols:
            batch.add_column(sa.Column("fulfillment", sa.Boolean, nullable=False, server_default=sa.false()))

def downgrade():
    with op.batch_alter_table("listings") as batch:
        batch.drop_column("fulfillment")
        batch.drop_column("official_store")
