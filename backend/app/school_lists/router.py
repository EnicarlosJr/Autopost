"""Listas escolares: cadastro da lista da série, escolha dos produtos de cada opção,
conferência automática de preço (pela extensão) e a página de orçamento para os pais."""
import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.deps import require_user
from app.database.session import get_db
from app.models.product import Product
from app.models.school import SchoolList, SchoolListItem, SchoolListOption, SchoolVisitor
from app.models.user import User
from app.products.service import add_note
from app.products.sources import BROWSER_NOTICE, marketplace_of, needs_browser
from app.products.urls import normalize_product_url
from app.publications.service import main_rule
from app.school_lists import service

router = APIRouter(prefix="/api/school-lists", tags=["school-lists"])


class ListWrite(BaseModel):
    school: str = Field(default="", max_length=160)
    grade: str = Field(min_length=1, max_length=80)
    year: int = Field(default=2027, ge=2020, le=2100)
    notes: str = Field(default="", max_length=5000)
    refresh_hours: int = Field(default=12, ge=1, le=168)
    public: bool = False
    turmas: list[str] = Field(default_factory=list, max_length=30)
    contact: str = Field(default="", max_length=200)

class ItemWrite(BaseModel):
    section: str = Field(default="coletivo", pattern="^(coletivo|individual)$")
    name: str = Field(min_length=1, max_length=300)
    requested: str = Field(default="", max_length=120)
    color: str = Field(default="", max_length=160)

class ItemPatch(BaseModel):
    section: str | None = Field(default=None, pattern="^(coletivo|individual)$")
    name: str | None = Field(default=None, min_length=1, max_length=300)
    requested: str | None = Field(default=None, max_length=120)
    color: str | None = Field(default=None, max_length=160)
    position: int | None = Field(default=None, ge=0, le=100000)

class ImportText(BaseModel):
    section: str = Field(default="coletivo", pattern="^(coletivo|individual)$")
    text: str = Field(min_length=1, max_length=20000)

class OptionWrite(BaseModel):
    """Cole o link do anúncio (de preferência a página de catálogo /p/MLB…) ou aponte um produto já cadastrado."""
    url: HttpUrl | None = None
    product_id: int | None = None
    label: str = Field(default="", max_length=40)
    buy_qty: int = Field(default=1, ge=1, le=999)
    watch: bool = True

class OptionPatch(BaseModel):
    label: str | None = Field(default=None, max_length=40)
    buy_qty: int | None = Field(default=None, ge=1, le=999)
    watch: bool | None = None

class RefreshDone(BaseModel):
    error: str = Field(default="", max_length=500)


def _list(db: Session, user: User, list_id: int) -> SchoolList:
    row = db.get(SchoolList, list_id)
    if row is None or row.owner_id != user.id:
        raise HTTPException(404, "Lista não encontrada")
    return row

def _item(db: Session, user: User, item_id: int) -> SchoolListItem:
    item = db.get(SchoolListItem, item_id)
    if item is None:
        raise HTTPException(404, "Item não encontrado")
    _list(db, user, item.list_id)
    return item

def _next_position(db: Session, list_id: int, section: str) -> int:
    last = db.scalar(select(func.max(SchoolListItem.position)).where(SchoolListItem.list_id == list_id, SchoolListItem.section == section))
    return (last or 0) + 1


