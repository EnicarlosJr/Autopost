"""Buscas automáticas: buscas salvas, anúncios encontrados, histórico de preço e agenda por grupo."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0009_searches"
down_revision = "0008_data_source_settings"
branch_labels = None
depends_on = None

MONEY = sa.Numeric(12, 2)

def upgrade():
    tables = set(inspect(op.get_bind()).get_table_names())
    if "searches" not in tables:
        op.create_table(
            "searches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("terms", sa.Text, nullable=False, server_default=""),
            sa.Column("exclude_terms", sa.Text, nullable=False, server_default=""),
            sa.Column("min_price", MONEY, nullable=True),
            sa.Column("max_price", MONEY, nullable=True),
            sa.Column("min_discount", sa.Integer, nullable=False, server_default="0"),
            sa.Column("min_rating", sa.Float, nullable=True),
            sa.Column("free_shipping_only", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("group_name", sa.String(160), nullable=False, server_default=""),
            sa.Column("mode", sa.String(20), nullable=False, server_default="approval"),
            sa.Column("interval_minutes", sa.Integer, nullable=False, server_default="120"),
            sa.Column("max_per_run", sa.Integer, nullable=False, server_default="5"),
            sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_result", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_searches_next_run_at", "searches", ["next_run_at"])
    if "listings" not in tables:
        op.create_table(
            "listings",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("external_id", sa.String(40), nullable=False),
            sa.Column("search_id", sa.Integer, sa.ForeignKey("searches.id", ondelete="SET NULL"), nullable=True),
            sa.Column("term", sa.String(160), nullable=False, server_default=""),
            sa.Column("url", sa.String(2048), nullable=False),
            sa.Column("title", sa.String(500), nullable=False, server_default=""),
            sa.Column("image_url", sa.String(2048), nullable=False, server_default=""),
            sa.Column("seller", sa.String(160), nullable=False, server_default=""),
            sa.Column("price", MONEY, nullable=True),
            sa.Column("original_price", MONEY, nullable=True),
            sa.Column("price_note", sa.String(60), nullable=False, server_default=""),
            sa.Column("discount_pct", sa.Integer, nullable=True),
            sa.Column("rating", sa.Float, nullable=True),
            sa.Column("sold", sa.Integer, nullable=True),
            sa.Column("free_shipping", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("min_price_30d", MONEY, nullable=True),
            sa.Column("score", sa.Integer, nullable=False, server_default="0"),
            sa.Column("matches", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("reject_reason", sa.String(200), nullable=False, server_default=""),
            sa.Column("status", sa.String(20), nullable=False, server_default="new"),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
            sa.Column("publication_id", sa.Integer, sa.ForeignKey("publications.id", ondelete="SET NULL"), nullable=True),
            sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_listings_external_id", "listings", ["external_id"], unique=True)
        op.create_index("ix_listings_search_id", "listings", ["search_id"])
        op.create_index("ix_listings_status", "listings", ["status"])
        op.create_index("ix_listings_score", "listings", ["score"])
    if "price_history" not in tables:
        op.create_table(
            "price_history",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("listing_id", sa.Integer, sa.ForeignKey("listings.id", ondelete="CASCADE"), nullable=False),
            sa.Column("price", MONEY, nullable=False),
            sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_price_history_listing_id", "price_history", ["listing_id"])
        op.create_index("ix_price_history_seen_at", "price_history", ["seen_at"])
    if "group_schedules" not in tables:
        op.create_table(
            "group_schedules",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("group_name", sa.String(160), nullable=False, unique=True),
            sa.Column("start_hour", sa.Integer, nullable=False, server_default="8"),
            sa.Column("end_hour", sa.Integer, nullable=False, server_default="22"),
            sa.Column("max_per_day", sa.Integer, nullable=False, server_default="12"),
            sa.Column("gap_minutes", sa.Integer, nullable=False, server_default="40"),
            sa.Column("repost_days", sa.Integer, nullable=False, server_default="7"),
        )

def downgrade():
    for table in ("price_history", "listings", "group_schedules", "searches"):
        op.drop_table(table)
