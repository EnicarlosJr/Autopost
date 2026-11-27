from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

class AutomationRule(Base):
    __tablename__ = "automation_rules"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), default="Regra principal")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    process_on_create: Mapped[bool] = mapped_column(Boolean, default=True)
    generate_publication: Mapped[bool] = mapped_column(Boolean, default=False)
    require_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    whatsapp_group_name: Mapped[str] = mapped_column(String(160), default="")
    categories: Mapped[str] = mapped_column(Text, default="[]")
    marketplaces: Mapped[str] = mapped_column(Text, default="[]")
    # Modelo da mensagem de oferta; vazio usa o modelo padrão (publications/messages.py).
    message_template: Mapped[str] = mapped_column(Text, default="", server_default="")
    # Forma de envio padrão das ofertas avulsas (fora de campanha) e a marca d'água da foto.
    send_mode: Mapped[str] = mapped_column(String(10), default="preview", server_default="preview")
    watermark_text: Mapped[str] = mapped_column(String(80), default="", server_default="")
    watermark_handle: Mapped[str] = mapped_column(String(60), default="", server_default="")
    # Identificação de publicidade (o programa de afiliados pede que o afiliado se identifique): vai na foto e no texto.
    disclosure_text: Mapped[str] = mapped_column(String(40), default="#publi", server_default="#publi")
    show_discount: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")   # selo "-30% OFF" na foto
    # Listas escolares: quem diz que não tem conta no Mercado Pago recebe um convite com este WhatsApp e mensagem.
    mp_help_whatsapp: Mapped[str] = mapped_column(String(20), default="", server_default="")
    mp_help_message: Mapped[str] = mapped_column(Text, default="", server_default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

class AutomationLog(Base):
    __tablename__ = "automation_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_id: Mapped[str] = mapped_column(String(80), index=True)
    task_type: Mapped[str] = mapped_column(String(80), index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="SET NULL"), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    detail: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
