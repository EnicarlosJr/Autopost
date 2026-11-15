"""Persist the configured WhatsApp group target."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision="0005_group_target"
down_revision="0004_users"
branch_labels=None
depends_on=None

def upgrade():
    bind=op.get_bind()
    automation={c["name"] for c in inspect(bind).get_columns("automation_rules")}
    if "whatsapp_group_name" not in automation: op.add_column("automation_rules",sa.Column("whatsapp_group_name",sa.String(160),nullable=False,server_default=""))
    publications={c["name"] for c in inspect(bind).get_columns("publications")}
    if "group_name" not in publications: op.add_column("publications",sa.Column("group_name",sa.String(160),nullable=False,server_default=""))

def downgrade():
    bind=op.get_bind()
    publications={c["name"] for c in inspect(bind).get_columns("publications")}
    if "group_name" in publications: op.drop_column("publications","group_name")
    automation={c["name"] for c in inspect(bind).get_columns("automation_rules")}
    if "whatsapp_group_name" in automation: op.drop_column("automation_rules","whatsapp_group_name")
