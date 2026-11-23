"""API das buscas automáticas (Mercado Livre): buscas salvas, achados e agenda dos grupos."""
import json
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.publication import Publication
from app.models.search import GroupSchedule, Listing, Search
from app.searches import service
from app.searches.service import SEARCH_LEASE_MINUTES, as_utc, lines, now, search_url

router = APIRouter(prefix="/api/searches", tags=["searches"])


# ---------------------------------------------------------------- esquemas

class SearchWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    terms: str = Field(min_length=1, max_length=4000)
    exclude_terms: str = Field(default="", max_length=4000)
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_discount: int = Field(default=0, ge=0, le=95)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    free_shipping_only: bool = False
    group_name: str = Field(default="", max_length=160)
    mode: str = Field(default="approval", pattern="^(approval|auto)$")
    interval_minutes: int = Field(default=120, ge=30, le=10080)
    max_per_run: int = Field(default=5, ge=1, le=50)
    active: bool = True

    @field_validator("terms")
    @classmethod
    def _terms(cls, value: str) -> str:
        items = lines(value)
        if not items:
            raise ValueError("Informe pelo menos um termo de busca")
        if len(items) > 10:
            raise ValueError("Use no máximo 10 termos por busca")
        return "\n".join(items)

class SearchRead(SearchWrite):
    model_config = ConfigDict(from_attributes=True)
    id: int
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_result: str
    pending: int = 0

class ListingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    external_id: str
    search_id: int | None
    term: str
    url: str
    title: str
    image_url: str
    seller: str
    price: float | None
    original_price: float | None
    price_note: str
    discount_pct: int | None
    rating: float | None
    sold: int | None
    free_shipping: bool
    min_price_30d: float | None
    score: int
    matches: bool
    reject_reason: str
    status: str
    publication_id: int | None
    first_seen_at: datetime
    last_seen_at: datetime

class ResultItem(BaseModel):
    external_id: str = Field(max_length=40)
    url: str = Field(max_length=2048)
    term: str = Field(default="", max_length=160)
    title: str = Field(default="", max_length=500)
    image_url: str = Field(default="", max_length=2048)
    seller: str = Field(default="", max_length=160)
    price: float | None = Field(default=None, ge=0)
    original_price: float | None = Field(default=None, ge=0)
    price_note: str = Field(default="", max_length=60)
    rating: float | None = Field(default=None, ge=0, le=5)
    sold: int | None = Field(default=None, ge=0)
    free_shipping: bool = False
    official_store: bool = False
    fulfillment: bool = False
    ml_category_id: str | None = Field(default=None, max_length=20)
    catalog_product_id: str | None = Field(default=None, max_length=20)   # /p/MLB...: mesmo produto em várias lojas

class Results(BaseModel):
    items: list[ResultItem] = Field(default_factory=list, max_length=500)
    error: str = Field(default="", max_length=500)

class Decision(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)
    # Horário escolhido para o primeiro; os seguintes respeitam o intervalo do grupo. Vazio = distribuir na agenda.
    scheduled_at: datetime | None = None

class AcceptAll(BaseModel):
    search_id: int | None = None

class OfficialPick(BaseModel):
    id: str = Field(max_length=20)
    include_children: bool = True
    name: str = Field(default="", max_length=200)
    path: str = Field(default="", max_length=1000)

class ScheduleWrite(BaseModel):
    categories: list[str] = Field(default_factory=list, max_length=50)
    ml_categories: list[OfficialPick] = Field(default_factory=list, max_length=100)
    active: bool = True
    start_hour: int = Field(default=8, ge=0, le=23)
    end_hour: int = Field(default=22, ge=1, le=24)
    max_per_day: int = Field(default=12, ge=1, le=200)
    gap_minutes: int = Field(default=40, ge=5, le=1440)
    repost_days: int = Field(default=7, ge=0, le=365)

class ScheduleRead(ScheduleWrite):
    group_name: str


# ---------------------------------------------------------------- buscas salvas

def _get(db: Session, search_id: int) -> Search:
    search = db.get(Search, search_id)
    if not search:
        raise HTTPException(404, "Busca não encontrada")
    return search

def _check(data: SearchWrite) -> None:
    if data.min_price is not None and data.max_price is not None and data.min_price > data.max_price:
        raise HTTPException(422, "O preço mínimo não pode ser maior que o máximo")
    if data.mode == "auto" and not data.group_name.strip():
        raise HTTPException(422, "O modo automático precisa de um grupo de destino")

