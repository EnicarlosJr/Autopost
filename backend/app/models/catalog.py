"""Catálogo oficial de categorias do Mercado Livre (global) e preferências do perfil: favoritas e nichos."""
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from app.database.session import Base

def _now():
    return datetime.now(timezone.utc)

class MlCategory(Base):
    """Uma categoria oficial (ex.: MLB1672, HDs e SSDs). Compartilhada por todos os perfis; nunca duplicada."""
    __tablename__ = "ml_categories"
    id: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    search_name: Mapped[str] = mapped_column(String(200), index=True)      # minúsculas e sem acento, para a busca
    parent_id: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    path_ids: Mapped[str] = mapped_column(Text, default="")                # "MLB1648/MLB430598/..."
    path_names: Mapped[str] = mapped_column(Text, default="")              # "Informática > Armazenamento > ..."
    depth: Mapped[int] = mapped_column(Integer, default=0)
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=True)
    children_count: Mapped[int] = mapped_column(Integer, default=0)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)            # some da API = inativa (nada é apagado)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class FavoriteCategory(Base):
    __tablename__ = "favorite_categories"
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("ml_categories.id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

class Niche(Base):
    """Conjunto reutilizável do perfil: categorias oficiais, tags pessoais e palavras-chave."""
    __tablename__ = "niches"
    __table_args__ = (UniqueConstraint("owner_id", "name", name="uq_niche_owner_name"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    tags: Mapped[str] = mapped_column(Text, default="[]")                  # tags pessoais (não são categorias)
    include_keywords: Mapped[str] = mapped_column(Text, default="[]")
    exclude_keywords: Mapped[str] = mapped_column(Text, default="[]")
    gender: Mapped[str] = mapped_column(String(10), default="any", server_default="any")   # any | male | female
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

class NicheCategory(Base):
    __tablename__ = "niche_categories"
    niche_id: Mapped[int] = mapped_column(ForeignKey("niches.id", ondelete="CASCADE"), primary_key=True)
    category_id: Mapped[str] = mapped_column(ForeignKey("ml_categories.id", ondelete="CASCADE"), primary_key=True)
    include_children: Mapped[bool] = mapped_column(Boolean, default=True)
