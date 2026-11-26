"""Busca de produtos dentro da campanha.

O Mercado Livre não libera a busca da API e o site ignora a categoria pedida na URL. Por isso:
1. a extensão busca cada palavra-chave no site, no Chrome do usuário;
2. classifica cada resultado com o preditor oficial (domain_discovery) e devolve a categoria;
3. aqui o resultado é filtrado pelas categorias da busca (com ou sem subcategorias), pelas palavras
   excluídas e pelos filtros de preço, desconto, nota e frete.
"""
import json
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.catalog.service import plain, subtree_ids
from app.models.campaign import Campaign, CampaignProduct, CampaignSearch, CampaignSearchResult
from app.models.catalog import MlCategory
from app.models.product import Product
from app.models.search import Listing
from app.products.urls import normalize_product_url
from app.publications.service import record_event
from app.models.publication import ACTIVE_STATUSES, Publication
from app.searches.service import OFFER_KINDS, OFFERS_MAX_PAGE, OFFERS_PAGES, offer_urls, pages_for, product_for, upsert_listing

LEASE_MINUTES = 10
MAX_TERMS = 10


def now() -> datetime:
    return datetime.now(timezone.utc)


def jl(text: str | None, default):
    try:
        value = json.loads(text or "")
        return value if isinstance(value, type(default)) else default
    except ValueError:
        return default


# Palavras que indicam o público no título ou na categoria (comparadas sem acento e sem maiúsculas).
GENDER_WORDS = {
    "male": {"masculino", "masculina", "masculinos", "masculinas", "masc", "homem", "homens", "men", "mens",
             "menino", "meninos", "rapaz", "garoto", "garotos", "cavalheiro"},
    "female": {"feminino", "feminina", "femininos", "femininas", "fem", "mulher", "mulheres", "women", "womens", "woman",
               "menina", "meninas", "garota", "garotas", "dama", "damas", "ladies", "lady", "gestante"},
    "unisex": {"unissex", "unisex"},
}
GENDER_TERM = {"male": "masculino", "female": "feminino"}
GENDER_LABEL = {"male": "masculino", "female": "feminino"}

# Termos comuns em anúncios de baixa confiabilidade (imitação, folheado, "primeira linha"...).
SUSPICIOUS_TERMS = ["banhado", "banhada", "folheado", "folheada", "replica", "réplica", "imitacao", "imitação",
                    "primeira linha", "1a linha", "1ª linha", "similar", "inspirado", "inspirada", "inspired",
                    "tipo original", "aaa", "importado china", "bijuteria", "bijuterias", "generico", "genérico"]


def suspicious_term(title: str) -> str:
    words = " " + re.sub(r"[^\w]+", " ", plain(title)) + " "
    for term in SUSPICIOUS_TERMS:
        if f" {plain(term)} " in words:
            return term
    return ""


def genders_in(text: str) -> set[str]:
    """Públicos citados no texto: {"male"}, {"female"}, {"unisex"} ou combinações."""
    words = set(plain(text).replace("'", " ").replace("-", " ").replace("/", " ").split())
    return {g for g, vocab in GENDER_WORDS.items() if words & vocab}


def from_offers(search: CampaignSearch) -> bool:
    return jl(search.filters, {}).get("source") == "offers"


def offer_kinds(search: CampaignSearch) -> list[str]:
    """Seções da área de ofertas escolhidas; buscas antigas (sem a escolha) leem a Oferta do dia."""
    kinds = [k for k in jl(search.filters, {}).get("offer_kinds") or [] if k in OFFER_KINDS]
    return kinds or ["deal_of_the_day"]


def offer_categories(search: CampaignSearch) -> list[str]:
    """Categorias usadas no filtro da própria página de ofertas (até 6; o resto filtra depois, pela árvore)."""
    if jl(search.filters, {}).get("offers_by_category") is False:
        return []
    return [c["id"] for c in jl(search.categories, []) if isinstance(c, dict) and c.get("id")][:6]


def pages_of(search: CampaignSearch) -> list[dict]:
    """Páginas que a extensão lê: as buscas por palavra ou as páginas da área de ofertas."""
    if from_offers(search):
        f = jl(search.filters, {})
        return offer_urls(offer_kinds(search), offer_categories(search),
                          int(f.get("offers_pages") or OFFERS_PAGES), int(f.get("offers_start") or 1))
    return [page for term in terms_of(search) for page in pages_for(term)]


