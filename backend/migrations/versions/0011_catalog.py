"""Catálogo oficial de categorias do Mercado Livre, categorias favoritas e nichos do perfil."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0011_catalog"
down_revision = "0010_campaigns"
branch_labels = None
depends_on = None

def _columns(bind, table):
    return {c["name"] for c in inspect(bind).get_columns(table)}

def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "ml_categories" not in tables:
        op.create_table(
            "ml_categories",
            sa.Column("id", sa.String(20), primary_key=True),
            sa.Column("name", sa.String(200), nullable=False),
            sa.Column("search_name", sa.String(200), nullable=False),
            sa.Column("parent_id", sa.String(20), nullable=True),
            sa.Column("path_ids", sa.Text, nullable=False, server_default=""),
            sa.Column("path_names", sa.Text, nullable=False, server_default=""),
            sa.Column("depth", sa.Integer, nullable=False, server_default="0"),
            sa.Column("is_leaf", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("children_count", sa.Integer, nullable=False, server_default="0"),
            sa.Column("total_items", sa.Integer, nullable=False, server_default="0"),
            sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_ml_categories_parent_id", "ml_categories", ["parent_id"])
        op.create_index("ix_ml_categories_search_name", "ml_categories", ["search_name"])
    if "favorite_categories" not in tables:
        op.create_table(
            "favorite_categories",
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("category_id", sa.String(20), sa.ForeignKey("ml_categories.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "niches" not in tables:
        op.create_table(
            "niches",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("description", sa.Text, nullable=False, server_default=""),
            sa.Column("favorite", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
            sa.Column("include_keywords", sa.Text, nullable=False, server_default="[]"),
            sa.Column("exclude_keywords", sa.Text, nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("owner_id", "name", name="uq_niche_owner_name"),
        )
        op.create_index("ix_niches_owner_id", "niches", ["owner_id"])
    if "niche_categories" not in tables:
        op.create_table(
            "niche_categories",
            sa.Column("niche_id", sa.Integer, sa.ForeignKey("niches.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("category_id", sa.String(20), sa.ForeignKey("ml_categories.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("include_children", sa.Boolean, nullable=False, server_default=sa.true()),
        )
    if "ml_category_id" not in _columns(bind, "products"):
        op.add_column("products", sa.Column("ml_category_id", sa.String(20), nullable=True))
        op.create_index("ix_products_ml_category_id", "products", ["ml_category_id"])
    listings = _columns(bind, "listings")
    if "ml_category_id" not in listings:
        op.add_column("listings", sa.Column("ml_category_id", sa.String(20), nullable=True))
        op.create_index("ix_listings_ml_category_id", "listings", ["ml_category_id"])
    if "category_source" not in listings:
        op.add_column("listings", sa.Column("category_source", sa.String(20), nullable=False, server_default=""))
    # Decisão do usuário: a categoria em texto livre dos produtos antigos não é aproveitada (começa do zero).
    op.execute("UPDATE products SET category = ''")

def downgrade():
    op.drop_column("listings", "category_source")
    op.drop_column("listings", "ml_category_id")
    op.drop_column("products", "ml_category_id")
    for table in ("niche_categories", "niches", "favorite_categories", "ml_categories"):
        op.drop_table(table)
