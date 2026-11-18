"""Campanhas de divulgação: segmentação dos produtos, grupos de destino, distribuição e ritmo dos envios."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

def _now():
    return datetime.now(timezone.utc)

# Estados guardados: draft (rascunho), scheduled (confirmada), paused, cancelled.
# "Em execução", "Concluída" e "Com falhas" são calculados a partir das publicações da campanha.
class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    # Segmentação (listas em JSON). Produtos escolhidos à mão têm prioridade sobre os filtros.
    product_ids: Mapped[str] = mapped_column(Text, default="[]")
    categories: Mapped[str] = mapped_column(Text, default="[]")
    exclude_categories: Mapped[str] = mapped_column(Text, default="[]")
    tags: Mapped[str] = mapped_column(Text, default="[]")
    tag_mode: Mapped[str] = mapped_column(String(10), default="any")   # any | all
    exclude_tags: Mapped[str] = mapped_column(Text, default="[]")
    include_uncategorized: Mapped[bool] = mapped_column(Boolean, default=False)
    min_discount: Mapped[int] = mapped_column(Integer, default=0)
    # Destino e distribuição: [{"group": "...", "limit": 5, "categories": ["..."]}]
    groups: Mapped[str] = mapped_column(Text, default="[]")
    strategy: Mapped[str] = mapped_column(String(20), default="balanced")  # sequential | balanced | category | custom
    total_limit: Mapped[int] = mapped_column(Integer, default=20)
    # Ritmo
    block_size: Mapped[int] = mapped_column(Integer, default=1)            # anúncios por execução
    interval_minutes: Mapped[int] = mapped_column(Integer, default=5)      # intervalo mínimo entre execuções
    interval_max_minutes: Mapped[int] = mapped_column(Integer, default=0)  # 0 = intervalo fixo
    start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    start_hour: Mapped[int] = mapped_column(Integer, default=8)
    end_hour: Mapped[int] = mapped_column(Integer, default=22)
    weekdays: Mapped[str] = mapped_column(String(40), default="[0,1,2,3,4,5,6]")  # 0 = segunda
    daily_limit: Mapped[int] = mapped_column(Integer, default=0)           # 0 = sem limite
    pause_every: Mapped[int] = mapped_column(Integer, default=0)           # pausa a cada N anúncios (0 = sem pausa)
    pause_minutes: Mapped[int] = mapped_column(Integer, default=0)
    # Regras da Fase C: término, intervalo entre mensagens da mesma execução, reutilização e limite diário por grupo.
    end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message_gap_seconds: Mapped[int] = mapped_column(Integer, default=20, server_default="20")
    reuse_days: Mapped[int | None] = mapped_column(Integer, nullable=True)        # None = prazo de repostagem do grupo
    group_daily_limit: Mapped[int] = mapped_column(Integer, default=0, server_default="0")   # 0 = sem limite
    # Forma de envio: "preview" (só texto, o WhatsApp monta a prévia do link) ou "image" (foto padronizada + legenda).
    send_mode: Mapped[str] = mapped_column(String(10), default="preview", server_default="preview")
    watermark_text: Mapped[str] = mapped_column(String(80), default="", server_default="")     # ex.: nome do grupo
    watermark_handle: Mapped[str] = mapped_column(String(60), default="", server_default="")   # ex.: @instagram
    # Dono (perfil) e segmentação oficial. Os nichos aplicados são copiados: mudar a campanha não muda o nicho.
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    niche_ids: Mapped[str] = mapped_column(Text, default="[]")
    ml_categories: Mapped[str] = mapped_column(Text, default="[]")      # [{"id", "include_children", "name", "path"}]
    include_keywords: Mapped[str] = mapped_column(Text, default="[]")
    exclude_keywords: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=True)


# Estados da busca: queued (na fila da extensão), running, done, no_results, failed.
class CampaignSearch(Base):
    """Uma busca de produtos feita dentro de uma campanha (histórico com parâmetros e resultados)."""
    __tablename__ = "campaign_searches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), index=True)
    niche_id: Mapped[int | None] = mapped_column(ForeignKey("niches.id", ondelete="SET NULL"), nullable=True)
    niche_name: Mapped[str] = mapped_column(String(120), default="")
    categories: Mapped[str] = mapped_column(Text, default="[]")
    keywords: Mapped[str] = mapped_column(Text, default="[]")
    exclude_keywords: Mapped[str] = mapped_column(Text, default="[]")
    filters: Mapped[str] = mapped_column(Text, default="{}")
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    result_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, default=0)
    added_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class CampaignSearchResult(Base):
    __tablename__ = "campaign_search_results"
    search_id: Mapped[int] = mapped_column(ForeignKey("campaign_searches.id", ondelete="CASCADE"), primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), primary_key=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    reason: Mapped[str] = mapped_column(String(200), default="")

class CampaignProduct(Base):
    """Produto escolhido para a campanha (pela busca da campanha ou pela tela Produtos)."""
    __tablename__ = "campaign_products"
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id", ondelete="CASCADE"), primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    search_id: Mapped[int | None] = mapped_column(ForeignKey("campaign_searches.id", ondelete="SET NULL"), nullable=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class GroupSet(Base):
    """Conjunto nomeado de grupos do WhatsApp (por perfil), aplicado de uma vez nas campanhas."""
    __tablename__ = "group_sets"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    groups: Mapped[str] = mapped_column(Text, default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
