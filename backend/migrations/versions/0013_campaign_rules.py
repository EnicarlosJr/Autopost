"""Regras de automação das campanhas, categorias oficiais dos grupos e conjuntos de grupos."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0013_campaign_rules"
down_revision = "0012_campaign_search"
branch_labels = None
depends_on = None

def _columns(bind, table):
    return {c["name"] for c in inspect(bind).get_columns(table)}

def upgrade():
    bind = op.get_bind()
    cols = _columns(bind, "campaigns")
    with op.batch_alter_table("campaigns") as batch:
        if "end_at" not in cols:
            batch.add_column(sa.Column("end_at", sa.DateTime(timezone=True), nullable=True))
        if "message_gap_seconds" not in cols:
            batch.add_column(sa.Column("message_gap_seconds", sa.Integer, nullable=False, server_default="20"))
        if "reuse_days" not in cols:
            batch.add_column(sa.Column("reuse_days", sa.Integer, nullable=True))
        if "group_daily_limit" not in cols:
            batch.add_column(sa.Column("group_daily_limit", sa.Integer, nullable=False, server_default="0"))
    if "ml_categories" not in _columns(bind, "group_schedules"):
        with op.batch_alter_table("group_schedules") as batch:
            batch.add_column(sa.Column("ml_categories", sa.Text, nullable=False, server_default="[]"))
    if "group_sets" not in set(inspect(bind).get_table_names()):
        op.create_table(
            "group_sets",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("name", sa.String(80), nullable=False),
            sa.Column("groups", sa.Text, nullable=False, server_default="[]"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.UniqueConstraint("owner_id", "name", name="uq_group_sets_owner_name"),
        )

def downgrade():
    op.drop_table("group_sets")
    with op.batch_alter_table("group_schedules") as batch:
        batch.drop_column("ml_categories")
    with op.batch_alter_table("campaigns") as batch:
        for name in ("group_daily_limit", "reuse_days", "message_gap_seconds", "end_at"):
            batch.drop_column(name)
