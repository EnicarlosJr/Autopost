"""Campanhas: tags nos produtos, cadastro de grupos (categorias e ativo), campanhas e vínculo das publicações."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0010_campaigns"
down_revision = "0009_searches"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('pending','awaiting_approval','approved','scheduled','sending','paused')"

def _columns(bind, table):
    return {c["name"] for c in inspect(bind).get_columns(table)}

def upgrade():
    bind = op.get_bind()
    tables = set(inspect(bind).get_table_names())
    if "tags" not in _columns(bind, "products"):
        op.add_column("products", sa.Column("tags", sa.Text(), nullable=False, server_default="[]"))
    groups = _columns(bind, "group_schedules")
    if "categories" not in groups:
        op.add_column("group_schedules", sa.Column("categories", sa.Text(), nullable=False, server_default="[]"))
    if "active" not in groups:
        op.add_column("group_schedules", sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()))
    if "campaigns" not in tables:
        op.create_table(
            "campaigns",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("name", sa.String(120), nullable=False),
            sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
            sa.Column("product_ids", sa.Text, nullable=False, server_default="[]"),
            sa.Column("categories", sa.Text, nullable=False, server_default="[]"),
            sa.Column("exclude_categories", sa.Text, nullable=False, server_default="[]"),
            sa.Column("tags", sa.Text, nullable=False, server_default="[]"),
            sa.Column("tag_mode", sa.String(10), nullable=False, server_default="any"),
            sa.Column("exclude_tags", sa.Text, nullable=False, server_default="[]"),
            sa.Column("include_uncategorized", sa.Boolean, nullable=False, server_default=sa.false()),
            sa.Column("min_discount", sa.Integer, nullable=False, server_default="0"),
            sa.Column("groups", sa.Text, nullable=False, server_default="[]"),
            sa.Column("strategy", sa.String(20), nullable=False, server_default="balanced"),
            sa.Column("total_limit", sa.Integer, nullable=False, server_default="20"),
            sa.Column("block_size", sa.Integer, nullable=False, server_default="1"),
            sa.Column("interval_minutes", sa.Integer, nullable=False, server_default="5"),
            sa.Column("interval_max_minutes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("start_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("start_hour", sa.Integer, nullable=False, server_default="8"),
            sa.Column("end_hour", sa.Integer, nullable=False, server_default="22"),
            sa.Column("weekdays", sa.String(40), nullable=False, server_default="[0,1,2,3,4,5,6]"),
            sa.Column("daily_limit", sa.Integer, nullable=False, server_default="0"),
            sa.Column("pause_every", sa.Integer, nullable=False, server_default="0"),
            sa.Column("pause_minutes", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index("ix_campaigns_status", "campaigns", ["status"])
    if "campaign_id" not in _columns(bind, "publications"):
        with op.batch_alter_table("publications") as batch:
            batch.add_column(sa.Column("campaign_id", sa.Integer, nullable=True))
            batch.create_foreign_key("fk_publications_campaign", "campaigns", ["campaign_id"], ["id"], ondelete="SET NULL")
            batch.create_index("ix_publications_campaign_id", ["campaign_id"])
    # A vaga de "publicação ativa" passa a incluir as pausadas (campanha pausada).
    op.drop_index("uq_active_publication_group", table_name="publications", if_exists=True)
    op.create_index("uq_active_publication_group", "publications", ["product_id", "group_name"], unique=True,
                    postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))

def downgrade():
    with op.batch_alter_table("publications") as batch:
        batch.drop_index("ix_publications_campaign_id")
        batch.drop_constraint("fk_publications_campaign", type_="foreignkey")
        batch.drop_column("campaign_id")
    op.drop_table("campaigns")
