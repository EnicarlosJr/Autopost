"""Público do nicho (masculino, feminino ou todos)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0014_niche_gender"
down_revision = "0013_campaign_rules"
branch_labels = None
depends_on = None

def upgrade():
    if "gender" not in {c["name"] for c in inspect(op.get_bind()).get_columns("niches")}:
        with op.batch_alter_table("niches") as batch:
            batch.add_column(sa.Column("gender", sa.String(10), nullable=False, server_default="any"))

def downgrade():
    with op.batch_alter_table("niches") as batch:
        batch.drop_column("gender")
