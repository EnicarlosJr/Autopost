"""Add fields for store and stock availability."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0002_product_meta"
down_revision = "0001_initial"
branch_labels = None
depends_on = None

def upgrade():
    names={column["name"] for column in inspect(op.get_bind()).get_columns("products")}
    if "store" not in names: op.add_column("products",sa.Column("store",sa.String(160),nullable=False,server_default=""))
    if "availability" not in names: op.add_column("products",sa.Column("availability",sa.String(80),nullable=False,server_default=""))

def downgrade():
    names={column["name"] for column in inspect(op.get_bind()).get_columns("products")}
    if "availability" in names: op.drop_column("products","availability")
    if "store" in names: op.drop_column("products","store")
