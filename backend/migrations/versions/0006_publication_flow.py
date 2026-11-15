"""Fluxo de envio confiável: estados sending/failed, aprovação registrada,
unicidade por grupo, preços em NUMERIC e controle de processamento travado."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0006_publication_flow"
down_revision = "0005_group_target"
branch_labels = None
depends_on = None

ACTIVE = "status IN ('pending','awaiting_approval','approved','scheduled','sending')"

def _columns(bind, table):
    return {c["name"]: c for c in inspect(bind).get_columns(table)}

def _indexes(bind, table):
    return {i["name"] for i in inspect(bind).get_indexes(table)}

def upgrade():
    bind = op.get_bind()
    pub = _columns(bind, "publications")
    if "approved_at" not in pub: op.add_column("publications", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    if "send_attempts" not in pub: op.add_column("publications", sa.Column("send_attempts", sa.Integer(), nullable=False, server_default="0"))
    if "last_error" not in pub: op.add_column("publications", sa.Column("last_error", sa.Text(), nullable=False, server_default=""))
    if "updated_at" not in pub: op.add_column("publications", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
    prod = _columns(bind, "products")
    if "processing_started_at" not in prod: op.add_column("products", sa.Column("processing_started_at", sa.DateTime(timezone=True), nullable=True))
    if "updated_at" not in prod: op.add_column("products", sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))

    # Estados antigos: "pending" passa a ser "awaiting_approval"; aprovadas ganham data de aprovação.
    op.execute("UPDATE publications SET status='awaiting_approval' WHERE status='pending'")
    op.execute("UPDATE publications SET approved_at=created_at WHERE status IN ('approved','sent') AND approved_at IS NULL")
    op.execute("UPDATE publications SET updated_at=created_at WHERE updated_at IS NULL")
    op.execute("UPDATE products SET updated_at=created_at WHERE updated_at IS NULL")

    # Unicidade passa a ser por produto + grupo, e "sent" não bloqueia mais um repost.
    indexes = _indexes(bind, "publications")
    if "uq_active_manual_publication" in indexes:
        op.drop_index("uq_active_manual_publication", table_name="publications")
    if "uq_active_publication_group" not in indexes:
        op.create_index("uq_active_publication_group", "publications", ["product_id", "group_name"], unique=True,
                        postgresql_where=sa.text(ACTIVE), sqlite_where=sa.text(ACTIVE))

    if bind.dialect.name == "postgresql":
        for column in ("price", "original_price"):
            if not isinstance(prod[column]["type"], sa.Numeric) or isinstance(prod[column]["type"], sa.Float):
                op.execute(f"ALTER TABLE products ALTER COLUMN {column} TYPE NUMERIC(12,2) USING round({column}::numeric, 2)")

def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for column in ("price", "original_price"):
            op.execute(f"ALTER TABLE products ALTER COLUMN {column} TYPE DOUBLE PRECISION USING {column}::double precision")
    indexes = _indexes(bind, "publications")
    if "uq_active_publication_group" in indexes:
        op.drop_index("uq_active_publication_group", table_name="publications")
    op.execute("UPDATE publications SET status='pending' WHERE status='awaiting_approval'")
    op.execute("UPDATE publications SET status='approved' WHERE status IN ('failed','sending')")
    for table, cols in (("publications", ("approved_at", "send_attempts", "last_error", "updated_at")),
                        ("products", ("processing_started_at", "updated_at"))):
        existing = _columns(bind, table)
        for col in cols:
            if col in existing:
                op.drop_column(table, col)
