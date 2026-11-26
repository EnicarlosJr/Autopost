"""API das campanhas: rascunho, prévia, confirmação, pausa, retomada, cancelamento, duplicação e histórico."""
import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete as sql_delete, func, select, update
from sqlalchemy.orm import Session
from app.core.deps import require_user
from app.database.session import get_db
from app.models.campaign import Campaign, CampaignProduct, CampaignSearch, CampaignSearchResult, GroupSet
from app.models.catalog import MlCategory, Niche, NicheCategory
from app.models.search import Listing
from app.models.user import User
from app.campaigns import search_service
from app.models.product import Product
from app.models.publication import Publication
from app.models.search import GroupSchedule, Search
from app.campaigns import service
from app.campaigns.service import clean_list, jload, tags_of
from app.searches import ranking
from app.searches.service import OFFER_KINDS


router = APIRouter(prefix="/api/campaigns", tags=["campaigns"])
LISTS = ("product_ids", "categories", "exclude_categories", "tags", "exclude_tags", "groups", "weekdays",
         "niche_ids", "ml_categories", "include_keywords", "exclude_keywords")


class OfficialCategory(BaseModel):
    id: str = Field(max_length=20)
    include_children: bool = True
    name: str = Field(default="", max_length=200)
    path: str = Field(default="", max_length=1000)


class GroupTarget(BaseModel):
    group: str = Field(min_length=1, max_length=160)
    limit: int = Field(default=0, ge=0, le=500)          # 0 = automático
    categories: list[str] = Field(default_factory=list, max_length=50)
    ml_categories: list[OfficialCategory] = Field(default_factory=list, max_length=100)   # estratégia personalizada


class CampaignWrite(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    niche_ids: list[int] = Field(default_factory=list, max_length=20)
    ml_categories: list[OfficialCategory] = Field(default_factory=list, max_length=200)
    # Vários nichos juntos passam fácil de 50 palavras; a busca por nicho usa as palavras de cada nicho.
    include_keywords: list[str] = Field(default_factory=list, max_length=300)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=300)
    product_ids: list[int] = Field(default_factory=list, max_length=1000)
    categories: list[str] = Field(default_factory=list, max_length=50)
    exclude_categories: list[str] = Field(default_factory=list, max_length=50)
    tags: list[str] = Field(default_factory=list, max_length=50)
    tag_mode: str = Field(default="any", pattern="^(any|all)$")
    exclude_tags: list[str] = Field(default_factory=list, max_length=50)
    include_uncategorized: bool = False
    min_discount: int = Field(default=0, ge=0, le=95)
    groups: list[GroupTarget] = Field(default_factory=list, max_length=100)
    strategy: str = Field(default="balanced", pattern="^(sequential|balanced|category|custom)$")
    total_limit: int = Field(default=20, ge=1, le=service.MAX_MESSAGES)
    block_size: int = Field(default=1, ge=1, le=20)
    interval_minutes: int = Field(default=5, ge=1, le=1440)
    interval_max_minutes: int = Field(default=0, ge=0, le=1440)
    start_at: datetime | None = None
    start_hour: int = Field(default=8, ge=0, le=23)
    end_hour: int = Field(default=22, ge=1, le=24)
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)), max_length=7)
    daily_limit: int = Field(default=0, ge=0, le=500)
    pause_every: int = Field(default=0, ge=0, le=500)
    pause_minutes: int = Field(default=0, ge=0, le=1440)
    end_at: datetime | None = None
    message_gap_seconds: int = Field(default=20, ge=20, le=3600)
    reuse_days: int | None = Field(default=None, ge=0, le=365)
    group_daily_limit: int = Field(default=0, ge=0, le=500)
    send_mode: str = Field(default="preview", pattern="^(preview|image)$")
    watermark_text: str = Field(default="", max_length=80)
    watermark_handle: str = Field(default="", max_length=60)
    custom_style: bool = False                                 # falso = modelo e marca d'água do perfil
    message_template: str = Field(default="", max_length=4000)  # vazio = modelo do perfil

    @field_validator("message_template")
    @classmethod
    def _template(cls, value: str) -> str:
        from app.publications.messages import unknown_variables
        unknown = unknown_variables(value)
        if unknown:
            raise ValueError("Variáveis desconhecidas no modelo: " + ", ".join("{" + u + "}" for u in unknown))
        return value.strip()

    @field_validator("weekdays")
    @classmethod
    def _days(cls, value: list[int]) -> list[int]:
        return sorted({d for d in value if 0 <= d <= 6})

    def to_model(self, c: Campaign) -> Campaign:
        data = self.model_dump()
        for name in ("categories", "exclude_categories", "tags", "exclude_tags", "include_keywords", "exclude_keywords"):
            data[name] = clean_list(data[name])
        data["groups"] = [{**g, "group": " ".join(g["group"].split()), "categories": clean_list(g["categories"])}
                          for g in data["groups"]]
        for name, value in data.items():
            setattr(c, name, json.dumps(value, ensure_ascii=False) if name in LISTS else value)
        c.name = c.name.strip()
        return c


