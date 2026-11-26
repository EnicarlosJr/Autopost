"""Busca de equivalentes das listas escolares, preço normal x Pix/Mercado Pago e conferência do link de afiliado."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0022_school_search"
down_revision = "0021_school_public"
branch_labels = None
depends_on = None

def upgrade():
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("products")}
    with op.batch_alter_table("products") as batch:
        if "regular_price" not in cols:
            batch.add_column(sa.Column("regular_price", sa.Numeric(12, 2), nullable=True))
        if "price_conditions" not in cols:
            batch.add_column(sa.Column("price_conditions", sa.String(300), nullable=False, server_default=""))
        if "affiliate_ok" not in cols:
            batch.add_column(sa.Column("affiliate_ok", sa.Boolean, nullable=True))
        if "affiliate_checked_at" not in cols:
            batch.add_column(sa.Column("affiliate_checked_at", sa.DateTime(timezone=True), nullable=True))
    cols = {c["name"] for c in insp.get_columns("school_list_items")}
    if "dismissed" not in cols:
        with op.batch_alter_table("school_list_items") as batch:
            batch.add_column(sa.Column("dismissed", sa.Text, nullable=False, server_default="[]"))
    if "school_item_searches" not in set(insp.get_table_names()):
        op.create_table("school_item_searches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("item_id", sa.Integer, sa.ForeignKey("school_list_items.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("reference_product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
            sa.Column("reason", sa.String(40), nullable=False, server_default="manual"),
            sa.Column("status", sa.String(20), nullable=False, server_default="queued", index=True),
            sa.Column("terms", sa.Text, nullable=False, server_default="[]"),
            sa.Column("suggestions", sa.Text, nullable=False, server_default="{}"),
            sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("error", sa.String(500), nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True))

def downgrade():
    op.drop_table("school_item_searches")
    with op.batch_alter_table("school_list_items") as batch:
        batch.drop_column("dismissed")
    with op.batch_alter_table("products") as batch:
        for name in ("affiliate_checked_at", "affiliate_ok", "price_conditions", "regular_price"):
            batch.drop_column(name)
