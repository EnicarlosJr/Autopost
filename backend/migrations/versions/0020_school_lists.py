"""Listas escolares: listas por série, itens e até 3 opções de produto por item."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0020_school_lists"
down_revision = "0019_publication_style"
branch_labels = None
depends_on = None

def _tables():
    return set(inspect(op.get_bind()).get_table_names())

def upgrade():
    tables = _tables()
    if "school_lists" not in tables:
        op.create_table("school_lists",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("school", sa.String(160), nullable=False, server_default=""),
            sa.Column("grade", sa.String(80), nullable=False, server_default=""),
            sa.Column("year", sa.Integer, nullable=False, server_default="2027"),
            sa.Column("notes", sa.Text, nullable=False, server_default=""),
            sa.Column("refresh_hours", sa.Integer, nullable=False, server_default="12"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if "school_list_items" not in tables:
        op.create_table("school_list_items",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("list_id", sa.Integer, sa.ForeignKey("school_lists.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("section", sa.String(20), nullable=False, server_default="coletivo"),
            sa.Column("name", sa.String(300), nullable=False),
            sa.Column("requested", sa.String(120), nullable=False, server_default=""),
            sa.Column("color", sa.String(160), nullable=False, server_default=""),
            sa.Column("position", sa.Integer, nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))
    if "school_list_options" not in tables:
        op.create_table("school_list_options",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("item_id", sa.Integer, sa.ForeignKey("school_list_items.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("slot", sa.Integer, nullable=False),
            sa.Column("label", sa.String(40), nullable=False, server_default=""),
            sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("buy_qty", sa.Integer, nullable=False, server_default="1"),
            sa.Column("watch", sa.Boolean, nullable=False, server_default=sa.true()),
            sa.Column("refresh_claimed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_error", sa.String(500), nullable=False, server_default=""),
            sa.UniqueConstraint("item_id", "slot", name="uq_school_option_slot"))

def downgrade():
    op.drop_table("school_list_options")
    op.drop_table("school_list_items")
    op.drop_table("school_lists")
