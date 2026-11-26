"""Buscas automáticas de ofertas: buscas salvas, anúncios encontrados, histórico de preço e agenda por grupo."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

def _now():
    return datetime.now(timezone.utc)

class Search(Base):
    """Uma busca salva: termos, filtros, frequência, grupo de destino e modo (aprovação ou automático)."""
    __tablename__ = "searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    terms: Mapped[str] = mapped_column(Text, default="")            # um termo por linha
    exclude_terms: Mapped[str] = mapped_column(Text, default="")    # palavras que descartam o anúncio
    min_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    max_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    min_discount: Mapped[int] = mapped_column(Integer, default=0)
    min_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    free_shipping_only: Mapped[bool] = mapped_column(Boolean, default=False)
    group_name: Mapped[str] = mapped_column(String(160), default="")
    mode: Mapped[str] = mapped_column(String(20), default="approval")  # "approval" ou "auto"
    interval_minutes: Mapped[int] = mapped_column(Integer, default=120)
    max_per_run: Mapped[int] = mapped_column(Integer, default=5)       # no modo automático
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    last_result: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

# Estados do anúncio encontrado:
#   new        apareceu numa busca e espera decisão (aprovar ou descartar)
#   scheduled  virou publicação (agendada, na fila ou já enviada)
#   discarded  descartado por você; não volta a aparecer
class Listing(Base):
    __tablename__ = "listings"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    external_id: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    search_id: Mapped[int | None] = mapped_column(ForeignKey("searches.id", ondelete="SET NULL"), nullable=True, index=True)
    term: Mapped[str] = mapped_column(String(160), default="")
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str] = mapped_column(String(500), default="")
    image_url: Mapped[str] = mapped_column(String(2048), default="")
    seller: Mapped[str] = mapped_column(String(160), default="")
    price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    original_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    price_note: Mapped[str] = mapped_column(String(60), default="")
    # Preço para quem não usa Pix nem saldo do Mercado Pago, quando o destaque depende do pagamento.
    regular_price: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    discount_pct: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    sold: Mapped[int | None] = mapped_column(Integer, nullable=True)
    free_shipping: Mapped[bool] = mapped_column(Boolean, default=False)
    # Sinais de confiabilidade lidos na página de resultados.
    official_store: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    fulfillment: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")    # Full (estoque no Mercado Livre)
    # Categoria oficial identificada pelo preditor do Mercado Livre (o card da busca não traz a categoria).
    ml_category_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    category_source: Mapped[str] = mapped_column(String(20), default="")
    # Produto de catálogo do Mercado Livre (/p/MLB...): anúncios de lojas diferentes do mesmo produto.
    catalog_product_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    min_price_30d: Mapped[float | None] = mapped_column(Numeric(12, 2, asdecimal=False), nullable=True)
    score: Mapped[int] = mapped_column(Integer, default=0, index=True)
    matches: Mapped[bool] = mapped_column(Boolean, default=False)   # passou nos filtros da busca
    reject_reason: Mapped[str] = mapped_column(String(200), default="")
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True)
    publication_id: Mapped[int | None] = mapped_column(ForeignKey("publications.id", ondelete="SET NULL"), nullable=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class PricePoint(Base):
    __tablename__ = "price_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2, asdecimal=False))
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

class GroupSchedule(Base):
    """Janela de postagem de um grupo: horário, limite por dia, intervalo e prazo para repostar."""
    __tablename__ = "group_schedules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    group_name: Mapped[str] = mapped_column(String(160), unique=True)
    start_hour: Mapped[int] = mapped_column(Integer, default=8)
    end_hour: Mapped[int] = mapped_column(Integer, default=22)
    max_per_day: Mapped[int] = mapped_column(Integer, default=12)
    gap_minutes: Mapped[int] = mapped_column(Integer, default=40)
    repost_days: Mapped[int] = mapped_column(Integer, default=7)
    # Cadastro do grupo: categorias e tags de interesse (para a distribuição por categoria) e se está ativo.
    categories: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Categorias oficiais do Mercado Livre que o grupo recebe: [{"id", "include_children", "name", "path"}]
    ml_categories: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
