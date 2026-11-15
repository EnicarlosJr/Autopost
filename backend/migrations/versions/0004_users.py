"""Add administrator accounts."""
from alembic import op
from sqlalchemy import inspect
from app.models.user import User

revision="0004_users"
down_revision="0003_publication_schedule"
branch_labels=None
depends_on=None

def upgrade():
    if "users" not in inspect(op.get_bind()).get_table_names():
        User.__table__.create(bind=op.get_bind(),checkfirst=True)

def downgrade():
    if "users" in inspect(op.get_bind()).get_table_names():
        User.__table__.drop(bind=op.get_bind(),checkfirst=True)