def next_offers_start(db: Session, owner_id: int, pages: int) -> int:
    """Página inicial que muda a cada busca de ofertas: 1, depois 1+N, 1+2N... até a 20 e volta.
    Assim, buscas seguidas trazem ofertas diferentes em vez das mesmas da primeira página."""
    since = now() - timedelta(hours=24)
    done = db.scalar(select(func.count(CampaignSearch.id)).join(Campaign, Campaign.id == CampaignSearch.campaign_id)
                     .where(Campaign.owner_id == owner_id, CampaignSearch.created_at >= since,
                            CampaignSearch.filters.like('%"source":%"offers"%'))) or 0
    span = max(1, OFFERS_MAX_PAGE // max(1, pages))
    return 1 + (done % span) * max(1, pages)


def terms_of(search: CampaignSearch) -> list[str]:
    """Palavras-chave da busca; sem palavras, usa o nome de cada categoria escolhida.
    Com público definido, acrescenta "masculino" ou "feminino" a quem ainda não cita o público.
    Nas Ofertas do dia, as palavras não são buscadas: filtram o título (ver reject_reason)."""
    if from_offers(search):
        f = jl(search.filters, {})
        pages, start = int(f.get("offers_pages") or OFFERS_PAGES), int(f.get("offers_start") or 1)
        names = " + ".join(OFFER_KINDS[k][0] for k in offer_kinds(search))
        where = f", {len(offer_categories(search))} categoria(s)" if offer_categories(search) else ""
        span = f"página {start}" if pages == 1 else f"páginas {start} a {start + pages - 1}"
        if not f.get("offer_kinds") and start == 1:
            return [f"Ofertas do dia ({pages} página{'s' if pages > 1 else ''})"]     # buscas antigas
        return [f"{names} ({span}{where})"]
    words = [w for w in jl(search.keywords, []) if isinstance(w, str) and w.strip()]
    if not words:
        words = [c.get("name") or c.get("id") for c in jl(search.categories, []) if isinstance(c, dict)]
    gender = jl(search.filters, {}).get("gender")
    seen, out = set(), []
    for w in words:
        w = w.strip()
        if gender in GENDER_TERM and not genders_in(w):
            w = f"{w} {GENDER_TERM[gender]}"
        if plain(w) not in seen:
            seen.add(plain(w)); out.append(w)
    return out[:MAX_TERMS]


def allowed_categories(db: Session, search: CampaignSearch) -> set[str]:
    allowed: set[str] = set()
    for c in jl(search.categories, []):
        if isinstance(c, dict) and c.get("id"):
            allowed |= subtree_ids(db, c["id"]) if c.get("include_children", True) else {c["id"]}
    return allowed


def recently_used(db: Session, days: int) -> set[str]:
    """Links dos produtos já anunciados (enviados ou na fila) nos últimos N dias."""
    if days <= 0:
        return set()
    since = now() - timedelta(days=days)
    rows = db.scalars(select(Product.original_url).join(Publication, Publication.product_id == Product.id)
                      .where((Publication.status.in_(ACTIVE_STATUSES)) |
                             ((Publication.status == "sent") & (Publication.sent_at >= since)))).all()
    return set(rows)


def reject_reason(db: Session, search: CampaignSearch, listing: Listing, allowed: set[str], used: set[str] | None = None) -> str:
    filters = jl(search.filters, {})
    if listing.price is None:
        return "sem preço"
    if used and normalize_product_url(listing.url) in used:
        return f"já anunciado nos últimos {int(filters.get('skip_used_days') or 0)} dias"
    if allowed:
        if not listing.ml_category_id:
            if not filters.get("allow_uncategorized"):
                return "categoria não identificada"
        elif listing.ml_category_id not in allowed:
            cat = db.get(MlCategory, listing.ml_category_id)
            return f"fora das categorias ({cat.name if cat else listing.ml_category_id})"
    title = plain(listing.title)
    if from_offers(search) and filters.get("offers_match_keywords", True):
        # Ofertas: as palavras da busca precisam aparecer no título (basta uma delas).
        # Na busca por nicho com categorias, as categorias já filtram e as palavras não cortam nada.
        wanted = [w for w in jl(search.keywords, []) if isinstance(w, str) and plain(w).strip()]
        words = set(re.findall(r"\w+", title))
        if wanted and not any(set(re.findall(r"\w+", plain(w))) <= words for w in wanted):
            return "não cita as palavras-chave"
    for word in jl(search.exclude_keywords, []):
        if plain(word) and plain(word) in title:
            return f'contém "{word}"'
    if filters.get("min_price") is not None and listing.price < float(filters["min_price"]):
        return "abaixo do preço mínimo"
    if filters.get("max_price") is not None and listing.price > float(filters["max_price"]):
        return "acima do preço máximo"
    if filters.get("min_discount") and (listing.discount_pct or 0) < int(filters["min_discount"]):
        return f"desconto menor que {filters['min_discount']}%"
    if filters.get("min_rating") and (listing.rating is None or listing.rating < float(filters["min_rating"])):
        return f"nota menor que {filters['min_rating']}"
    if filters.get("free_shipping") and not listing.free_shipping:
        return "sem frete grátis"
    if filters.get("exclude_suspicious"):
        term = suspicious_term(listing.title)
        if term:
            return f'baixa confiabilidade ("{term}")'
    if filters.get("min_sold") and (listing.sold or 0) < int(filters["min_sold"]):
        return f"menos de {filters['min_sold']} vendidos"
    if filters.get("official_or_full") and not (listing.official_store or listing.fulfillment):
        return "não é loja oficial nem Full"
    gender = filters.get("gender")
    if gender in GENDER_TERM:
        cat = db.get(MlCategory, listing.ml_category_id) if listing.ml_category_id else None
        found = genders_in(f"{listing.title} {cat.path_names if cat else ''}")
        other = "female" if gender == "male" else "male"
        if other in found and gender not in found and "unisex" not in found:
            return f"para o público {GENDER_LABEL[other]}"
        if filters.get("gender_strict") and not found & {gender, "unisex"}:
            return f"não diz que é {GENDER_LABEL[gender]} ou unissex"
    return ""


def next_due(db: Session, owner_id: int) -> CampaignSearch | None:
    """A busca de campanha mais antiga na fila (ou presa há mais de 10 min) é reservada para a extensão."""
    stale = now() - timedelta(minutes=LEASE_MINUTES)
    search = db.scalar(select(CampaignSearch).join(Campaign, Campaign.id == CampaignSearch.campaign_id)
                       .where(Campaign.owner_id == owner_id,
                              (CampaignSearch.status == "queued") | ((CampaignSearch.status == "running") & (CampaignSearch.started_at < stale)))
                       .order_by(CampaignSearch.created_at, CampaignSearch.id).limit(1))
    if search:
        search.status, search.started_at = "running", now()
    return search


def receive(db: Session, search: CampaignSearch, items: list[dict], error: str = "") -> CampaignSearch:
    allowed = allowed_categories(db, search)
    used = recently_used(db, int(jl(search.filters, {}).get("skip_used_days") or 0))
    seen: set[int] = set()
    matched = 0
    for item in items:
        saved = upsert_listing(db, item, status="campaign")
        if saved is None:
            continue
        listing = saved[0]
        if listing.id in seen:
            continue                      # o mesmo anúncio em duas palavras-chave conta uma vez
        seen.add(listing.id)
        reason = reject_reason(db, search, listing, allowed, used)
        matched += not reason
        row = db.get(CampaignSearchResult, (search.id, listing.id))
        if row is None:
            db.add(CampaignSearchResult(search_id=search.id, listing_id=listing.id, matched=not reason, reason=reason))
        else:
            row.matched, row.reason = not reason, reason
    search.result_count, search.matched_count = len(seen), matched
    search.finished_at = now()
    search.error = error[:500]
    search.status = "failed" if error and not seen else ("no_results" if not matched else "done")
    record_event(db, "extensao", "campaigns.search", None, search.status,
                 f"Busca #{search.id} da campanha #{search.campaign_id}: {len(seen)} resultado(s), {matched} dentro dos filtros."
                 + (f" Erro: {error}" if error else ""))
    db.flush()
    return search


def campaign_product_ids(db: Session, campaign_id: int) -> list[int]:
    return list(db.scalars(select(CampaignProduct.product_id).where(CampaignProduct.campaign_id == campaign_id)
                           .order_by(CampaignProduct.added_at, CampaignProduct.product_id)))


def add_listings(db: Session, c: Campaign, listing_ids: list[int], search_id: int | None) -> dict:
    added = skipped = 0
    for listing in db.scalars(select(Listing).where(Listing.id.in_(listing_ids))):
        product = product_for(db, listing)
        db.flush()
        if db.get(CampaignProduct, (c.id, product.id)):
            skipped += 1; continue
        db.add(CampaignProduct(campaign_id=c.id, product_id=product.id, search_id=search_id)); added += 1
    if search_id and added:
        s = db.get(CampaignSearch, search_id)
        if s:
            s.added_count += added
    db.flush()
    return {"added": added, "skipped": skipped}


def add_products(db: Session, c: Campaign, product_ids: list[int]) -> dict:
    added = skipped = 0
    for pid in db.scalars(select(Product.id).where(Product.id.in_(product_ids))):
        if db.get(CampaignProduct, (c.id, pid)):
            skipped += 1; continue
        db.add(CampaignProduct(campaign_id=c.id, product_id=pid)); added += 1
    db.flush()
    return {"added": added, "skipped": skipped}


def in_campaign_urls(db: Session, campaign_id: int) -> set[str]:
    return set(db.scalars(select(Product.original_url).join(CampaignProduct, CampaignProduct.product_id == Product.id)
                          .where(CampaignProduct.campaign_id == campaign_id)))


def listing_in_campaign(listing: Listing, urls: set[str]) -> bool:
    return normalize_product_url(listing.url) in urls
