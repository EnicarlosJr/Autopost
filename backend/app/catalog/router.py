"""API do catálogo oficial do Mercado Livre, das categorias favoritas e dos nichos do perfil."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.core.deps import require_user
from app.database.session import get_db
from app.models.catalog import FavoriteCategory, MlCategory, Niche, NicheCategory
from app.models.user import User
from app.catalog import service
from app.campaigns.service import clean_list, jload

router = APIRouter(prefix="/api/ml-categories", tags=["catalog"])
niches_router = APIRouter(prefix="/api/niches", tags=["catalog"])


def _cat(c: MlCategory, favorites: set[str]) -> dict:
    return {"id": c.id, "name": c.name, "parent_id": c.parent_id, "path": c.path_names, "path_ids": c.path_ids.split("/") if c.path_ids else [],
            "depth": c.depth, "is_leaf": c.is_leaf, "children_count": c.children_count, "total_items": c.total_items,
            "active": c.active, "favorite": c.id in favorites}


def _favorites(db: Session, user: User) -> set[str]:
    return set(db.scalars(select(FavoriteCategory.category_id).where(FavoriteCategory.owner_id == user.id)))


# ---------------------------------------------------------------- catálogo

class SlimCategory(BaseModel):
    id: str = Field(max_length=20)
    name: str = Field(max_length=200)
    parent_id: str | None = Field(default=None, max_length=20)
    total_items: int = 0
    children: int = 0

class ImportPayload(BaseModel):
    categories: list[SlimCategory] = Field(max_length=60000)


@router.get("/status")
def status(db: Session = Depends(get_db)):
    total = db.scalar(select(func.count()).select_from(MlCategory).where(MlCategory.active.is_(True))) or 0
    roots = db.scalar(select(func.count()).select_from(MlCategory).where(MlCategory.active.is_(True), MlCategory.parent_id.is_(None))) or 0
    synced = db.scalar(select(func.max(MlCategory.synced_at)))
    return {"total": total, "roots": roots, "synced_at": synced}


@router.post("/sync")
def sync_server(db: Session = Depends(get_db)):
    """Tenta atualizar pelo servidor. Se o Mercado Livre bloquear, o painel usa a extensão."""
    try:
        result = service.sync_from_api(db)
    except service.CatalogError as exc:
        db.commit()   # grava o registro da falha
        raise HTTPException(502, {"code": "use_browser", "message": str(exc)})
    db.commit()
    return result


@router.post("/import")
def import_categories(data: ImportPayload, db: Session = Depends(get_db)):
    """Recebe a árvore baixada pela extensão no navegador."""
    try:
        result = service.import_tree(db, [c.model_dump() for c in data.categories], "extensao")
    except service.CatalogError as exc:
        raise HTTPException(422, str(exc))
    db.commit()
    return result


@router.get("/children")
def children(parent: str = "root", db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = select(MlCategory).where(MlCategory.active.is_(True))
    stmt = stmt.where(MlCategory.parent_id.is_(None)) if parent == "root" else stmt.where(MlCategory.parent_id == parent)
    favorites = _favorites(db, user)
    return [_cat(c, favorites) for c in db.scalars(stmt.order_by(MlCategory.name))]


@router.get("/search")
def search(q: str = Query(min_length=2, max_length=80), limit: int = 60, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Busca pelo nome (sem acento e sem diferença de maiúsculas) ou pelo ID oficial."""
    term = service.plain(q)
    stmt = select(MlCategory).where(MlCategory.active.is_(True))
    if term.upper().startswith("MLB") and term[3:].isdigit():
        stmt = stmt.where(MlCategory.id == term.upper())
    else:
        stmt = stmt.where(MlCategory.search_name.like(f"%{term}%"))
    rows = list(db.scalars(stmt.order_by(MlCategory.depth, MlCategory.name).limit(max(1, min(limit, 200)))))
    favorites = _favorites(db, user)
    return [_cat(c, favorites) for c in rows]