@router.get("")
def list_lists(db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = db.scalars(select(SchoolList).where(SchoolList.owner_id == user.id).order_by(SchoolList.year.desc(), SchoolList.school, SchoolList.grade))
    out = []
    for row in rows:
        detail = service.list_detail(db, row)
        detail.pop("items")
        detail["item_count"] = sum(v["items"] for v in detail["totals"].values())
        out.append(detail)
    return out

@router.post("", status_code=201)
def create_list(data: ListWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    row = SchoolList(owner_id=user.id, school=data.school.strip(), grade=data.grade.strip(), year=data.year,
                     notes=data.notes, refresh_hours=data.refresh_hours, public=data.public,
                     turmas=service.clean_turmas(data.turmas), contact=data.contact.strip())
    db.add(row); db.commit(); db.refresh(row)
    return service.list_detail(db, row)

@router.get("/refresh/next")
def refresh_next(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Para a extensão: o próximo produto das listas com preço vencido (ou nada)."""
    product = service.next_refresh(db, user.id)
    if product is None:
        return {"product": None}
    return {"product": {"id": product.id, "url": product.original_url, "affiliate_url": product.affiliate_url}}

@router.post("/refresh/{product_id}/done")
def refresh_done(product_id: int, data: RefreshDone, db: Session = Depends(get_db), user: User = Depends(require_user)):
    service.finish_refresh(db, product_id, data.error.strip())
    return {"ok": True}

@router.get("/{list_id}")
def get_list(list_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return service.list_detail(db, _list(db, user, list_id))

@router.put("/{list_id}")
def update_list(list_id: int, data: ListWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    row = _list(db, user, list_id)
    row.school, row.grade, row.year = data.school.strip(), data.grade.strip(), data.year
    row.notes, row.refresh_hours = data.notes, data.refresh_hours
    row.public, row.turmas, row.contact = data.public, service.clean_turmas(data.turmas), data.contact.strip()
    db.commit()
    return service.list_detail(db, row)

@router.delete("/{list_id}", status_code=204)
def delete_list(list_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Apaga a lista, os itens e as opções. Os produtos continuam cadastrados em Produtos."""
    row = _list(db, user, list_id)
    item_ids = list(db.scalars(select(SchoolListItem.id).where(SchoolListItem.list_id == row.id)))
    if item_ids:
        db.query(SchoolListOption).filter(SchoolListOption.item_id.in_(item_ids)).delete(synchronize_session=False)
        db.query(SchoolListItem).filter(SchoolListItem.id.in_(item_ids)).delete(synchronize_session=False)
    db.delete(row); db.commit()

@router.post("/{list_id}/items", status_code=201)
def add_item(list_id: int, data: ItemWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    row = _list(db, user, list_id)
    item = SchoolListItem(list_id=row.id, section=data.section, name=data.name.strip(), requested=data.requested.strip(),
                          color=data.color.strip(), position=_next_position(db, row.id, data.section))
    db.add(item); db.commit()
    return service.list_detail(db, row)

@router.post("/{list_id}/items/import")
def import_items(list_id: int, data: ImportText, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Cola a lista da escola como texto, um item por linha."""
    row = _list(db, user, list_id)
    parsed = service.parse_lines(data.text)
    if not parsed:
        raise HTTPException(422, "Nenhum item encontrado no texto. Use um item por linha.")
    position = _next_position(db, row.id, data.section)
    for offset, entry in enumerate(parsed):
        db.add(SchoolListItem(list_id=row.id, section=data.section, name=entry["name"], requested=entry["requested"], position=position + offset))
    db.commit()
    detail = service.list_detail(db, row)
    detail["imported"] = len(parsed)
    return detail

@router.patch("/items/{item_id}")
def update_item(item_id: int, data: ItemPatch, db: Session = Depends(get_db), user: User = Depends(require_user)):
    item = _item(db, user, item_id)
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(item, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    return service.list_detail(db, _list(db, user, item.list_id))

@router.delete("/items/{item_id}")
def delete_item(item_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    item = _item(db, user, item_id)
    school_list = _list(db, user, item.list_id)
    db.query(SchoolListOption).filter(SchoolListOption.item_id == item.id).delete(synchronize_session=False)
    db.delete(item); db.commit()
    return service.list_detail(db, school_list)

@router.put("/items/{item_id}/options/{slot}")
def set_option(item_id: int, slot: int, data: OptionWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Define o produto de uma opção. Um link novo vira produto (a extensão completa nome, foto e preço)."""
    if slot not in (0, 1, 2):
        raise HTTPException(422, "Cada item tem no máximo 3 opções.")
    item = _item(db, user, item_id)
    if data.product_id is not None:
        product = db.get(Product, data.product_id)
        if product is None:
            raise HTTPException(404, "Produto não encontrado")
    elif data.url is not None:
        original = normalize_product_url(str(data.url))
        product = db.scalar(select(Product).where(Product.original_url == original))
        if product is None:
            # "pending" (e não "awaiting_browser"): a leitura pela extensão completa os dados sem gerar
            # publicação automática; produto de lista escolar só vira oferta quando você quiser.
            product = Product(original_url=original, affiliate_url=original, marketplace=marketplace_of(original), notes="", status="pending")
            if needs_browser(original):
                add_note(product, BROWSER_NOTICE)
            db.add(product); db.flush()
    else:
        raise HTTPException(422, "Cole o link do produto ou escolha um produto cadastrado.")
    option = db.scalar(select(SchoolListOption).where(SchoolListOption.item_id == item.id, SchoolListOption.slot == slot))
    if option is None:
        option = SchoolListOption(item_id=item.id, slot=slot, product_id=product.id)
        db.add(option)
    option.product_id, option.label = product.id, data.label.strip() or service.DEFAULT_LABELS[slot]
    option.buy_qty, option.watch, option.last_error, option.refresh_claimed_at = data.buy_qty, data.watch, "", None
    db.commit()
    detail = service.list_detail(db, _list(db, user, item.list_id))
    detail["product_id"] = product.id
    return detail

@router.patch("/items/{item_id}/options/{slot}")
def update_option(item_id: int, slot: int, data: OptionPatch, db: Session = Depends(get_db), user: User = Depends(require_user)):
    item = _item(db, user, item_id)
    option = db.scalar(select(SchoolListOption).where(SchoolListOption.item_id == item.id, SchoolListOption.slot == slot))
    if option is None:
        raise HTTPException(404, "Opção não encontrada")
    for key, value in data.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(option, key, value.strip() if isinstance(value, str) else value)
    db.commit()
    return service.list_detail(db, _list(db, user, item.list_id))

@router.delete("/items/{item_id}/options/{slot}")
def delete_option(item_id: int, slot: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    item = _item(db, user, item_id)
    db.query(SchoolListOption).filter(SchoolListOption.item_id == item.id, SchoolListOption.slot == slot).delete(synchronize_session=False)
    db.commit()
    return service.list_detail(db, _list(db, user, item.list_id))

@router.get("/{list_id}/page.html")
def export_page(list_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Página de orçamento para os pais, pronta para publicar no seu site (um arquivo só)."""
    row = _list(db, user, list_id)
    detail = service.list_detail(db, row)
    rule = main_rule(db)
    disclosure = (getattr(rule, "disclosure_text", "") or "#publi") if rule else "#publi"
    oldest = service.aware(min((p.captured_at for p in db.scalars(
        select(Product).join(SchoolListOption, SchoolListOption.product_id == Product.id)
        .join(SchoolListItem, SchoolListItem.id == SchoolListOption.item_id)
        .where(SchoolListItem.list_id == row.id, Product.captured_at.is_not(None)))), default=None))
    body = service.render_page(detail, disclosure, oldest)
    name = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", f"orcamento {row.grade} {row.year}").encode("ascii", "ignore").decode().lower()).strip("-")
    return Response(body, media_type="text/html; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{name}.html"'})


# ------------------------------------------------------------------ responsáveis (quem se identificou na página pública)

visitors_router = APIRouter(prefix="/api/school-visitors", tags=["school-lists"])

class VisitorIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)

def _visitors_query(user: User, list_id: int | None, q: str | None):
    stmt = select(SchoolVisitor).where(SchoolVisitor.owner_id == user.id)
    if list_id: stmt = stmt.where(SchoolVisitor.list_id == list_id)
    if q: stmt = stmt.where(SchoolVisitor.student_name.ilike(f"%{q.strip()}%"))
    return stmt

def _visitor_read(v: SchoolVisitor) -> dict:
    return {"id": v.id, "list_id": v.list_id, "school": v.school, "student_name": v.student_name, "turma": v.turma,
            "visits": v.visits, "created_at": service.aware(v.created_at).isoformat() if v.created_at else None,
            "last_seen_at": service.aware(v.last_seen_at).isoformat() if v.last_seen_at else None}

@visitors_router.get("")
def list_visitors(response: Response, list_id: int | None = None, q: str | None = None, limit: int = 50, offset: int = 0,
                  db: Session = Depends(get_db), user: User = Depends(require_user)):
    stmt = _visitors_query(user, list_id, q)
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())))
    rows = db.scalars(stmt.order_by(SchoolVisitor.last_seen_at.desc(), SchoolVisitor.id.desc()).offset(max(0, offset)).limit(max(1, min(limit, 200))))
    return [_visitor_read(v) for v in rows]

@visitors_router.get("/export.csv")
def export_visitors(list_id: int | None = None, q: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_user)):
    import csv, io
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow(["Aluno", "Turma", "Escola", "Acessos", "Primeiro acesso", "Último acesso"])
    for v in db.scalars(_visitors_query(user, list_id, q).order_by(SchoolVisitor.turma, SchoolVisitor.student_name)):
        r = _visitor_read(v)
        writer.writerow([r["student_name"], r["turma"], r["school"], r["visits"], r["created_at"], r["last_seen_at"]])
    return Response("\ufeff" + buffer.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="responsaveis.csv"'})

@visitors_router.post("/bulk/delete")
def delete_visitors(data: VisitorIds, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Exclui os registros (pedido do responsável ou limpeza). O cookie no navegador deixa de valer."""
    rows = list(db.scalars(select(SchoolVisitor).where(SchoolVisitor.owner_id == user.id, SchoolVisitor.id.in_(data.ids))))
    for v in rows:
        db.delete(v)
    db.commit()
    return {"deleted": len(rows)}
