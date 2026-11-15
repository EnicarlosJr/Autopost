"""Origem e data dos preços, modelo de mensagem editável, link de produto único,
remoção da coluna destination (sem uso)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "0008_data_source_settings"
down_revision = "0007_price_note"
branch_labels = None
depends_on = None

def _columns(bind, table):
    return {c["name"] for c in inspect(bind).get_columns(table)}

def _indexes(bind, table):
    return {i["name"]: i for i in inspect(bind).get_indexes(table)}

def upgrade():
    bind = op.get_bind()
    products = _columns(bind, "products")
    if "data_source" not in products:
        op.add_column("products", sa.Column("data_source", sa.String(20), nullable=False, server_default=""))
    if "captured_at" not in products:
        op.add_column("products", sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True))
    rules = _columns(bind, "automation_rules")
    if "message_template" not in rules:
        op.add_column("automation_rules", sa.Column("message_template", sa.Text(), nullable=False, server_default=""))

    # Produtos antigos com preço: origem = servidor; data da leitura desconhecida (será conferida antes do envio).
    op.execute("UPDATE products SET data_source='server' WHERE data_source='' AND price IS NOT NULL")

    # Link do produto passa a ser único no banco. Duplicados antigos recebem um sufixo (nada é apagado).
    rows = bind.execute(sa.text("SELECT id, original_url FROM products ORDER BY id")).fetchall()
    seen = set()
    for product_id, url in rows:
        if url in seen:
            bind.execute(sa.text("UPDATE products SET original_url = :u WHERE id = :i"),
                         {"u": f"{url}#duplicado-{product_id}", "i": product_id})
        else:
            seen.add(url)
    indexes = _indexes(bind, "products")
    current = indexes.get("ix_products_original_url")
    if current is not None and not current.get("unique"):
        op.drop_index("ix_products_original_url", table_name="products")
        current = None
    if current is None:
        op.create_index("ix_products_original_url", "products", ["original_url"], unique=True)

    if "destination" in _columns(bind, "publications"):
        with op.batch_alter_table("publications") as batch:
            batch.drop_column("destination")

def downgrade():
    bind = op.get_bind()
    if "destination" not in _columns(bind, "publications"):
        op.add_column("publications", sa.Column("destination", sa.String(160), nullable=False, server_default="whatsapp"))
    if "ix_products_original_url" in _indexes(bind, "products"):
        op.drop_index("ix_products_original_url", table_name="products")
        op.create_index("ix_products_original_url", "products", ["original_url"], unique=False)
    for table, column in (("automation_rules", "message_template"), ("products", "captured_at"), ("products", "data_source")):
        if column in _columns(bind, table):
            with op.batch_alter_table(table) as batch:
                batch.drop_column(column)
