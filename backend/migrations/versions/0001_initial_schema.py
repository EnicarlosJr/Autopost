"""Create application schema (safe baseline for existing create_all deployments)."""
from alembic import op
from app.database.session import Base
from app.models.product import Product
from app.models.publication import Publication
from app.models.automation import AutomationLog, AutomationRule

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    Base.metadata.create_all(bind=op.get_bind(), checkfirst=True)

def downgrade():
    Base.metadata.drop_all(bind=op.get_bind(), checkfirst=True)
