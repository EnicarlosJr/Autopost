from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.product import Product
from app.models.publication import Publication
from app.publications.messages import normalize_offer_text
from app.publications.service import (record_event, release_due, approval_required, as_utc, conflict_reason, initial_status, main_rule, now,
                                      offer_text, price_needs_check)

router = APIRouter(prefix="/api/publications", tags=["publications"])

EDITABLE = {"pending", "awaiting_approval", "approved", "scheduled", "failed"}

class Offer(BaseModel):
    product_id: int
    message: str = Field(min_length=1, max_length=4096)
    scheduled_at: datetime | None = None
    group_name: str = Field(default="", max_length=160)
    force_repost: bool = False
    send_mode: str | None = Field(default=None, pattern="^(preview|image)$")   # vazio = padrão

class OfferUpdate(BaseModel):
    message: str | None = Field(default=None, min_length=1, max_length=4096)
    group_name: str | None = Field(default=None, max_length=160)
    scheduled_at: datetime | None = None
    clear_schedule: bool = False
    send_mode: str | None = Field(default=None, pattern="^(preview|image|default)$")   # "default" volta ao padrão

class SendReceipt(BaseModel):
    group_name: str | None = Field(default=None, max_length=160)
    # Como o envio foi confirmado (prévia do link, mensagem vista na conversa); vai para o histórico.
    detail: str = Field(default="", max_length=500)

class SendFailure(BaseModel):
    error: str = Field(default="Falha no envio", max_length=2000)

class BulkIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)