def _read(db: Session, c: Campaign) -> dict:
    counts = service.counts_of(db, c)
    total = sum(n for s, n in counts.items() if s != "cancelled")
    sent = counts.get("sent", 0)
    data = {name: getattr(c, name) for name in ("id", "name", "status", "tag_mode", "include_uncategorized", "min_discount",
            "strategy", "total_limit", "block_size", "interval_minutes", "interval_max_minutes", "start_at", "start_hour",
            "end_hour", "daily_limit", "pause_every", "pause_minutes", "created_at", "confirmed_at", "end_at",
            "message_gap_seconds", "reuse_days", "group_daily_limit", "send_mode", "watermark_text", "watermark_handle",
            "custom_style", "message_template")}
    data.update({name: jload(getattr(c, name)) for name in LISTS})
    data.update({
        "display_status": service.display_status(c, counts),
        "counts": counts, "total": total, "sent": sent, "failed": counts.get("failed", 0),
        "pending": sum(counts.get(s, 0) for s in ("scheduled", "approved", "sending", "paused")),
        "progress": round(sent * 100 / total) if total else 0,
        "next_send": service.next_send(db, c),
        "products_count": db.scalar(select(func.count()).select_from(CampaignProduct).where(CampaignProduct.campaign_id == c.id)) or 0,
        "searches_count": db.scalar(select(func.count()).select_from(CampaignSearch).where(CampaignSearch.campaign_id == c.id)) or 0,
        "niche_names": [n.name for n in db.scalars(select(Niche).where(Niche.id.in_(jload(c.niche_ids))))] if jload(c.niche_ids) else [],
    })
    return data


def _get(db: Session, campaign_id: int, user: User) -> Campaign:
    c = db.get(Campaign, campaign_id)
    # Campanha de outro perfil responde como inexistente.
    if not c or (c.owner_id is not None and c.owner_id != user.id):
        raise HTTPException(404, "Campanha não encontrada")
    return c


def _public(result: dict) -> dict:
    return {k: v for k, v in result.items() if not k.startswith("_")}


