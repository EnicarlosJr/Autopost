"""Regras das buscas automáticas: filtros, nota, histórico de preço, agenda e criação das publicações."""
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import NamedTuple
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.publication import ACTIVE_STATUSES, Publication
from app.models.search import GroupSchedule, Listing, PricePoint, Search
from app.products.image_fetch import download_product_image
from app.products.urls import normalize_product_url
from app.publications.service import as_utc, conflict_reason, offer_text
from app.searches.ranking import offer_score

SEARCH_LEASE_MINUTES = 10   # tempo que a extensão tem para devolver o resultado de uma busca
HISTORY_DAYS = 30


def now() -> datetime:
    return datetime.now(timezone.utc)


def local_zone() -> ZoneInfo:
    return ZoneInfo(os.getenv("APP_TIMEZONE", "America/Sao_Paulo"))


def plain(text: str) -> str:
    """Minúsculas e sem acentos, para comparar palavras."""
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def lines(text: str) -> list[str]:
    seen, result = set(), []
    for raw in (text or "").replace(",", "\n").splitlines():
        item = " ".join(raw.split())
        if item and plain(item) not in seen:
            seen.add(plain(item)); result.append(item)
    return result


def search_url(term: str) -> str:
    """Página de resultados do Mercado Livre para um termo."""
    slug = re.sub(r"\s+", "-", term.strip().lower())
    return f"https://lista.mercadolivre.com.br/{quote(slug, safe='-')}"


# Área de ofertas do Mercado Livre (www.mercadolivre.com.br/ofertas). Conferido em 26/11/2026 no site:
# os tipos de promoção e o filtro de categoria combinam entre si e aceitam subcategorias (ex.: category=MLB23332).
OFFERS_BASE = "https://www.mercadolivre.com.br/ofertas"
OFFER_KINDS: dict[str, tuple[str, list[tuple[str, str]]]] = {
    "all": ("Todas as ofertas", []),
    "lightning": ("Ofertas relâmpago", [("promotion_type", "lightning")]),
    "deal_of_the_day": ("Oferta do dia", [("promotion_type", "deal_of_the_day")]),
    "unbeatable": ("Preços imbatíveis", [("container_id", "MLB1298579-1"), ("deal_ids", "MLB1298579")]),
    "outlet": ("Outlet", [("container_id", "MLB916440-2")]),
}
OFFERS_URL = f"{OFFERS_BASE}?promotion_type=deal_of_the_day"
# Palavras aceitas na busca automática (uma por linha) para cada seção.
OFFERS_WORDS = {"ofertas do dia": "deal_of_the_day", "oferta do dia": "deal_of_the_day", "ofertas": "all", "todas as ofertas": "all",
                "ofertas relampago": "lightning", "oferta relampago": "lightning", "relampago": "lightning",
                "precos imbativeis": "unbeatable", "outlet": "outlet"}
OFFERS_PAGES = 3
OFFERS_MAX_PAGE = 20          # o ML mostra até a página 20
OFFERS_MAX_URLS = 12          # teto de páginas numa busca: ~50 anúncios cada, e a extensão manda até 600
ML_HOSTS = {"www.mercadolivre.com.br", "lista.mercadolivre.com.br", "mercadolivre.com.br"}


def is_ml_url(text: str) -> bool:
    """Endereço do Mercado Livre que a extensão pode abrir (nunca outro site)."""
    try:
        parts = urlsplit((text or "").strip())
    except ValueError:
        return False
    return parts.scheme == "https" and parts.hostname in ML_HOSTS


def offer_kind_of(text: str) -> str | None:
    """Seção de ofertas citada por uma palavra da busca automática ("ofertas relâmpago" etc.)."""
    return OFFERS_WORDS.get(plain(" ".join((text or "").split())))


def is_offers(text: str) -> bool:
    t = " ".join((text or "").strip().split())
    return offer_kind_of(t) is not None or (is_ml_url(t) and urlsplit(t).path.rstrip("/") == "/ofertas")


