from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import and_, case, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.product import Product
from app.products.media import remove_image
from app.products.service import apply_capture, apply_manual_edit, add_note
from app.products.sources import BROWSER_NOTICE, marketplace_of, needs_browser
from app.products.urls import normalize_product_url
from app.publications.service import main_rule, maybe_generate_publication
import json
from app.campaigns.service import clean_list, key, tags_of
from app.models.publication import Publication
from app.schemas.product import BrowserCapture, BrowserProductCreate, BulkProducts, BulkProductUpdate, ProductCreate, ProductRead, ProductUpdate
from app.workers.tasks import PROCESSING_TIMEOUT, process_product

router = APIRouter(prefix="/api/products", tags=["products"])

def _get(db: Session, product_id: int) -> Product:
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    return product

def _start_processing(db: Session, product: Product) -> None:
    """Lojas que bloqueiam o servidor ficam aguardando o navegador; as demais vão para o worker."""
    if needs_browser(product.original_url):
        product.status = "awaiting_browser"
        add_note(product, BROWSER_NOTICE)
        db.commit(); db.refresh(product)
        return
    product.status = "processing"
    product.processing_started_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(product)
    process_product.delay(product.id)

def _commit_new(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Este link de produto já está cadastrado")

@router.get("", response_model=list[ProductRead])
def list_products(response: Response, status: str | None = None, category: str | None = None,
                  marketplace: str | None = None, q: str | None = Query(default=None, max_length=100),
                  tag: str | None = Query(default=None, max_length=60),
                  sort: str = Query(default="newest", pattern="^(newest|oldest|price_asc|price_desc|title|discount)$"),
                  created_from: datetime | None = None, created_to: datetime | None = None,
                  limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Product)
    if status: stmt = stmt.where(Product.status.in_(status.split(",")))
    if category == "__none__": stmt = stmt.where(Product.category == "")
    elif category: stmt = stmt.where(Product.category.in_(category.split("|")))
    if tag: stmt = stmt.where(Product.tags.ilike(f'%"{tag}"%'))
    if created_from: stmt = stmt.where(Product.created_at >= created_from)
    if created_to: stmt = stmt.where(Product.created_at <= created_to)
    if marketplace: stmt = stmt.where(Product.marketplace == marketplace)
    if q: stmt = stmt.where(Product.title.ilike(f"%{q}%"))
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())))
    order = {"newest": (Product.created_at.desc(), Product.id.desc()), "oldest": (Product.created_at.asc(), Product.id.asc()),
             "price_asc": (Product.price.asc(), Product.id.desc()), "price_desc": (Product.price.desc(), Product.id.desc()),
             "title": (Product.title.asc(), Product.id.desc()),
             # Maior desconto primeiro (preço de antes acima do atual); sem desconto vai para o fim.
             "discount": (case((and_(Product.original_price > Product.price, Product.price.is_not(None)),
                                (Product.original_price - Product.price) / Product.original_price), else_=0).desc(), Product.id.desc())}[sort]
    stmt = stmt.order_by(*order)
    return list(db.scalars(stmt.offset(max(0, offset)).limit(max(1, min(limit, 200)))))

@router.post("", response_model=ProductRead, status_code=201)
def create_product(data: ProductCreate, db: Session = Depends(get_db)):
    original = normalize_product_url(str(data.original_url))
    if db.scalar(select(Product.id).where(Product.original_url == original)):
        raise HTTPException(409, "Este link de produto já está cadastrado")
    product = Product(original_url=original, affiliate_url=str(data.affiliate_url), marketplace=data.marketplace.strip() or marketplace_of(original),
                      category=data.category.strip(), notes=data.notes, status="pending")
    db.add(product)
    _commit_new(db)
    db.refresh(product)
    rule = main_rule(db)
    if rule is None or (rule.enabled and rule.process_on_create) or needs_browser(product.original_url):
        _start_processing(db, product)
    return product