@router.get("/favorites")
def list_favorites(db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = db.scalars(select(MlCategory).join(FavoriteCategory, FavoriteCategory.category_id == MlCategory.id)
                      .where(FavoriteCategory.owner_id == user.id).order_by(MlCategory.path_names))
    return [_cat(c, {c.id}) for c in rows]


@router.put("/favorites/{category_id}", status_code=204)
def add_favorite(category_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if db.get(MlCategory, category_id) is None:
        raise HTTPException(404, "Categoria não encontrada no catálogo")
    if db.get(FavoriteCategory, (user.id, category_id)) is None:
        db.add(FavoriteCategory(owner_id=user.id, category_id=category_id)); db.commit()
    return Response(status_code=204)


@router.delete("/favorites/{category_id}", status_code=204)
def remove_favorite(category_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    fav = db.get(FavoriteCategory, (user.id, category_id))
    if fav:
        db.delete(fav); db.commit()
    return Response(status_code=204)


@router.get("/lookup")
def lookup(ids: str = Query(max_length=4000), db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Detalhes de várias categorias (para mostrar chips com o caminho completo)."""
    wanted = [i for i in ids.split(",") if i][:200]
    favorites = _favorites(db, user)
    return [_cat(c, favorites) for c in db.scalars(select(MlCategory).where(MlCategory.id.in_(wanted)))]


@router.get("/{category_id}")
def detail(category_id: str, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = db.get(MlCategory, category_id)
    if c is None:
        raise HTTPException(404, "Categoria não encontrada no catálogo")
    return _cat(c, _favorites(db, user))


# ---------------------------------------------------------------- nichos

class NicheCategoryIn(BaseModel):
    id: str = Field(max_length=20)
    include_children: bool = True

class NicheWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field(default="", max_length=1000)
    favorite: bool = False
    categories: list[NicheCategoryIn] = Field(default_factory=list, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=50)
    include_keywords: list[str] = Field(default_factory=list, max_length=50)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    gender: str = Field(default="any", pattern="^(any|male|female)$")


def _niche(db: Session, user: User, niche_id: int) -> Niche:
    niche = db.get(Niche, niche_id)
    # Nichos de outro perfil respondem como inexistentes (não revela que existem).
    if niche is None or niche.owner_id != user.id:
        raise HTTPException(404, "Nicho não encontrado")
    return niche


def _niche_read(db: Session, n: Niche) -> dict:
    links = list(db.scalars(select(NicheCategory).where(NicheCategory.niche_id == n.id)))
    cats = {c.id: c for c in db.scalars(select(MlCategory).where(MlCategory.id.in_([l.category_id for l in links])))}
    return {"id": n.id, "name": n.name, "description": n.description, "favorite": n.favorite,
            "tags": jload(n.tags), "include_keywords": jload(n.include_keywords), "exclude_keywords": jload(n.exclude_keywords),
            "gender": n.gender or "any",
            "categories": [{"id": l.category_id, "include_children": l.include_children,
                            "name": cats[l.category_id].name if l.category_id in cats else l.category_id,
                            "path": cats[l.category_id].path_names if l.category_id in cats else "",
                            "is_leaf": cats[l.category_id].is_leaf if l.category_id in cats else True,
                            "active": cats[l.category_id].active if l.category_id in cats else False} for l in links],
            "created_at": n.created_at, "updated_at": n.updated_at}


def _apply(db: Session, n: Niche, data: NicheWrite) -> None:
    ids = [c.id for c in data.categories]
    known = set(db.scalars(select(MlCategory.id).where(MlCategory.id.in_(ids)))) if ids else set()
    missing = [i for i in ids if i not in known]
    if missing:
        raise HTTPException(422, f"Categoria(s) fora do catálogo oficial: {', '.join(missing[:5])}. Atualize as categorias.")
    n.name = data.name.strip()
    n.description = data.description.strip()
    n.favorite = data.favorite
    n.tags = json.dumps(clean_list(data.tags), ensure_ascii=False)
    n.include_keywords = json.dumps(clean_list(data.include_keywords), ensure_ascii=False)
    n.exclude_keywords = json.dumps(clean_list(data.exclude_keywords), ensure_ascii=False)
    n.gender = data.gender
    n.updated_at = datetime.now().astimezone()
    db.flush()
    db.query(NicheCategory).filter(NicheCategory.niche_id == n.id).delete()
    seen = set()
    for c in data.categories:
        if c.id not in seen:
            seen.add(c.id); db.add(NicheCategory(niche_id=n.id, category_id=c.id, include_children=c.include_children))


def _save(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Você já tem um nicho com esse nome")


@niches_router.get("")
def list_niches(db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = db.scalars(select(Niche).where(Niche.owner_id == user.id).order_by(Niche.favorite.desc(), Niche.name))
    return [_niche_read(db, n) for n in rows]


@niches_router.post("", status_code=201)
def create_niche(data: NicheWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    if db.scalar(select(Niche.id).where(Niche.owner_id == user.id, Niche.name == data.name.strip())):
        raise HTTPException(409, "Você já tem um nicho com esse nome")
    n = Niche(owner_id=user.id, name=data.name.strip())
    db.add(n); db.flush()
    _apply(db, n, data); _save(db); db.refresh(n)
    return _niche_read(db, n)


@niches_router.get("/{niche_id}")
def get_niche(niche_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _niche_read(db, _niche(db, user, niche_id))


@niches_router.put("/{niche_id}")
def update_niche(niche_id: int, data: NicheWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    n = _niche(db, user, niche_id)
    if db.scalar(select(Niche.id).where(Niche.owner_id == user.id, Niche.name == data.name.strip(), Niche.id != n.id)):
        raise HTTPException(409, "Você já tem um nicho com esse nome")
    _apply(db, n, data); _save(db); db.refresh(n)
    return _niche_read(db, n)


@niches_router.post("/{niche_id}/favorite")
def toggle_favorite(niche_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    n = _niche(db, user, niche_id)
    n.favorite = not n.favorite
    db.commit(); db.refresh(n)
    return _niche_read(db, n)


@niches_router.post("/{niche_id}/duplicate", status_code=201)
def duplicate_niche(niche_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    src = _niche(db, user, niche_id)
    names = set(db.scalars(select(Niche.name).where(Niche.owner_id == user.id)))
    name, n = f"{src.name} (cópia)"[:120], 2
    while name in names:
        name, n = f"{src.name} (cópia {n})"[:120], n + 1
    copy = Niche(owner_id=user.id, name=name, description=src.description, favorite=False, tags=src.tags,
                 include_keywords=src.include_keywords, exclude_keywords=src.exclude_keywords, gender=src.gender)
    db.add(copy); db.flush()
    for link in db.scalars(select(NicheCategory).where(NicheCategory.niche_id == src.id)):
        db.add(NicheCategory(niche_id=copy.id, category_id=link.category_id, include_children=link.include_children))
    _save(db); db.refresh(copy)
    return _niche_read(db, copy)


@niches_router.delete("/{niche_id}", status_code=204)
def delete_niche(niche_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    n = _niche(db, user, niche_id)
    db.delete(n); db.commit()
    return Response(status_code=204)
