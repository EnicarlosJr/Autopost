from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

def _now():
    return datetime.now(timezone.utc)

# Estados do produto:
#   pending           cadastrado, sem extração automática
#   processing        o servidor está extraindo os dados
#   awaiting_browser  a loja bloqueia o servidor (Mercado Livre): falta a leitura pelo navegador
#   processed         dados prontos
#   needs_review      faltam dados; revisar à mão
#   error             a extração falhou

class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_url: Mapped[str] = mapped_column(String(2048), unique=True, index=True)
    affiliate_url: Mapped[str] = mapped_column(String(2048))
    marketplace: Mapped[str] = mapped_column(String(100), default="")
    category: Mapped[str] = mapped_column(String(100), default="")
    # Tags livres em JSON (lista de textos), usadas para segmentar campanhas. Ex.: ["academia", "promo"].
    tags: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    # Categoria oficial do Mercado Livre (ID, ex.: MLB1672). "category" acima é um rótulo antigo, sem uso no fluxo novo.
    ml_category_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    title: Mapped[str] = mapped_column(String(500), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    image_url: Mapped[str] = mapped_column(String(2048), default="")
    # Endereço original da foto na loja (usado para buscar a versão de maior qualidade no envio com foto).
    image_source_url: Mapped[str] = mapped_column(String(2048), default="", server_default="")
    # Numeric guarda centavos exatos no banco; asdecimal=False mantém float no Python.
    price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    original_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    # Condição do preço exibido, por exemplo "no Pix" (vazio quando vale para qualquer pagamento).
    price_note: Mapped[str] = mapped_column(String(60), default="", server_default="")
    # De onde vieram os preços: "server" (extração), "browser" (extensão) ou "manual" (edição).
    data_source: Mapped[str] = mapped_column(String(20), default="", server_default="")
    # Quando os preços foram lidos pela última vez (base para conferir antes do envio).
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Preço para qualquer pagamento (cartão), quando o preço em destaque depende de Pix ou Mercado Pago.
    regular_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    # Condições lidas junto do preço: "no Pix", "com Mercado Pago", "cupom" (separadas por " · ").
    price_conditions: Mapped[str] = mapped_column(String(300), default="", server_default="")
    store: Mapped[str] = mapped_column(String(160), default="")
    # "indisponível" quando a loja diz que acabou ou pausou (o último preço continua guardado).
    availability: Mapped[str] = mapped_column(String(80), default="")
    # Última conferência do link de afiliado: abre o produto? (None = ainda não conferido).
    affiliate_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    affiliate_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="pending", index=True)
    processing_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=True)