@router.post("/from-browser")
def create_from_browser(data: BrowserProductCreate, db: Session = Depends(get_db)):
    """Cadastra (ou atualiza) um produto com os dados lidos pela extensão, sem passar pelo servidor da loja."""
    if not data.title.strip() and data.price is None:
        raise HTTPException(422, "A página não trouxe nome nem preço do produto")
    original = normalize_product_url(str(data.original_url))
    product = db.scalar(select(Product).where(Product.original_url == original))
    created = product is None
    if created:
        affiliate = str(data.affiliate_url) if data.affiliate_url else original
        product = Product(original_url=original, affiliate_url=affiliate, marketplace=data.marketplace.strip() or marketplace_of(original),
                          category=data.category.strip(), notes="", status="processing")
        db.add(product)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(409, "Este produto acabou de ser cadastrado por outra tela. Tente de novo.")
    else:
        if data.affiliate_url: product.affiliate_url = str(data.affiliate_url)
        if data.category.strip(): product.category = data.category.strip()
        if data.marketplace.strip(): product.marketplace = data.marketplace.strip()
    apply_capture(db, product, data, generate=created and not data.enqueue)
    publication = None
    if data.enqueue:
        group = data.group_name.strip() or None
        publication = maybe_generate_publication(db, product, force=True, group=group, approve=True)
    db.commit(); db.refresh(product)
    return {"created": created, "product": ProductRead.model_validate(product).model_dump(mode="json"),
            "publication_id": publication.id if publication else None,
            "publication_status": publication.status if publication else None}

@router.post("/bulk/update")
def bulk_update(data: BulkProductUpdate, db: Session = Depends(get_db)):
    """Altera categoria e tags de vários produtos de uma vez."""
    rows = list(db.scalars(select(Product).where(Product.id.in_(data.ids))))
    add, remove = clean_list(data.add_tags), {key(t) for t in data.remove_tags}
    for p in rows:
        if data.category is not None:
            p.category = data.category.strip()
        if add or remove:
            tags = [t for t in tags_of(p) if key(t) not in remove]
            tags += [t for t in add if key(t) not in {key(x) for x in tags}]
            p.tags = json.dumps(tags, ensure_ascii=False)
    db.commit()
    return {"updated": len(rows)}

@router.post("/bulk/delete")
def bulk_delete(data: BulkProducts, db: Session = Depends(get_db)):
    """Exclui vários produtos. Os que estão sendo enviados agora ficam de fora."""
    busy = set(db.scalars(select(Publication.product_id).where(Publication.product_id.in_(data.ids), Publication.status == "sending")))
    rows = [p for p in db.scalars(select(Product).where(Product.id.in_(data.ids))) if p.id not in busy]
    for p in rows:
        db.delete(p)
    db.commit()
    for p in rows:
        remove_image(p.id)
    return {"deleted": len(rows), "skipped": len(busy)}

@router.patch("/{product_id}", response_model=ProductRead)
def update_product(product_id: int, data: ProductUpdate, db: Session = Depends(get_db)):
    product = _get(db, product_id)
    apply_manual_edit(db, product, data.model_dump(exclude_unset=True))
    db.commit(); db.refresh(product)
    return product

@router.post("/{product_id}/reprocess", response_model=ProductRead)
def reprocess(product_id: int, db: Session = Depends(get_db)):
    product = _get(db, product_id)
    started = product.processing_started_at
    if started and started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    if product.status == "processing" and started and datetime.now(timezone.utc) - started < timedelta(seconds=PROCESSING_TIMEOUT):
        raise HTTPException(409, "Este produto já está sendo processado")
    _start_processing(db, product)
    return product

@router.post("/{product_id}/browser-data", response_model=ProductRead)
def apply_browser_capture(product_id: int, data: BrowserCapture, db: Session = Depends(get_db)):
    """Aplica os dados lidos no navegador do usuário (quando a loja bloqueia o servidor)."""
    product = _get(db, product_id)
    if not data.title.strip() and data.price is None:
        raise HTTPException(422, "A página aberta no navegador não trouxe nome nem preço do produto")
    apply_capture(db, product, data, generate=product.status == "awaiting_browser")
    db.commit(); db.refresh(product)
    return product

@router.delete("/{product_id}", status_code=204)
def delete_product(product_id: int, db: Session = Depends(get_db)):
    product = _get(db, product_id)
    db.delete(product); db.commit()
    remove_image(product_id)
