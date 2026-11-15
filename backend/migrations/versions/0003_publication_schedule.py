"""Add scheduled publication time and active-publication uniqueness."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0003_publication_schedule"
down_revision = "0002_product_meta"
branch_labels = None
depends_on = None

def upgrade():
    bind=op.get_bind()
    columns={column["name"] for column in inspect(bind).get_columns("publications")}
    if "scheduled_at" not in columns:
        op.add_column("publications",sa.Column("scheduled_at",sa.DateTime(timezone=True),nullable=True))
    indexes={index["name"] for index in inspect(bind).get_indexes("publications")}
    # Em bancos novos a tabela já nasce sem "destination" (removida na 0008): nada a criar aqui.
    if "uq_active_manual_publication" not in indexes and "destination" in columns:
        op.create_index("uq_active_manual_publication","publications",["product_id","destination"],unique=True,postgresql_where=sa.text("status IN ('pending','awaiting_approval','approved','scheduled','sending','sent')"),sqlite_where=sa.text("status IN ('pending','awaiting_approval','approved','scheduled','sending','sent')"))

def downgrade():
    bind=op.get_bind()
    indexes={index["name"] for index in inspect(bind).get_indexes("publications")}
    if "uq_active_manual_publication" in indexes: op.drop_index("uq_active_manual_publication",table_name="publications")
    columns={column["name"] for column in inspect(bind).get_columns("publications")}
    if "scheduled_at" in columns: op.drop_column("publications","scheduled_at")