def offer_pages(url: str = OFFERS_URL, pages: int = OFFERS_PAGES, start: int = 1, label: str = "") -> list[dict]:
    """Páginas start..start+N-1 de uma página de ofertas do ML (sem o trecho depois de #)."""
    parts = urlsplit(url if is_ml_url(url) else OFFERS_URL)
    query = [(k, v) for k, v in parse_qsl(parts.query) if k != "page"]
    label = label or "ofertas"
    first = max(1, min(OFFERS_MAX_PAGE, start))
    out = []
    for page in range(first, min(OFFERS_MAX_PAGE, first + max(1, min(5, pages)) - 1) + 1):
        q = urlencode(query + ([("page", str(page))] if page > 1 else []))
        out.append({"term": f"{label}, página {page}", "url": urlunsplit(("https", parts.hostname, parts.path or "/ofertas", q, ""))})
    return out


def offer_urls(kinds: list[str], categories: list[str], pages: int = OFFERS_PAGES, start: int = 1) -> list[dict]:
    """Páginas a ler na área de ofertas: cada seção escolhida x cada categoria (ou nenhuma) x páginas.
    Se passar de OFFERS_MAX_URLS, lê menos páginas por combinação (mínimo 1) e corta o resto."""
    kinds = [k for k in dict.fromkeys(kinds or ["all"]) if k in OFFER_KINDS] or ["all"]
    cats = [c for c in dict.fromkeys(categories) if re.fullmatch(r"MLB\d+", c or "")] or [None]
    combos = [(k, c) for k in kinds for c in cats]
    per = max(1, min(max(1, min(5, pages)), OFFERS_MAX_URLS // len(combos)))
    out = []
    for kind, cat in combos:
        query = list(OFFER_KINDS[kind][1]) + ([("category", cat)] if cat else [])
        url = OFFERS_BASE + ("?" + urlencode(query) if query else "")
        out += offer_pages(url, per, start, OFFER_KINDS[kind][0] + (f" em {cat}" if cat else ""))
    return out[:OFFERS_MAX_URLS]


def pages_for(term: str, pages: int = OFFERS_PAGES) -> list[dict]:
    """O que a extensão lê para um termo: busca por palavra, página de ofertas (com paginação) ou um link do ML."""
    term = (term or "").strip()
    if is_offers(term):
        if is_ml_url(term):
            return offer_pages(term, pages)
        return offer_urls([offer_kind_of(term) or "deal_of_the_day"], [], pages)
    if is_ml_url(term):
        parts = urlsplit(term)
        return [{"term": term[:160], "url": urlunsplit(("https", parts.hostname, parts.path, parts.query, ""))}]
    return [{"term": term, "url": search_url(term)}]


# ---------------------------------------------------------------- filtros e nota

def discount_of(price: float | None, original: float | None) -> int | None:
    if price is None or not original or original <= price:
        return None
    return int((original - price) / original * 100)


def reject_reason(search: Search, listing: Listing) -> str:
    """Motivo para o anúncio não entrar na lista da busca (vazio quando passa nos filtros)."""
    if listing.price is None:
        return "sem preço"
    if search.min_price is not None and listing.price < search.min_price:
        return "abaixo do preço mínimo"
    if search.max_price is not None and listing.price > search.max_price:
        return "acima do preço máximo"
    if search.min_discount and (listing.discount_pct or 0) < search.min_discount:
        return f"desconto menor que {search.min_discount}%"
    if search.min_rating and (listing.rating is None or listing.rating < search.min_rating):
        return f"nota menor que {search.min_rating:g}"
    if search.free_shipping_only and not listing.free_shipping:
        return "sem frete grátis"
    title = plain(listing.title)
    for word in lines(search.exclude_terms):
        if plain(word) in title:
            return f'contém "{word}"'
    return ""


def score_of(listing: Listing, history_points: int, history: "PriceHistory | None" = None) -> int:
    """Nota de 0 a 100 (regras em app.searches.ranking.offer_score)."""
    h = history or PriceHistory(listing.min_price_30d, None, history_points, 0)
    return offer_score(discount_pct=listing.discount_pct, rating=listing.rating, sold=listing.sold,
                       free_shipping=bool(listing.free_shipping), official_store=bool(listing.official_store),
                       fulfillment=bool(listing.fulfillment), price=listing.price, history_points=h.points,
                       min_30d=h.lowest, max_30d=h.highest, history_days=h.days)


# ---------------------------------------------------------------- resultados da busca

class PriceHistory(NamedTuple):
    lowest: float | None    # menor preço dos últimos 30 dias
    highest: float | None   # maior preço dos últimos 30 dias
    points: int             # leituras guardadas nos últimos 30 dias
    days: float             # dias entre a primeira e a última leitura


def _record_price(db: Session, listing: Listing) -> PriceHistory:
    """Guarda o preço (sem repetir o mesmo valor na mesma hora) e resume os últimos 30 dias."""
    if listing.price is not None:
        last = db.scalar(select(PricePoint).where(PricePoint.listing_id == listing.id)
                         .order_by(PricePoint.seen_at.desc(), PricePoint.id.desc()).limit(1))
        if last is None or last.price != listing.price or as_utc(last.seen_at) < now() - timedelta(hours=1):
            db.add(PricePoint(listing_id=listing.id, price=listing.price, seen_at=now()))
            db.flush()
    since = now() - timedelta(days=HISTORY_DAYS)
    lowest, highest, count, first, last_seen = db.execute(
        select(func.min(PricePoint.price), func.max(PricePoint.price), func.count(PricePoint.id),
               func.min(PricePoint.seen_at), func.max(PricePoint.seen_at))
        .where(PricePoint.listing_id == listing.id, PricePoint.seen_at >= since)).one()
    days = (as_utc(last_seen) - as_utc(first)).total_seconds() / 86400 if first and last_seen else 0
    return PriceHistory(lowest, highest, count, days)


def _recently_posted(db: Session, listing: Listing) -> bool:
    """O anúncio já virou publicação ativa, ou foi enviado dentro do prazo de repostagem do grupo."""
    if not listing.publication_id:
        return False
    publication = db.get(Publication, listing.publication_id)
    if publication is None or publication.status in ("cancelled", "failed"):
        return False
    if publication.status in ACTIVE_STATUSES:
        return True
    schedule = group_schedule(db, publication.group_name)
    sent = as_utc(publication.sent_at)
    return bool(sent and sent > now() - timedelta(days=schedule.repost_days))


def upsert_listing(db: Session, item: dict, *, search_id: int | None = None,
                   status: str = "new") -> tuple[Listing, bool, int] | None:
    """Grava um anúncio lido numa página de resultados (preço, histórico, nota e categoria oficial).

    Usada pelas buscas automáticas e pelas buscas feitas dentro das campanhas.
    Devolve (anúncio, criado agora?, pontos de histórico) ou None se o item for inválido.
    """
    external_id = (item.get("external_id") or "").strip().upper()
    url = (item.get("url") or "").strip()
    if not external_id or not url.startswith("https://"):
        return None
    listing = db.scalar(select(Listing).where(Listing.external_id == external_id))
    created = listing is None
    if created:
        listing = Listing(external_id=external_id, search_id=search_id, url=url, first_seen_at=now(), status=status,
                          term=(item.get("term") or "")[:160])
        db.add(listing)
    if item.get("ml_category_id"):
        listing.ml_category_id = str(item["ml_category_id"])[:20]
        listing.category_source = "preditor"
    listing.url = url
    listing.title = (item.get("title") or listing.title or "")[:500]
    listing.image_url = (item.get("image_url") or listing.image_url or "")[:2048]
    listing.seller = (item.get("seller") or "")[:160]
    listing.price = item.get("price")
    original = item.get("original_price")
    listing.original_price = original if original and listing.price is not None and original > listing.price else None
    listing.price_note = (item.get("price_note") or "")[:60]
    regular = item.get("regular_price")
    listing.regular_price = regular if regular and listing.price is not None and regular > listing.price else None
    listing.discount_pct = discount_of(listing.price, listing.original_price)
    listing.rating = item.get("rating")
    listing.sold = item.get("sold")
    listing.free_shipping = bool(item.get("free_shipping"))
    listing.official_store = bool(item.get("official_store"))
    listing.fulfillment = bool(item.get("fulfillment"))
    catalog = str(item.get("catalog_product_id") or "").strip().upper()
    if re.fullmatch(r"MLB\d+", catalog):
        listing.catalog_product_id = catalog   # produto de catálogo: lojas diferentes do mesmo produto
    listing.last_seen_at = now()
    db.flush()
    history = _record_price(db, listing)
    listing.min_price_30d = history.lowest
    listing.score = score_of(listing, history.points, history)
    return listing, created, history.points


def ingest(db: Session, search: Search, items: list[dict]) -> dict:
    """Grava os anúncios lidos na página de resultados e decide quais entram na lista."""
    counts = {"read": 0, "new": 0, "matching": 0}
    for item in items:
        saved = upsert_listing(db, item, search_id=search.id)
        if saved is None:
            continue
        listing, created, points = saved
        counts["read"] += 1
        if listing.status == "campaign":
            # Achado antes só por uma busca de campanha: passa a valer também para esta busca automática.
            listing.status = "new"
        reason = reject_reason(search, listing)
        listing.reject_reason = reason
        if created or listing.status == "new":
            listing.search_id, listing.term = search.id, (item.get("term") or "")[:160]
            listing.matches = not reason
        elif listing.status == "scheduled" and not _recently_posted(db, listing):
            # Já foi postado há mais tempo que o prazo de repostagem: volta para a lista se ainda vale a pena.
            listing.status, listing.search_id, listing.matches = "new", search.id, not reason
            listing.decided_at = None
        if created:
            counts["new"] += 1
        if listing.status == "new" and listing.matches:
            counts["matching"] += 1
    db.flush()
    return counts


# ---------------------------------------------------------------- agenda

def group_schedule(db: Session, group_name: str) -> GroupSchedule:
    schedule = db.scalar(select(GroupSchedule).where(GroupSchedule.group_name == group_name))
    return schedule or GroupSchedule(group_name=group_name, start_hour=8, end_hour=22, max_per_day=12,
                                     gap_minutes=40, repost_days=7)


def next_slots(db: Session, group_name: str, count: int, start: datetime | None = None) -> list[datetime]:
    """Próximos horários livres do grupo, respeitando janela, limite diário e intervalo."""
    schedule = group_schedule(db, group_name)
    zone = local_zone()
    gap = timedelta(minutes=max(1, schedule.gap_minutes))
    start_hour = max(0, min(23, schedule.start_hour))
    end_hour = max(start_hour + 1, min(24, schedule.end_hour))
    rows = db.execute(select(Publication.status, Publication.scheduled_at, Publication.approved_at, Publication.sent_at)
                      .where(Publication.group_name == group_name,
                             Publication.status.in_(("scheduled", "approved", "sending", "sent")),
                             func.coalesce(Publication.sent_at, Publication.scheduled_at, Publication.approved_at)
                             >= now() - timedelta(days=1))).all()
    taken = []
    for status, scheduled_at, approved_at, sent_at in rows:
        moment = sent_at if status == "sent" else (scheduled_at or approved_at)
        if moment:
            taken.append(as_utc(moment))
    per_day: dict = {}
    for moment in taken:
        day = moment.astimezone(zone).date()
        per_day[day] = per_day.get(day, 0) + 1

    candidate = max([start or now() + timedelta(minutes=2)] + [t + gap for t in taken])
    slots: list[datetime] = []
    guard = 0
    while len(slots) < count and guard < 10000:
        guard += 1
        local = candidate.astimezone(zone)
        day_start = local.replace(hour=start_hour, minute=0, second=0, microsecond=0)
        if local < day_start:
            candidate = day_start.astimezone(timezone.utc); continue
        day_end = day_start + timedelta(hours=end_hour - start_hour)
        if local >= day_end or per_day.get(local.date(), 0) >= max(1, schedule.max_per_day):
            next_day = (day_start + timedelta(days=1)).replace(hour=start_hour)
            candidate = next_day.astimezone(timezone.utc); continue
        slot = candidate.replace(second=0, microsecond=0)
        slots.append(slot)
        per_day[local.date()] = per_day.get(local.date(), 0) + 1
        candidate = slot + gap
    return slots


# ---------------------------------------------------------------- aprovar e descartar

def product_for(db: Session, listing: Listing) -> Product:
    url = normalize_product_url(listing.url)
    product = db.scalar(select(Product).where(Product.original_url == url))
    if product is None:
        product = Product(original_url=url, affiliate_url="", marketplace="Mercado Livre", status="processed")
        db.add(product); db.flush()
    product.title = listing.title or product.title
    product.price = listing.price
    product.original_price = listing.original_price
    product.price_note = listing.price_note
    product.regular_price = listing.regular_price
    product.store = product.store or "Mercado Livre"
    product.marketplace = product.marketplace or "Mercado Livre"
    product.data_source = "browser"
    product.captured_at = as_utc(listing.last_seen_at)
    product.status = "processed"
    # Categoria oficial identificada pelo preditor; o termo da busca vira tag pessoal (nunca categoria).
    if listing.ml_category_id:
        product.ml_category_id = listing.ml_category_id
    if listing.term:
        tags = json.loads(product.tags or "[]")
        if listing.term.casefold() not in {t.casefold() for t in tags}:
            product.tags = json.dumps(tags + [listing.term], ensure_ascii=False)
    if listing.image_url.startswith("https://") and not product.image_source_url:
        product.image_source_url = listing.image_url[:2048]
    if listing.image_url.startswith("https://") and not product.image_url:
        try:
            product.image_url = download_product_image(listing.image_url, product.id)
        except Exception:  # a imagem é opcional
            pass
    return product


def approve(db: Session, listings: list[Listing], *, when: datetime | None = None,
            group_override: str | None = None) -> dict:
    """Transforma anúncios em publicações aprovadas. Sem `when`, distribui nos próximos horários do grupo.

    O link de afiliado é gerado pela extensão logo antes do envio (botão Compartilhar do Mercado Livre).
    """
    done, skipped = [], []
    by_group: dict[str, list[Listing]] = {}
    for listing in listings:
        if listing.status != "new":
            skipped.append({"id": listing.id, "reason": "já decidido"}); continue
        search = db.get(Search, listing.search_id) if listing.search_id else None
        group = (group_override if group_override is not None else (search.group_name if search else "")).strip()
        if not group:
            skipped.append({"id": listing.id, "reason": "a busca não tem grupo de destino"}); continue
        by_group.setdefault(group, []).append(listing)
    for group, items in by_group.items():
        items.sort(key=lambda x: x.score, reverse=True)
        if when is not None:
            gap = timedelta(minutes=group_schedule(db, group).gap_minutes)
            slots = [as_utc(when) + gap * i for i in range(len(items))]
        else:
            slots = next_slots(db, group, len(items))
        for listing, slot in zip(items, slots):
            product = product_for(db, listing)
            if conflict_reason(db, product.id, group):
                skipped.append({"id": listing.id, "reason": "já há publicação deste produto para o grupo"})
                continue
            publication = Publication(product_id=product.id, group_name=group, message=offer_text(db, product),
                                      approved_at=now(), scheduled_at=slot)
            publication.status = "scheduled" if slot > now() else "approved"
            db.add(publication); db.flush()
            listing.status, listing.product_id, listing.publication_id = "scheduled", product.id, publication.id
            listing.decided_at = now()
            done.append({"id": listing.id, "publication_id": publication.id, "scheduled_at": slot.isoformat()})
    return {"scheduled": done, "skipped": skipped}


def restore(listings: list[Listing]) -> int:
    """Descartados voltam para "Para aprovar"."""
    count = 0
    for listing in listings:
        if listing.status == "discarded":
            listing.status, listing.decided_at = "new", None
            count += 1
    return count


def discard(listings: list[Listing]) -> int:
    count = 0
    for listing in listings:
        if listing.status == "new":
            listing.status, listing.decided_at = "discarded", now()
            count += 1
    return count


def auto_approve(db: Session, search: Search) -> dict:
    """Modo automático: aprova os melhores anúncios novos da busca, até o limite por execução."""
    if search.mode != "auto" or not search.group_name.strip():
        return {"scheduled": [], "skipped": []}
    best = list(db.scalars(select(Listing).where(Listing.search_id == search.id, Listing.status == "new",
                                                 Listing.matches.is_(True))
                           .order_by(Listing.score.desc(), Listing.id).limit(max(1, search.max_per_run))))
    return approve(db, best)
