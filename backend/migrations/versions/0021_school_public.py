"""Página pública das listas escolares e identificação dos responsáveis (nome do aluno e turma)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0021_school_public"
down_revision = "0020_school_lists"
branch_labels = None
depends_on = None

def upgrade():
    insp = inspect(op.get_bind())
    cols = {c["name"] for c in insp.get_columns("school_lists")}
    with op.batch_alter_table("school_lists") as batch:
        if "public" not in cols:
            batch.add_column(sa.Column("public", sa.Boolean, nullable=False, server_default=sa.false()))
        if "turmas" not in cols:
            batch.add_column(sa.Column("turmas", sa.Text, nullable=False, server_default="[]"))
        if "contact" not in cols:
            batch.add_column(sa.Column("contact", sa.String(200), nullable=False, server_default=""))
    if "school_visitors" not in set(insp.get_table_names()):
        op.create_table("school_visitors",
            sa.Column("id", sa.Integer, primary_key=True),
            sa.Column("owner_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True),
            sa.Column("list_id", sa.Integer, sa.ForeignKey("school_lists.id", ondelete="SET NULL"), nullable=True, index=True),
            sa.Column("school", sa.String(160), nullable=False, server_default=""),
            sa.Column("student_name", sa.String(120), nullable=False),
            sa.Column("turma", sa.String(120), nullable=False, server_default=""),
            sa.Column("token", sa.String(64), nullable=False, unique=True, index=True),
            sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("visits", sa.Integer, nullable=False, server_default="1"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()))

def downgrade():
    op.drop_table("school_visitors")
    with op.batch_alter_table("school_lists") as batch:
        batch.drop_column("contact")
        batch.drop_column("turmas")
        batch.drop_column("public")
