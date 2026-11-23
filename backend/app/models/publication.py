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
    # Forma de envio escolhida só para esta publicação (vazio = da campanha ou das Configurações).
    send_mode_choice: Mapped[str | None] = mapped_column(String(10), nullable=True)
    product: Mapped[Product] = relationship(lazy="selectin")

    def style(self) -> dict:
        """Como esta publicação sai.

        Forma de envio: a escolhida na publicação, senão a da campanha, senão a do perfil (ofertas avulsas).
        Marca d'água: a da campanha quando ela personaliza, senão a do perfil.
        Identificação de publicidade e selo de desconto: sempre os do perfil (a campanha não tira o #publi)."""
        from sqlalchemy import select
        from sqlalchemy.orm import object_session
        from app.models.automation import AutomationRule
        from app.models.campaign import Campaign
        from app.publications.messages import clean_disclosure
        session = object_session(self)
        campaign = session.get(Campaign, self.campaign_id) if session and self.campaign_id else None
        rule = session.scalar(select(AutomationRule).order_by(AutomationRule.id).limit(1)) if session else None
        marks = campaign if campaign is not None and campaign.custom_style else rule
        mode = self.send_mode_choice or ((campaign.send_mode if campaign is not None else getattr(rule, "send_mode", "")) or "preview")
        show = getattr(rule, "show_discount", True)
        return {"mode": mode, "title": (getattr(marks, "watermark_text", "") or "") if marks is not None else "",
                "handle": (getattr(marks, "watermark_handle", "") or "") if marks is not None else "",
                "disclosure": clean_disclosure(getattr(rule, "disclosure_text", "") if rule is not None else ""),
                "show_discount": True if show is None else bool(show)}

    def delivery(self) -> tuple[str, str, str]:
        """(forma de envio, nome do grupo na marca d'água, Instagram)."""
        s = self.style()
        return s["mode"], s["title"], s["handle"]

    @property
    def outgoing_message(self) -> str:
        """O texto exatamente como vai para o grupo: com a identificação de publicidade no topo."""
        from app.publications.messages import normalize_offer_text, with_disclosure
        return with_disclosure(normalize_offer_text(self.message or ""), self.style()["disclosure"])

    @property
    def send_mode(self) -> str:
        return self.delivery()[0]