class ProductBrief(BaseModel):
    """O essencial do produto para mostrar e enviar a publicação, sem outra consulta."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    title: str
    image_url: str
    original_url: str
    affiliate_url: str
    price: float | None
    original_price: float | None
    price_note: str = ""
    status: str
    captured_at: datetime | None = None

class PublicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    campaign_id: int | None = None
    id: int
    product_id: int
    group_name: str
    message: str
    status: str
    created_at: datetime
    sent_at: datetime | None
    scheduled_at: datetime | None
    approved_at: datetime | None = None
    send_attempts: int = 0
    last_error: str = ""
    send_mode: str = "preview"          # "preview" (texto com prévia do link) ou "image" (foto + legenda)
    send_mode_choice: str | None = None  # escolhida só para esta publicação (vazio = padrão)
    outgoing_message: str = ""           # exatamente o que vai para o grupo (com o #publi no topo)
    product: ProductBrief | None = None

    @field_validator("message")
    @classmethod
    def clean_legacy_disclosure(cls, value: str) -> str:
        return normalize_offer_text(value)

def _get(db: Session, publication_id: int) -> Publication:
    publication = db.get(Publication, publication_id)
    if not publication:
        raise HTTPException(404, "Publicação não encontrada")
    return publication

def _validate_schedule(value: datetime | None) -> None:
    if value is None:
        return
    if value.tzinfo is None:
        raise HTTPException(422, "A data programada precisa incluir fuso horário")
    if value <= now():
        raise HTTPException(422, "A data programada precisa estar no futuro")

def _commit(db: Session, publication: Publication) -> Publication:
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Já existe uma publicação ativa deste produto para este grupo")
    db.refresh(publication)
    return publication

@router.get("/preview/{product_id}")
def preview(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    return {"product_id": product.id, "image_url": product.image_url, "title": product.title, "message": offer_text(db, product)}

@router.get("/summary")
def publication_summary(db: Session = Depends(get_db)):
    product_counts = dict(db.execute(select(Product.status, func.count()).group_by(Product.status)).all())
    publication_counts = dict(db.execute(select(Publication.status, func.count()).group_by(Publication.status)).all())
    return {
        "total_products": sum(product_counts.values()),
        "pending": product_counts.get("pending", 0) + product_counts.get("processing", 0),
        "processed": product_counts.get("processed", 0),
        "errors": product_counts.get("error", 0),
        "needs_review": product_counts.get("needs_review", 0),
        "awaiting_browser": product_counts.get("awaiting_browser", 0),
        "publications": sum(publication_counts.values()),
        "awaiting_approval": publication_counts.get("awaiting_approval", 0) + publication_counts.get("pending", 0),
        "approved": publication_counts.get("approved", 0),
        "scheduled": publication_counts.get("scheduled", 0),
        "sent": publication_counts.get("sent", 0),
        "failed": publication_counts.get("failed", 0),
        "cancelled": publication_counts.get("cancelled", 0),
    }

@router.get("/queue", response_model=list[PublicationRead])
def send_queue(group_name: str | None = None, limit: int = 50, db: Session = Depends(get_db)):
    """Publicações aprovadas e prontas para sair, na ordem de envio (libera antes os agendamentos vencidos)."""
    if release_due(db, "api-queue"):
        db.commit()
    stmt = select(Publication).where(Publication.status == "approved",
                                     or_(Publication.scheduled_at.is_(None), Publication.scheduled_at <= now()))
    if group_name:
        stmt = stmt.where(Publication.group_name == group_name)
    stmt = stmt.order_by(func.coalesce(Publication.scheduled_at, Publication.approved_at, Publication.created_at), Publication.id)
    return list(db.scalars(stmt.limit(max(1, min(limit, 200)))))

@router.get("", response_model=list[PublicationRead])
def list_publications(response: Response, status: str | None = None, group_name: str | None = None,
                      campaign_id: int | None = None, q: str | None = None, sort: str = "default",
                      limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Publication)
    if status:
        # "pending" é o nome antigo de "awaiting_approval"; os dois aparecem juntos.
        stmt = stmt.where(Publication.status.in_(status.split(",") + (["pending"] if "awaiting_approval" in status else [])))
    if group_name:
        stmt = stmt.where(Publication.group_name == group_name)
    if campaign_id:
        stmt = stmt.where(Publication.campaign_id == campaign_id)
    if q:
        stmt = stmt.join(Product, Product.id == Publication.product_id).where(Product.title.ilike(f"%{q[:100]}%"))
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())))
    order = Publication.scheduled_at.asc() if status == "scheduled" else Publication.created_at.desc()
    if sort == "oldest":
        order = Publication.created_at.asc()
    elif sort == "newest":
        order = Publication.created_at.desc()
    return list(db.scalars(stmt.order_by(order, Publication.id.desc()).offset(max(0, offset)).limit(max(1, min(limit, 200)))))

@router.post("", response_model=PublicationRead, status_code=201)
def create_publication(data: Offer, db: Session = Depends(get_db)):
    product = db.get(Product, data.product_id)
    if not product:
        raise HTTPException(404, "Produto não encontrado")
    _validate_schedule(data.scheduled_at)
    group = data.group_name.strip()
    if not group:
        rule = main_rule(db)
        group = (rule.whatsapp_group_name if rule else "").strip()
    conflict = conflict_reason(db, product.id, group)
    if conflict and not (conflict[0] == "recent" and data.force_repost):
        raise HTTPException(409, conflict[1])
    publication = Publication(product_id=product.id, message=normalize_offer_text(data.message), group_name=group,
                              scheduled_at=data.scheduled_at, send_mode_choice=data.send_mode)
    publication.status = initial_status(publication, approval_required(db))
    db.add(publication)
    return _commit(db, publication)

@router.get("/{publication_id}", response_model=PublicationRead)
def get_publication(publication_id: int, db: Session = Depends(get_db)):
    return _get(db, publication_id)

@router.patch("/{publication_id}", response_model=PublicationRead)
def update_publication(publication_id: int, data: OfferUpdate, db: Session = Depends(get_db)):
    publication = _get(db, publication_id)
    if publication.status not in EDITABLE:
        raise HTTPException(409, "Esta publicação não pode mais ser editada")
    if data.message is not None:
        publication.message = normalize_offer_text(data.message)
    if data.group_name is not None and data.group_name.strip() != publication.group_name:
        group = data.group_name.strip()
        conflict = conflict_reason(db, publication.product_id, group, exclude_id=publication.id)
        if conflict and conflict[0] == "active":
            raise HTTPException(409, conflict[1])
        publication.group_name = group
    if data.send_mode is not None:
        publication.send_mode_choice = None if data.send_mode == "default" else data.send_mode
    if data.clear_schedule:
        publication.scheduled_at = None
    elif data.scheduled_at is not None:
        _validate_schedule(data.scheduled_at)
        publication.scheduled_at = data.scheduled_at
    if publication.status != "failed":
        # Recalcula o estado: agendada se a data é futura, senão aprovada ou aguardando aprovação.
        publication.status = initial_status(publication, approval_required(db))
    return _commit(db, publication)

def _approve(publication: Publication) -> bool:
    if publication.status in {"pending", "awaiting_approval", "failed"}:
        publication.approved_at = now()
        scheduled = as_utc(publication.scheduled_at)
        publication.status = "scheduled" if scheduled and scheduled > now() else "approved"
        publication.last_error = ""
        return True
    if publication.status == "scheduled" and publication.approved_at is None:
        publication.approved_at = now()
        return True
    return False

@router.post("/bulk/approve", response_model=list[PublicationRead])
def bulk_approve(data: BulkIds, db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Publication).where(Publication.id.in_(data.ids))))
    changed = [p for p in rows if _approve(p)]
    db.commit()
    for p in changed:
        db.refresh(p)
    return changed

@router.post("/bulk/cancel")
def bulk_cancel(data: BulkIds, db: Session = Depends(get_db)):
    """Remove da fila várias publicações de uma vez (as que ainda não foram enviadas)."""
    rows = [p for p in db.scalars(select(Publication).where(Publication.id.in_(data.ids))) if p.status in EDITABLE | {"paused"}]
    for p in rows:
        p.status = "cancelled"
    db.commit()
    return {"cancelled": len(rows)}

DELETABLE = {"cancelled", "failed"}


@router.post("/bulk/delete")
def bulk_delete(data: BulkIds, db: Session = Depends(get_db)):
    """Apaga de vez publicações canceladas ou com falha. Enviadas ficam: elas contam para o prazo de repostagem."""
    from app.models.search import Listing
    rows = list(db.scalars(select(Publication).where(Publication.id.in_(data.ids))))
    gone = [p for p in rows if p.status in DELETABLE]
    ids = [p.id for p in gone]
    if ids:
        db.execute(update(Listing).where(Listing.publication_id.in_(ids)).values(publication_id=None))
        for p in gone:
            db.delete(p)
    db.commit()
    return {"deleted": len(gone), "skipped": len(rows) - len(gone)}


@router.post("/{publication_id}/approve", response_model=PublicationRead)
def approve(publication_id: int, db: Session = Depends(get_db)):
    publication = _get(db, publication_id)
    if not _approve(publication):
        raise HTTPException(409, "Ação incompatível com o estado atual")
    return _commit(db, publication)

@router.post("/{publication_id}/cancel", response_model=PublicationRead)
def cancel(publication_id: int, db: Session = Depends(get_db)):
    publication = _get(db, publication_id)
    if publication.status not in EDITABLE:
        raise HTTPException(409, "Ação incompatível com o estado atual")
    publication.status = "cancelled"
    return _commit(db, publication)

@router.get("/{publication_id}/image")
def publication_image(publication_id: int, db: Session = Depends(get_db)):
    """Foto padronizada (1080 x 1080, com a marca d'água da campanha) usada no envio "foto + texto"."""
    from app.products.social_image import social_image
    publication = _get(db, publication_id)
    if not publication.product:
        raise HTTPException(404, "Publicação sem produto")
    from app.publications.messages import discount_percent
    st, p = publication.style(), publication.product
    try:
        data = social_image(p, st["title"], st["handle"], st["disclosure"],
                            discount_percent(p.price, p.original_price) if st["show_discount"] else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

@router.post("/{publication_id}/claim", response_model=PublicationRead)
def claim_for_sending(publication_id: int, db: Session = Depends(get_db)):
    """Reserva a publicação para envio. Só um cliente consegue reservar (evita envio duplo).

    Se o preço do produto foi lido há mais tempo que PRICE_MAX_AGE_HOURS, responde 409 com
    code "stale_price": quem envia relê o produto no navegador e tenta de novo.
    """
    if release_due(db, "api-claim"):
        db.commit()
    pending = _get(db, publication_id)
    if pending.status == "approved" and pending.product and price_needs_check(pending.product):
        raise HTTPException(409, {"code": "stale_price", "product_id": pending.product.id,
                                  "url": pending.product.original_url, "affiliate_url": pending.product.affiliate_url,
                                  "message": "O preço precisa ser conferido antes do envio."})
    result = db.execute(update(Publication)
                        .where(Publication.id == publication_id, Publication.status == "approved",
                               or_(Publication.scheduled_at.is_(None), Publication.scheduled_at <= now()))
                        .values(status="sending", send_attempts=Publication.send_attempts + 1, updated_at=now())
                        .execution_options(synchronize_session="fetch"))
    db.commit()
    publication = _get(db, publication_id)
    if result.rowcount != 1:
        raise HTTPException(409, "A publicação precisa estar aprovada e liberada para envio")
    if not publication.group_name.strip():
        publication.status = "approved"
        db.commit()
        raise HTTPException(422, "Defina o grupo de destino da publicação antes de enviar")
    db.refresh(publication)
    return publication

@router.post("/{publication_id}/sent", response_model=PublicationRead)
def mark_publication_sent(publication_id: int, data: SendReceipt | None = None, db: Session = Depends(get_db)):
    publication = _get(db, publication_id)
    if publication.status not in {"sending", "approved"}:
        raise HTTPException(409, "A publicação precisa estar em envio para ser confirmada")
    if data and data.group_name and data.group_name.strip():
        publication.group_name = data.group_name.strip()
    publication.status = "sent"
    publication.sent_at = now()
    publication.last_error = ""
    record_event(db, "extensao", "publications.send", publication.product_id, "sent",
                 f"Publicação #{publication.id} enviada para \"{publication.group_name}\". {data.detail if data else ''}".strip())
    return _commit(db, publication)

class Postpone(BaseModel):
    minutes: int = Field(default=5, ge=1, le=240)
    reason: str = Field(default="", max_length=2000)

MAX_POSTPONES = 3

@router.post("/{publication_id}/postpone", response_model=PublicationRead)
def postpone_publication(publication_id: int, data: Postpone, db: Session = Depends(get_db)):
    """Devolve uma publicação em envio para a fila, alguns minutos depois (ex.: o WhatsApp não montou a prévia).
    Depois de MAX_POSTPONES tentativas, marca como falha para não ficar adiando para sempre."""
    publication = _get(db, publication_id)
    if publication.status not in ("sending", "approved"):
        raise HTTPException(409, "A publicação não está em envio")
    if publication.status == "approved":
        # Adiada antes de reservar (ex.: falha passageira ao gerar o link de afiliado): conta como tentativa.
        publication.send_attempts = (publication.send_attempts or 0) + 1
    publication.last_error = data.reason.strip()[:2000]
    if (publication.send_attempts or 0) >= MAX_POSTPONES:
        publication.status = "failed"
        record_event(db, "extensao", "publications.send", publication.product_id, "failed",
                     f"Publicação #{publication.id}: {publication.last_error} Desisti depois de {publication.send_attempts} tentativas.")
    else:
        publication.status = "scheduled"
        publication.scheduled_at = now() + timedelta(minutes=data.minutes)
        record_event(db, "extensao", "publications.postpone", publication.product_id, "scheduled",
                     f"Publicação #{publication.id} adiada {data.minutes} min: {publication.last_error}")
    return _commit(db, publication)

@router.post("/{publication_id}/failed", response_model=PublicationRead)
def mark_publication_failed(publication_id: int, data: SendFailure, db: Session = Depends(get_db)):
    publication = _get(db, publication_id)
    # "approved" também pode ser segurada (ex.: não foi possível conferir o preço antes de reservar).
    if publication.status not in {"sending", "approved"}:
        raise HTTPException(409, "A publicação não está em envio")
    publication.status = "failed"
    publication.last_error = data.error.strip()[:2000]
    record_event(db, "extensao", "publications.send", publication.product_id, "failed",
                 f"Publicação #{publication.id}: {publication.last_error}")
    return _commit(db, publication)
