from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database.session import Base
from app.models.product import Product

# Estados que ocupam a vaga de "publicação ativa" de um produto em um grupo.
# "sent" fica de fora para permitir repostar (controlado pela janela de repost).
# "paused" é uma publicação de campanha pausada: continua ocupando a vaga até ser retomada ou cancelada.
ACTIVE_STATUSES = ("pending", "awaiting_approval", "approved", "scheduled", "sending", "paused")
_ACTIVE_SQL = "status IN ('pending','awaiting_approval','approved','scheduled','sending','paused')"

def _now():
    return datetime.now(timezone.utc)

class Publication(Base):
    __tablename__ = "publications"
    __table_args__ = (
        Index("uq_active_publication_group", "product_id", "group_name", unique=True,
              postgresql_where=text(_ACTIVE_SQL), sqlite_where=text(_ACTIVE_SQL)),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    group_name: Mapped[str] = mapped_column(String(160), default="")
    message: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="awaiting_approval", index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    send_attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Campanha que gerou a publicação (vazio para publicações avulsas).
    campaign_id: Mapped[int | None] = mapped_column(ForeignKey("campaigns.id", ondelete="SET NULL"), nullable=True, index=True)
    product: Mapped[Product] = relationship(lazy="selectin")