@router.get("")
def list_campaigns(response: Response, status: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = [_read(db, c) for c in db.scalars(select(Campaign).where((Campaign.owner_id == user.id) | Campaign.owner_id.is_(None))
                                               .order_by(Campaign.created_at.desc(), Campaign.id.desc()))]
    if status:
        rows = [r for r in rows if r["display_status"] in status.split(",")]
    response.headers["X-Total-Count"] = str(len(rows))
    return rows


@router.get("/options")
def options(db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Categorias, tags e grupos existentes, com contagem de produtos prontos, para montar os filtros."""
    categories: dict[str, int] = {}
    tags: dict[str, int] = {}
    uncategorized = 0
    for p in db.scalars(select(Product).where(Product.status == "processed")):
        if p.category.strip():
            categories[p.category.strip()] = categories.get(p.category.strip(), 0) + 1
        else:
            uncategorized += 1
        for t in tags_of(p):
            tags[t] = tags.get(t, 0) + 1
    groups = {g.group_name: g for g in db.scalars(select(GroupSchedule))}
    names = set(groups) | {g.strip() for g in db.scalars(select(Search.group_name)) if g and g.strip()} \
        | {g.strip() for g in db.scalars(select(Publication.group_name).distinct()) if g and g.strip()}
    return {
        "categories": [{"name": k, "count": v} for k, v in sorted(categories.items(), key=lambda x: x[0].casefold())],
        "tags": [{"name": k, "count": v} for k, v in sorted(tags.items(), key=lambda x: x[0].casefold())],
        "uncategorized": uncategorized,
        "groups": [{"name": n, "active": groups[n].active if n in groups else True,
                    "categories": jload(groups[n].categories) if n in groups else [],
                    "ml_categories": jload(groups[n].ml_categories) if n in groups else []}
                   for n in sorted(names, key=str.casefold)],
    }


@router.post("/preview")
def preview(data: CampaignWrite, campaign_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Prévia sem gravar nada. Com campaign_id, considera o que essa campanha já enviou."""
    if campaign_id:
        _get(db, campaign_id, user)
    # Objeto só em memória (não entra na sessão): a prévia nunca grava.
    c = data.to_model(Campaign(id=campaign_id))
    return _public(service.plan(db, c))


@router.post("", status_code=201)
def create_campaign(data: CampaignWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = data.to_model(Campaign(status="draft", owner_id=user.id))
    db.add(c); db.commit(); db.refresh(c)
    return _read(db, c)


@router.get("/{campaign_id}")
def get_campaign(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _read(db, _get(db, campaign_id, user))


@router.put("/{campaign_id}")
def update_campaign(campaign_id: int, data: CampaignWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status not in ("draft", "paused"):
        raise HTTPException(409, "Pause a campanha antes de editar. Campanhas canceladas podem ser duplicadas.")
    data.to_model(c)
    db.commit(); db.refresh(c)
    return _read(db, c)


@router.post("/{campaign_id}/confirm")
def confirm(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status not in ("draft", "paused"):
        raise HTTPException(409, "Só rascunhos e campanhas pausadas podem ser agendados.")
    result = service.apply(db, c)
    if result["errors"]:
        db.rollback()
        raise HTTPException(422, {"message": result["errors"][0], "errors": result["errors"]})
    if not result.get("created"):
        db.rollback()
        raise HTTPException(422, {"message": "Nenhum anúncio para agendar com esta configuração.", "errors": result["warnings"]})
    db.commit(); db.refresh(c)
    return {**_read(db, c), "plan": _public(result)}


@router.post("/{campaign_id}/pause")
def pause(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status != "scheduled":
        raise HTTPException(409, "Só campanhas agendadas ou em execução podem ser pausadas.")
    service.pause(db, c)
    db.commit()
    return _read(db, c)


@router.post("/{campaign_id}/resume")
def resume(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Retoma a partir de agora, replanejando os anúncios que ainda não saíram."""
    c = _get(db, campaign_id, user)
    if c.status != "paused":
        raise HTTPException(409, "Só campanhas pausadas podem ser retomadas.")
    c.start_at = None
    result = service.apply(db, c)
    if result["errors"]:
        db.rollback()
        raise HTTPException(422, {"message": result["errors"][0], "errors": result["errors"]})
    db.commit()
    return {**_read(db, c), "plan": _public(result)}


@router.post("/{campaign_id}/cancel")
def cancel(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status in ("cancelled", "draft"):
        raise HTTPException(409, "Esta campanha não está agendada.")
    service.cancel(db, c)
    db.commit()
    return _read(db, c)


@router.post("/{campaign_id}/duplicate", status_code=201)
def duplicate(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    copy = Campaign(status="draft", owner_id=user.id)
    for column in Campaign.__table__.columns:
        if column.name not in ("id", "status", "created_at", "confirmed_at", "updated_at", "start_at", "end_at"):
            setattr(copy, column.name, getattr(c, column.name))
    copy.name = f"{c.name} (cópia)"[:120]
    db.add(copy); db.commit(); db.refresh(copy)
    return _read(db, copy)


@router.delete("/{campaign_id}", status_code=204)
def delete(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    status = service.display_status(c, service.counts_of(db, c))
    if status not in ("draft", "cancelled", "completed", "failed"):
        raise HTTPException(409, "Cancele a campanha antes de excluir.")
    db.delete(c); db.commit()
    return Response(status_code=204)


# ---------------------------------------------------------------- nichos aplicados à campanha

@router.get("/{campaign_id}/sample-image")
def sample_image(campaign_id: int, product_id: int | None = None, title: str | None = None, handle: str | None = None,
                 db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Prévia da imagem do envio "foto + texto" (aceita a marca d'água ainda não salva, para ver antes de salvar)."""
    from app.products.social_image import social_image
    c = _get(db, campaign_id, user)
    pid = product_id or db.scalar(select(CampaignProduct.product_id).where(CampaignProduct.campaign_id == c.id)
                                  .order_by(CampaignProduct.added_at).limit(1))
    product = db.get(Product, pid) if pid else None
    if not product:
        raise HTTPException(404, "Adicione um produto à campanha para ver a imagem.")
    try:
        from app.publications.messages import clean_disclosure, discount_percent
        from app.publications.service import main_rule
        rule = main_rule(db)
        marks = c if c.custom_style else rule
        show = True if rule is None or rule.show_discount is None else bool(rule.show_discount)
        data = social_image(product, (getattr(marks, "watermark_text", "") or "") if title is None else title,
                            (getattr(marks, "watermark_handle", "") or "") if handle is None else handle,
                            clean_disclosure(rule.disclosure_text if rule else ""),
                            discount_percent(product.price, product.original_price) if show else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


@router.get("/{campaign_id}/niche-defaults")
def niche_defaults(campaign_id: int, niche_ids: str = "", db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Junta categorias e palavras dos nichos escolhidos (só do próprio perfil). A campanha recebe uma cópia."""
    if campaign_id:
        _get(db, campaign_id, user)
    ids = [int(x) for x in niche_ids.split(",") if x.strip().isdigit()]
    niches = list(db.scalars(select(Niche).where(Niche.id.in_(ids), Niche.owner_id == user.id)))
    cats, include, exclude = {}, [], []
    for n in niches:
        for link in db.scalars(select(NicheCategory).where(NicheCategory.niche_id == n.id)):
            cat = db.get(MlCategory, link.category_id)
            cats[link.category_id] = {"id": link.category_id, "include_children": link.include_children or cats.get(link.category_id, {}).get("include_children", False),
                                      "name": cat.name if cat else link.category_id, "path": cat.path_names if cat else "", "is_leaf": cat.is_leaf if cat else True}
        include += jload(n.include_keywords); exclude += jload(n.exclude_keywords)
    genders = {n.gender for n in niches if n.gender in ("male", "female")}
    return {"niche_ids": [n.id for n in niches], "categories": list(cats.values()),
            "include_keywords": clean_list(include), "exclude_keywords": clean_list(exclude),
            "gender": genders.pop() if len(genders) == 1 else "any"}


# ---------------------------------------------------------------- busca dentro da campanha

class SearchFilters(BaseModel):
    min_price: float | None = Field(default=None, ge=0)
    max_price: float | None = Field(default=None, ge=0)
    min_discount: int = Field(default=0, ge=0, le=95)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    free_shipping: bool = False
    allow_uncategorized: bool = False
    gender: str = Field(default="any", pattern="^(any|male|female)$")   # público: todos, masculino ou feminino
    gender_strict: bool = False         # só anúncios que dizem o público (ou unissex) no título ou na categoria
    # Confiabilidade: vendas mínimas, só loja oficial ou Full, e termos típicos de produto de baixa qualidade.
    trust: str = Field(default="custom", pattern="^(off|basic|high|custom)$")
    min_sold: int = Field(default=0, ge=0, le=1000000)
    official_or_full: bool = False
    exclude_suspicious: bool = False
    # Onde buscar: "search" (uma busca por palavra-chave) ou "offers" (área de ofertas do ML).
    source: str = Field(default="search", pattern="^(search|offers)$")
    offers_pages: int = Field(default=3, ge=1, le=5)
    # Seções da área de ofertas: all, lightning, deal_of_the_day, unbeatable, outlet (vazio = Oferta do dia).
    offer_kinds: list[str] = Field(default_factory=list, max_length=5)
    offers_rotate: bool = True            # cada nova busca de ofertas começa numa página diferente
    offers_start: int = Field(default=1, ge=1, le=20)   # preenchido pelo servidor quando offers_rotate
    offers_by_category: bool = True       # filtra a própria página de ofertas pelas categorias da busca
    offers_match_keywords: bool = True    # nas ofertas, o título precisa citar uma das palavras
    # Pula anúncios de produtos já anunciados (na fila ou enviados) nos últimos N dias. 0 = não pula.
    skip_used_days: int = Field(default=0, ge=0, le=90)

    @field_validator("offer_kinds")
    @classmethod
    def _kinds(cls, v: list[str]) -> list[str]:
        bad = [k for k in v if k not in OFFER_KINDS]
        if bad:
            raise ValueError(f"Seção de ofertas desconhecida: {', '.join(bad)}")
        return list(dict.fromkeys(v))

class SearchCreate(BaseModel):
    niche_id: int | None = None
    categories: list[OfficialCategory] = Field(default_factory=list, max_length=100)
    keywords: list[str] = Field(default_factory=list, max_length=search_service.MAX_TERMS)
    exclude_keywords: list[str] = Field(default_factory=list, max_length=50)
    filters: SearchFilters = Field(default_factory=SearchFilters)

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
    # Preço para quem não usa Pix nem saldo do Mercado Pago ("ou R$ X em outros meios").
    regular_price: float | None = Field(default=None, ge=0)
    rating: float | None = Field(default=None, ge=0, le=5)
    sold: int | None = Field(default=None, ge=0)
    free_shipping: bool = False
    ml_category_id: str | None = Field(default=None, max_length=20)
    catalog_product_id: str | None = Field(default=None, max_length=20)   # /p/MLB...: mesmo produto em várias lojas
    official_store: bool = False
    fulfillment: bool = False

class SearchResults(BaseModel):
    items: list[ResultItem] = Field(default_factory=list, max_length=600)
    error: str = Field(default="", max_length=500)

class AddProducts(BaseModel):
    listing_ids: list[int] = Field(default_factory=list, max_length=500)
    product_ids: list[int] = Field(default_factory=list, max_length=500)
    search_id: int | None = None

class RemoveProducts(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=500)


def _search_read(s: CampaignSearch) -> dict:
    return {"id": s.id, "campaign_id": s.campaign_id, "niche_id": s.niche_id, "niche_name": s.niche_name,
            "categories": jload(s.categories), "keywords": jload(s.keywords), "exclude_keywords": jload(s.exclude_keywords),
            "filters": search_service.jl(s.filters, {}), "terms": search_service.terms_of(s), "status": s.status,
            "result_count": s.result_count, "matched_count": s.matched_count, "added_count": s.added_count,
            "error": s.error, "created_at": s.created_at, "started_at": s.started_at, "finished_at": s.finished_at}


def _search(db: Session, search_id: int, user: User) -> CampaignSearch:
    s = db.get(CampaignSearch, search_id)
    if s is None:
        raise HTTPException(404, "Busca não encontrada")
    _get(db, s.campaign_id, user)
    return s


@router.get("/{campaign_id}/searches")
def list_searches(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _get(db, campaign_id, user)
    rows = db.scalars(select(CampaignSearch).where(CampaignSearch.campaign_id == campaign_id).order_by(CampaignSearch.id.desc()))
    return [_search_read(s) for s in rows]


@router.post("/{campaign_id}/searches", status_code=201)
def create_search(campaign_id: int, data: SearchCreate, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status == "cancelled":
        raise HTTPException(409, "Campanha cancelada. Duplique a campanha para buscar de novo.")
    niche = db.get(Niche, data.niche_id) if data.niche_id else None
    if data.niche_id and (niche is None or niche.owner_id != user.id):
        raise HTTPException(404, "Nicho não encontrado")
    ids = [x.id for x in data.categories]
    known = {m.id: m for m in db.scalars(select(MlCategory).where(MlCategory.id.in_(ids)))} if ids else {}
    if len(known) != len(set(ids)):
        raise HTTPException(422, "Há categorias fora do catálogo oficial. Atualize as categorias em Meu perfil.")
    keywords = clean_list(data.keywords)
    filters = _with_offers_start(db, user, data.filters)
    if not keywords and not ids and data.filters.source != "offers":
        raise HTTPException(422, "Informe pelo menos uma palavra-chave ou uma categoria.")
    s = CampaignSearch(campaign_id=c.id, niche_id=niche.id if niche else None, niche_name=niche.name if niche else "",
                       categories=json.dumps([{"id": x.id, "include_children": x.include_children, "name": known[x.id].name,
                                               "path": known[x.id].path_names} for x in data.categories], ensure_ascii=False),
                       keywords=json.dumps(keywords, ensure_ascii=False),
                       exclude_keywords=json.dumps(clean_list(data.exclude_keywords), ensure_ascii=False),
                       filters=filters.model_dump_json(), status="queued")
    db.add(s); db.commit(); db.refresh(s)
    return _search_read(s)


def _with_offers_start(db: Session, user: User, f: "SearchFilters") -> "SearchFilters":
    """Nas ofertas com "variar páginas", o servidor escolhe a página inicial (muda a cada busca)."""
    if f.source == "offers" and f.offers_rotate:
        return f.model_copy(update={"offers_start": search_service.next_offers_start(db, user.id, f.offers_pages)})
    return f


class NicheSearches(BaseModel):
    niche_ids: list[int] = Field(min_length=1, max_length=30)
    filters: SearchFilters = Field(default_factory=SearchFilters)   # o público de cada busca vem do nicho


@router.post("/{campaign_id}/searches/by-niches", status_code=201)
def create_searches_by_niche(campaign_id: int, data: NicheSearches, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Uma busca para cada nicho, cada uma com as categorias, palavras, exclusões e público do próprio nicho.
    Nicho com mais de 10 palavras vira mais de uma busca (a extensão lê até 10 termos por busca)."""
    c = _get(db, campaign_id, user)
    if c.status == "cancelled":
        raise HTTPException(409, "Campanha cancelada. Duplique a campanha para buscar de novo.")
    niches = {n.id: n for n in db.scalars(select(Niche).where(Niche.id.in_(data.niche_ids), Niche.owner_id == user.id))}
    base = _with_offers_start(db, user, data.filters)     # todos os nichos do mesmo clique começam na mesma página
    created, skipped = [], []
    for nid in dict.fromkeys(data.niche_ids):
        n = niches.get(nid)
        if n is None:
            continue
        links = list(db.scalars(select(NicheCategory).where(NicheCategory.niche_id == n.id)))
        cats = {m.id: m for m in db.scalars(select(MlCategory).where(MlCategory.id.in_([l.category_id for l in links])))} if links else {}
        categories = json.dumps([{"id": l.category_id, "include_children": l.include_children, "name": cats[l.category_id].name,
                                  "path": cats[l.category_id].path_names} for l in links if l.category_id in cats], ensure_ascii=False)
        keywords = clean_list(jload(n.include_keywords))
        if not keywords and not cats:
            skipped.append(n.name)
            continue
        filters = base.model_copy(update={"gender": n.gender if n.gender in ("male", "female") else "any",
                                          # Nas ofertas, com categorias no nicho, a própria página já vem filtrada por elas:
                                          # exigir as palavras no título cortaria quase tudo.
                                          "offers_match_keywords": not cats})
        # Nas ofertas as palavras só filtram o título: uma busca por nicho, com todas as palavras.
        size = (len(keywords) or 1) if filters.source == "offers" else search_service.MAX_TERMS
        for chunk in ([keywords[i:i + size] for i in range(0, len(keywords), size)] or [[]]):
            s = CampaignSearch(campaign_id=c.id, niche_id=n.id, niche_name=n.name, categories=categories,
                               keywords=json.dumps(chunk, ensure_ascii=False),
                               exclude_keywords=json.dumps(clean_list(jload(n.exclude_keywords)), ensure_ascii=False),
                               filters=filters.model_dump_json(), status="queued")
            db.add(s); created.append(s)
    db.commit()
    for s in created:
        db.refresh(s)
    return {"searches": [_search_read(s) for s in created], "skipped": skipped}


class SearchIds(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=200)


@router.post("/{campaign_id}/searches/remove")
def remove_searches(campaign_id: int, data: SearchIds, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Apaga buscas do histórico da campanha (e os resultados delas). Produtos já adicionados continuam na campanha."""
    _get(db, campaign_id, user)
    rows = list(db.scalars(select(CampaignSearch).where(CampaignSearch.campaign_id == campaign_id, CampaignSearch.id.in_(data.ids))))
    gone = [s for s in rows if s.status != "running"]
    ids = [s.id for s in gone]
    if ids:
        db.execute(sql_delete(CampaignSearchResult).where(CampaignSearchResult.search_id.in_(ids)))
        db.execute(update(CampaignProduct).where(CampaignProduct.search_id.in_(ids)).values(search_id=None))
        for s in gone:
            db.delete(s)
    db.commit()
    return {"deleted": len(gone), "skipped": len(data.ids) - len(gone)}


@router.post("/{campaign_id}/searches/{search_id}/repeat", status_code=201)
def repeat_search(campaign_id: int, search_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    old = _search(db, search_id, user)
    if old.campaign_id != campaign_id:
        raise HTTPException(404, "Busca não encontrada")
    s = CampaignSearch(campaign_id=old.campaign_id, niche_id=old.niche_id, niche_name=old.niche_name, categories=old.categories,
                       keywords=old.keywords, exclude_keywords=old.exclude_keywords, filters=old.filters, status="queued")
    db.add(s); db.commit(); db.refresh(s)
    return _search_read(s)


def _grouping(db: Session, s: CampaignSearch, rows: list) -> tuple[dict[int, "ranking.GroupInfo"], list["ranking.Offer"]]:
    """Agrupa os resultados nos filtros com os produtos que já estão na campanha (ids negativos)."""
    urls = search_service.in_campaign_urls(db, s.campaign_id)
    offers = [ranking.Offer(l.id, l.title, l.price, l.ml_category_id, l.catalog_product_id, l.seller, l.score,
                            eligible=True, taken=search_service.listing_in_campaign(l, urls)) for r, l in rows if r.matched]
    products = db.scalars(select(Product).join(CampaignProduct, CampaignProduct.product_id == Product.id)
                          .where(CampaignProduct.campaign_id == s.campaign_id))
    offers += [ranking.Offer(-p.id, p.title, p.price, p.ml_category_id, eligible=False, taken=True) for p in products]
    return ranking.group_offers(offers), offers


@router.get("/{campaign_id}/searches/{search_id}/results")
def search_results(campaign_id: int, search_id: int, matched: str = "true", db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Resultados da busca, com os parecidos agrupados: o melhor de cada grupo vem primeiro e os outros logo depois."""
    s = _search(db, search_id, user)
    rows = db.execute(select(CampaignSearchResult, Listing).join(Listing, Listing.id == CampaignSearchResult.listing_id)
                      .where(CampaignSearchResult.search_id == s.id)).all()
    groups, _ = _grouping(db, s, rows)
    rows.sort(key=lambda rl: (not rl[0].matched, groups[rl[1].id].order if rl[1].id in groups else 0, -rl[1].score, rl[1].id))
    if matched in ("true", "false"):
        rows = [(r, l) for r, l in rows if r.matched == (matched == "true")]
    cats = {m.id: m for m in db.scalars(select(MlCategory).where(MlCategory.id.in_({l.ml_category_id for _, l in rows if l.ml_category_id})))}
    urls = search_service.in_campaign_urls(db, s.campaign_id)
    out = []
    for r, l in rows:
        g = groups.get(l.id)
        in_campaign = search_service.listing_in_campaign(l, urls)
        out.append({"listing_id": l.id, "external_id": l.external_id, "title": l.title, "url": l.url, "image_url": l.image_url,
                    "price": l.price, "original_price": l.original_price, "price_note": l.price_note, "discount_pct": l.discount_pct,
                    "rating": l.rating, "sold": l.sold, "free_shipping": l.free_shipping, "score": l.score, "term": l.term,
                    "ml_category_id": l.ml_category_id, "category_name": cats[l.ml_category_id].name if l.ml_category_id in cats else "",
                    "category_path": cats[l.ml_category_id].path_names if l.ml_category_id in cats else "",
                    "matched": r.matched, "reason": r.reason, "in_campaign": in_campaign,
                    "official_store": bool(l.official_store), "fulfillment": bool(l.fulfillment), "seller": l.seller,
                    # Agrupamento de parecidos (só para os que passaram nos filtros).
                    "group_key": g.key if g else l.id, "group_size": g.size if g else 1, "group_best": g.best if g else True,
                    "cheapest": g.cheapest if g else False, "similar_in_campaign": bool(g and g.taken and not in_campaign)})
    return out


class BestPick(BaseModel):
    count: int = Field(default=10, ge=1, le=200)
    per_category: int = Field(default=0, ge=0, le=200)    # 0 = automático
    per_seller: int = Field(default=2, ge=0, le=200)      # 0 = sem limite


@router.post("/{campaign_id}/searches/{search_id}/best")
def best_results(campaign_id: int, search_id: int, data: BestPick, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Sugere os melhores: um por grupo de parecidos, sem repetir o que já está na campanha, variando categoria e loja.
    Só sugere: a escolha volta marcada na tela e o usuário confirma em "Adicionar à campanha"."""
    s = _search(db, search_id, user)
    if s.campaign_id != campaign_id:
        raise HTTPException(404, "Busca não encontrada")
    rows = db.execute(select(CampaignSearchResult, Listing).join(Listing, Listing.id == CampaignSearchResult.listing_id)
                      .where(CampaignSearchResult.search_id == s.id, CampaignSearchResult.matched.is_(True))).all()
    groups, offers = _grouping(db, s, rows)
    ids = ranking.pick_best(offers, groups, data.count, per_category=data.per_category, per_seller=data.per_seller)
    available = sum(1 for o in offers if o.id > 0 and groups[o.id].best and not groups[o.id].taken)
    return {"listing_ids": ids, "available": available, "groups": len({g.key for k, g in groups.items() if k > 0})}


class BestAll(BaseModel):
    per_search: int = Field(default=10, ge=1, le=100)
    search_ids: list[int] = Field(default_factory=list, max_length=200)   # vazio = todas as concluídas


@router.post("/{campaign_id}/searches/best-all")
def best_from_all(campaign_id: int, data: BestAll, db: Session = Depends(get_db), user: User = Depends(require_user)):
    """Adiciona à campanha os melhores de cada busca concluída (um por grupo de parecidos, variando categoria e loja).
    É a ação do botão "Adicionar os melhores de cada busca": o clique do usuário é a confirmação.
    Cada busca já enxerga o que as anteriores adicionaram, então o mesmo produto não entra duas vezes."""
    c = _get(db, campaign_id, user)
    if c.status == "cancelled":
        raise HTTPException(409, "Campanha cancelada.")
    stmt = select(CampaignSearch).where(CampaignSearch.campaign_id == c.id, CampaignSearch.status == "done")
    if data.search_ids:
        stmt = stmt.where(CampaignSearch.id.in_(data.search_ids))
    report, total = [], 0
    for s in db.scalars(stmt.order_by(CampaignSearch.id)).all():
        rows = db.execute(select(CampaignSearchResult, Listing).join(Listing, Listing.id == CampaignSearchResult.listing_id)
                          .where(CampaignSearchResult.search_id == s.id, CampaignSearchResult.matched.is_(True))).all()
        groups, offers = _grouping(db, s, rows)
        ids = ranking.pick_best(offers, groups, data.per_search)
        added = search_service.add_listings(db, c, ids, s.id)["added"] if ids else 0
        total += added
        report.append({"search_id": s.id, "niche_name": s.niche_name, "terms": search_service.terms_of(s), "added": added})
    db.commit()
    return {"added": total, "searches": report}


@router.get("/{campaign_id}/products")
def campaign_products(campaign_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _get(db, campaign_id, user)
    rows = db.execute(select(CampaignProduct, Product).join(Product, Product.id == CampaignProduct.product_id)
                      .where(CampaignProduct.campaign_id == campaign_id).order_by(CampaignProduct.added_at, Product.id)).all()
    cats = {m.id: m for m in db.scalars(select(MlCategory).where(MlCategory.id.in_({p.ml_category_id for _, p in rows if p.ml_category_id})))}
    return [{"product_id": p.id, "title": p.title, "image_url": p.image_url, "price": p.price, "original_price": p.original_price,
             "price_note": p.price_note, "ml_category_id": p.ml_category_id, "category_name": cats[p.ml_category_id].name if p.ml_category_id in cats else "",
             "category_path": cats[p.ml_category_id].path_names if p.ml_category_id in cats else "", "tags": jload(p.tags),
             "search_id": cp.search_id, "added_at": cp.added_at, "ready": p.status == "processed" and p.price is not None} for cp, p in rows]


@router.post("/{campaign_id}/products")
def add_campaign_products(campaign_id: int, data: AddProducts, db: Session = Depends(get_db), user: User = Depends(require_user)):
    c = _get(db, campaign_id, user)
    if c.status == "cancelled":
        raise HTTPException(409, "Campanha cancelada.")
    if data.search_id:
        _search(db, data.search_id, user)
    result = {"added": 0, "skipped": 0}
    if data.listing_ids:
        r = search_service.add_listings(db, c, data.listing_ids, data.search_id)
        result = {k: result[k] + r[k] for k in result}
    if data.product_ids:
        r = search_service.add_products(db, c, data.product_ids)
        result = {k: result[k] + r[k] for k in result}
    db.commit()
    return result


@router.post("/{campaign_id}/products/remove")
def remove_campaign_products(campaign_id: int, data: RemoveProducts, db: Session = Depends(get_db), user: User = Depends(require_user)):
    _get(db, campaign_id, user)
    n = db.query(CampaignProduct).filter(CampaignProduct.campaign_id == campaign_id, CampaignProduct.product_id.in_(data.product_ids)).delete()
    db.commit()
    return {"removed": n}


# ---------------------------------------------------------------- usado pela extensão

searches_router = APIRouter(prefix="/api/campaign-searches", tags=["campaigns"])

@searches_router.get("/due")
def due_campaign_search(db: Session = Depends(get_db), user: User = Depends(require_user)):
    s = search_service.next_due(db, user.id)
    if s is None:
        return None
    db.commit()
    return {"id": s.id, "campaign_id": s.campaign_id, "terms": search_service.pages_of(s)}

@searches_router.post("/{search_id}/results")
def receive_campaign_results(search_id: int, data: SearchResults, db: Session = Depends(get_db), user: User = Depends(require_user)):
    s = _search(db, search_id, user)
    search_service.receive(db, s, [i.model_dump() for i in data.items], data.error)
    db.commit()
    return _search_read(s)



# ---------------------------------------------------------------- conjuntos de grupos

group_sets_router = APIRouter(prefix="/api/group-sets", tags=["campaigns"])


class GroupSetWrite(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    groups: list[str] = Field(default_factory=list, max_length=200)


def _set_read(g: GroupSet) -> dict:
    return {"id": g.id, "name": g.name, "groups": jload(g.groups), "created_at": g.created_at, "updated_at": g.updated_at}


def _set_get(db: Session, set_id: int, user: User) -> GroupSet:
    g = db.get(GroupSet, set_id)
    if not g or g.owner_id != user.id:
        raise HTTPException(404, "Conjunto não encontrado")
    return g


def _set_save(db: Session, g: GroupSet, data: GroupSetWrite, user: User) -> dict:
    name = " ".join(data.name.split())
    clash = db.scalar(select(GroupSet.id).where(GroupSet.owner_id == user.id, func.lower(GroupSet.name) == name.lower(), GroupSet.id != (g.id or 0)))
    if clash:
        raise HTTPException(409, f'Já existe um conjunto chamado "{name}".')
    groups = []
    for item in data.groups:
        item = " ".join(item.split())
        if item and item not in groups:
            groups.append(item)
    if not groups:
        raise HTTPException(422, "Escolha pelo menos um grupo para o conjunto.")
    g.name, g.groups, g.owner_id = name, json.dumps(groups, ensure_ascii=False), user.id
    db.add(g); db.commit(); db.refresh(g)
    return _set_read(g)


@group_sets_router.get("")
def list_group_sets(db: Session = Depends(get_db), user: User = Depends(require_user)):
    return [_set_read(g) for g in db.scalars(select(GroupSet).where(GroupSet.owner_id == user.id).order_by(func.lower(GroupSet.name)))]


@group_sets_router.post("", status_code=201)
def create_group_set(data: GroupSetWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _set_save(db, GroupSet(), data, user)


@group_sets_router.put("/{set_id}")
def update_group_set(set_id: int, data: GroupSetWrite, db: Session = Depends(get_db), user: User = Depends(require_user)):
    return _set_save(db, _set_get(db, set_id, user), data, user)


@group_sets_router.delete("/{set_id}", status_code=204)
def delete_group_set(set_id: int, db: Session = Depends(get_db), user: User = Depends(require_user)):
    db.delete(_set_get(db, set_id, user)); db.commit()
    return Response(status_code=204)