def _read(db: Session, search: Search) -> SearchRead:
    pending = db.scalar(select(func.count(Listing.id)).where(Listing.search_id == search.id, Listing.status == "new",
                                                             Listing.matches.is_(True))) or 0
    return SearchRead.model_validate(search).model_copy(update={"pending": pending})

@router.get("", response_model=list[SearchRead])
def list_searches(db: Session = Depends(get_db)):
    return [_read(db, s) for s in db.scalars(select(Search).order_by(Search.name, Search.id))]

@router.post("", response_model=SearchRead, status_code=201)
def create_search(data: SearchWrite, db: Session = Depends(get_db)):
    _check(data)
    search = Search(**data.model_dump(), next_run_at=now() if data.active else None, created_at=now())
    search.group_name = search.group_name.strip()
    db.add(search); db.commit(); db.refresh(search)
    return _read(db, search)

@router.put("/{search_id}", response_model=SearchRead)
def update_search(search_id: int, data: SearchWrite, db: Session = Depends(get_db)):
    _check(data)
    search = _get(db, search_id)
    was_active = search.active
    for key, value in data.model_dump().items():
        setattr(search, key, value.strip() if isinstance(value, str) else value)
    if search.active and (not was_active or search.next_run_at is None):
        search.next_run_at = now()
    if not search.active:
        search.next_run_at = None
    db.commit(); db.refresh(search)
    return _read(db, search)

@router.delete("/{search_id}", status_code=204)
def delete_search(search_id: int, db: Session = Depends(get_db)):
    search = _get(db, search_id)
    db.delete(search); db.commit()
    return Response(status_code=204)

@router.post("/{search_id}/run", response_model=SearchRead)
def run_now(search_id: int, db: Session = Depends(get_db)):
    """Pede para a extensão rodar esta busca na próxima verificação (em até 30 s)."""
    search = _get(db, search_id)
    search.next_run_at = now()
    db.commit(); db.refresh(search)
    return _read(db, search)


# ---------------------------------------------------------------- usado pela extensão

@router.get("/due")
def due_search(db: Session = Depends(get_db)):
    """A próxima busca na hora de rodar. Fica reservada por alguns minutos para não rodar duas vezes."""
    search = db.scalar(select(Search).where(Search.active.is_(True), Search.next_run_at.is_not(None),
                                            Search.next_run_at <= now())
                       .order_by(Search.next_run_at, Search.id).limit(1))
    if search is None:
        return None
    search.next_run_at = now() + timedelta(minutes=SEARCH_LEASE_MINUTES)
    db.commit()
    return {"id": search.id, "name": search.name,
            "terms": [{"term": term, "url": search_url(term)} for term in lines(search.terms)]}

@router.post("/{search_id}/results")
def receive_results(search_id: int, data: Results, db: Session = Depends(get_db)):
    search = _get(db, search_id)
    counts = service.ingest(db, search, [item.model_dump() for item in data.items])
    auto = service.auto_approve(db, search) if not data.error else {"scheduled": [], "skipped": []}
    search.last_run_at = now()
    search.next_run_at = now() + timedelta(minutes=search.interval_minutes) if search.active else None
    parts = [f"{counts['read']} anúncios lidos", f"{counts['new']} novos", f"{counts['matching']} na lista"]
    if auto["scheduled"]:
        parts.append(f"{len(auto['scheduled'])} agendados automaticamente")
    search.last_result = (f"Erro: {data.error}. " if data.error else "") + ", ".join(parts)
    db.commit()
    return {**counts, "auto_scheduled": len(auto["scheduled"]), "message": search.last_result}


# ---------------------------------------------------------------- achados

listings_router = APIRouter(prefix="/api/listings", tags=["searches"])

