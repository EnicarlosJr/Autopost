"""Listas escolares: a lista de material de uma série, com até 3 opções de produto por item.

Cada opção aponta para um Product comum (mesmo cadastro, mesma leitura de preço pela extensão).
A página de orçamento para os pais é gerada a partir daqui.
"""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

def _now():
    return datetime.now(timezone.utc)

class SchoolList(Base):
    __tablename__ = "school_lists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    school: Mapped[str] = mapped_column(String(160), default="")
    grade: Mapped[str] = mapped_column(String(80), default="")          # série, ex.: "Maternal II"
    year: Mapped[int] = mapped_column(Integer, default=2027)
    notes: Mapped[str] = mapped_column(Text, default="")
    # De quantas em quantas horas a extensão reconfere o preço dos produtos desta lista.
    refresh_hours: Mapped[int] = mapped_column(Integer, default=12, server_default="12")
    # Página pública para os pais (em /escolas/<escola>/<série>), turmas da série (JSON) e contato do responsável pelos dados.
    public: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    turmas: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    contact: Mapped[str] = mapped_column(String(200), default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

class SchoolListItem(Base):
    __tablename__ = "school_list_items"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    list_id: Mapped[int] = mapped_column(ForeignKey("school_lists.id", ondelete="CASCADE"), index=True)
    section: Mapped[str] = mapped_column(String(20), default="coletivo")   # coletivo | individual
    name: Mapped[str] = mapped_column(String(300))
    requested: Mapped[str] = mapped_column(String(120), default="")      # como a escola pede: "500 folhas", "2 caixas"
    color: Mapped[str] = mapped_column(String(160), default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class SchoolListOption(Base):
    """Uma das (até) 3 opções de um item: o produto que você escolheu e quanto o pai precisa comprar."""
    __tablename__ = "school_list_options"
    __table_args__ = (UniqueConstraint("item_id", "slot", name="uq_school_option_slot"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int] = mapped_column(ForeignKey("school_list_items.id", ondelete="CASCADE"), index=True)
    slot: Mapped[int] = mapped_column(Integer)                            # 0, 1 ou 2
    label: Mapped[str] = mapped_column(String(40), default="")
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    buy_qty: Mapped[int] = mapped_column(Integer, default=1)
    # Reconferir o preço deste produto (o mesmo produto de catálogo) automaticamente.
    watch: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    # Reserva da conferência automática (evita duas abas lendo o mesmo produto) e último erro.
    refresh_claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str] = mapped_column(String(500), default="", server_default="")


class SchoolVisitor(Base):
    """Responsável que se identificou na página pública: nome do aluno e turma (com consentimento).

    O navegador guarda só o token (cookie); nada de telefone ou e-mail.
    """
    __tablename__ = "school_visitors"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    list_id: Mapped[int | None] = mapped_column(ForeignKey("school_lists.id", ondelete="SET NULL"), nullable=True, index=True)
    school: Mapped[str] = mapped_column(String(160), default="")
    student_name: Mapped[str] = mapped_column(String(120))
    turma: Mapped[str] = mapped_column(String(120), default="")
    token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    consent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    visits: Mapped[int] = mapped_column(Integer, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
