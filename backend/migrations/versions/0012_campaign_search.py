"""Busca de produtos dentro da campanha: histórico, resultados, produtos da campanha, dono e segmentação oficial."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0012_campaign_search"
down_revision = "0011_catalog"
branch_labels = None
depends_on = None

def _columns(bind, table):
    return {c["name"] for c in inspect(bind).get_columns(table)}

def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    cols = _columns(bind, "campaigns")
    with op.batch_alter_table("campaigns") as batch:
        if "owner_id" not in cols:
            batch.add_column(sa.Column("owner_id", sa.Integer, nullable=True))
            batch.create_foreign_key("fk_campaigns_owner", "users", ["owner_id"], ["id"], ondelete="CASCADE")
            batch.create_index("ix_campaigns_owner_id", ["owner_id"])
        for name in ("niche_ids", "ml_categories", "include_keywords", "exclude_keywords"):
            if name not in cols:
                batch.add_column(sa.Column(name, sa.Text, nullable=False, server_default="[]"))
    # Campanhas existentes passam a pertencer ao primeiro usuário (o sistema tinha um só).
    op.execute("UPDATE campaigns SET owner_id = (SELECT MIN(id) FROM users) WHERE owner_id IS NULL")
    if "campaign_searches" not in tables:
        op.create_table(
            "campaign_searches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False),
            sa.Column("niche_id", sa.Integer, sa.ForeignKey("niches.id", ondelete="SET NULL"), nullable=True),
            sa.Column("niche_name", sa.String(120), nullable=False, server_default=""),
            sa.Column("categories", sa.Text, nullable=False, server_default="[]"),
            sa.Column("keywords", sa.Text, nullable=False, server_default="[]"),
            sa.Column("exclude_keywords", sa.Text, nullable=False, server_default="[]"),
            sa.Column("filters", sa.Text, nullable=False, server_default="{}"),
            sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
            sa.Column("result_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("matched_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("added_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("error", sa.Text, nullable=False, server_default=""),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_campaign_searches_campaign_id", "campaign_searches", ["campaign_id"])
        op.create_index("ix_campaign_searches_status", "campaign_searches", ["status"])
    if "campaign_search_results" not in tables:
        op.create_table(
            "campaign_search_results",
            sa.Column("search_id", sa.Integer, sa.ForeignKey("campaign_searches.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("listing_id", sa.Integer, sa.ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("matched", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("reason", sa.String(200), nullable=False, server_default=""),
        )
    if "campaign_products" not in tables:
        op.create_table(
            "campaign_products",
            sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("search_id", sa.Integer, sa.ForeignKey("campaign_searches.id", ondelete="SET NULL"), nullable=True),
            sa.Column("added_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_campaign_products_product_id", "campaign_products", ["product_id"])

def downgrade():
    op.drop_table("campaign_products")
    op.drop_table("campaign_search_results")
    op.drop_table("campaign_searches")
    with op.batch_alter_table("campaigns") as batch:
        for name in ("exclude_keywords", "include_keywords", "ml_categories", "niche_ids"):
            batch.drop_column(name)
        batch.drop_index("ix_campaigns_owner_id")
        batch.drop_constraint("fk_campaigns_owner", type_="foreignkey")
        batch.drop_column("owner_id")