@listings_router.get("", response_model=list[ListingRead])
def list_listings(response: Response, status: str = "new", search_id: int | None = None,
                  matches: str = Query(default="true", pattern="^(true|false|all)$"),
                  limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    stmt = select(Listing)
    if status:
        stmt = stmt.where(Listing.status == status)
    if search_id:
        stmt = stmt.where(Listing.search_id == search_id)
    if matches != "all":
        stmt = stmt.where(Listing.matches.is_(matches == "true"))
    response.headers["X-Total-Count"] = str(db.scalar(select(func.count()).select_from(stmt.subquery())))
    order = (Listing.score.desc(), Listing.id.desc()) if status == "new" else (Listing.decided_at.desc(), Listing.id.desc())
    return list(db.scalars(stmt.order_by(*order).offset(max(0, offset)).limit(max(1, min(limit, 200)))))

def _listings(db: Session, ids: list[int]) -> list[Listing]:
    found = list(db.scalars(select(Listing).where(Listing.id.in_(ids))))
    if not found:
        raise HTTPException(404, "Nenhum achado encontrado")
    return found

@listings_router.post("/approve")
def approve_listings(data: Decision, db: Session = Depends(get_db)):
    if data.scheduled_at is not None and as_utc(data.scheduled_at) < now() - timedelta(minutes=1):
        raise HTTPException(422, "Escolha um horário no futuro")
    result = service.approve(db, _listings(db, data.ids), when=data.scheduled_at)
    db.commit()
    return result

@listings_router.post("/accept-all")
def accept_all(data: AcceptAll, db: Session = Depends(get_db)):
    stmt = select(Listing).where(Listing.status == "new", Listing.matches.is_(True))
    if data.search_id:
        stmt = stmt.where(Listing.search_id == data.search_id)
    items = list(db.scalars(stmt.order_by(Listing.score.desc()).limit(200)))
    result = service.approve(db, items) if items else {"scheduled": [], "skipped": []}
    db.commit()
    return result

@listings_router.post("/discard")
def discard_listings(data: Decision, db: Session = Depends(get_db)):
    count = service.discard(_listings(db, data.ids))
    db.commit()
    return {"discarded": count}

@listings_router.post("/restore")
def restore_listings(data: Decision, db: Session = Depends(get_db)):
    count = service.restore(_listings(db, data.ids))
    db.commit()
    return {"restored": count}

@listings_router.get("/{listing_id}/history")
def price_history(listing_id: int, db: Session = Depends(get_db)):
    from app.models.search import PricePoint
    rows = db.scalars(select(PricePoint).where(PricePoint.listing_id == listing_id).order_by(PricePoint.seen_at))
    return [{"price": p.price, "seen_at": p.seen_at} for p in rows]


# ---------------------------------------------------------------- agenda dos grupos

schedules_router = APIRouter(prefix="/api/group-schedules", tags=["searches"])

@schedules_router.get("", response_model=list[ScheduleRead])
def list_schedules(db: Session = Depends(get_db)):
    """Agendas salvas e os grupos usados nas buscas (com os valores padrão)."""
    groups = {g.strip() for g in db.scalars(select(Search.group_name)) if g and g.strip()}
    groups |= {g.strip() for g in db.scalars(select(Publication.group_name).distinct()) if g and g.strip()}
    groups |= set(db.scalars(select(GroupSchedule.group_name)))
    def read(g: str) -> ScheduleRead:
        s = service.group_schedule(db, g)
        values = {k: getattr(s, k) for k in ScheduleWrite.model_fields if k not in ("categories", "active", "ml_categories")}
        return ScheduleRead(group_name=g, categories=json.loads(s.categories or "[]"), ml_categories=json.loads(getattr(s, "ml_categories", None) or "[]"),
                            active=True if s.active is None else s.active, **values)
    return [read(g) for g in sorted(groups, key=str.casefold)]

@schedules_router.put("/{group_name}", response_model=ScheduleRead)
def save_schedule(group_name: str, data: ScheduleWrite, db: Session = Depends(get_db)):
    group_name = group_name.strip()
    if not group_name:
        raise HTTPException(422, "Informe o grupo")
    if data.end_hour <= data.start_hour:
        raise HTTPException(422, "O horário final precisa ser depois do inicial")
    schedule = db.scalar(select(GroupSchedule).where(GroupSchedule.group_name == group_name))
    if schedule is None:
        schedule = GroupSchedule(group_name=group_name); db.add(schedule)
    for key, value in data.model_dump().items():
        if key == "categories":
            from app.campaigns.service import clean_list
            value = json.dumps(clean_list(value), ensure_ascii=False)
        elif key == "ml_categories":
            value = json.dumps(value, ensure_ascii=False)
        setattr(schedule, key, value)
    db.commit()
    return ScheduleRead(group_name=group_name, **data.model_dump())

@schedules_router.delete("/{group_name}", status_code=204)
def delete_schedule(group_name: str, db: Session = Depends(get_db)):
    """Remove o grupo do cadastro (publicações e buscas que usam o nome continuam como estão)."""
    schedule = db.scalar(select(GroupSchedule).where(GroupSchedule.group_name == group_name.strip()))
    if schedule:
        db.delete(schedule); db.commit()
    return Response(status_code=204)

@schedules_router.get("/{group_name}/next")
def preview_slots(group_name: str, count: int = 5, db: Session = Depends(get_db)):
    return [slot.isoformat() for slot in service.next_slots(db, group_name.strip(), max(1, min(count, 50)))]
