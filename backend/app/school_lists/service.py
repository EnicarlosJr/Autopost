"""Regras das listas escolares: dados das opções, totais e a página de orçamento para os pais.

As funções de cima são puras (sem banco) para serem testadas sozinhas.
"""
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.school import SchoolItemSearch, SchoolList, SchoolListItem, SchoolListOption, SchoolVisitor
from app.models.search import Listing
from app.products.urls import normalize_product_url
from app.school_lists import matching

SECTIONS = ("coletivo", "individual")
DEFAULT_LABELS = ("Econômica", "Equilibrada", "Premium")
CLAIM_MINUTES = 10
SEARCH_LEASE_MINUTES = 10
ERROR_BACKOFF = timedelta(hours=2)          # conferência que falhou só volta depois de 2 h
UNAVAILABLE = "indisponível"
_CATALOG = re.compile(r"/p/(MLB\d+)", re.I)
_LISTING = re.compile(r"MLB-?U?(\d{6,})", re.I)
_AFFILIATE = re.compile(r"^https://(meli\.la|(www\.)?mercadolivre\.com(\.br)?/sec)/", re.I)


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def school_slug(school_list) -> str:
    return slugify(school_list.school) or "escola"


def grade_slug(school_list) -> str:
    return slugify(f"{school_list.grade} {school_list.year}") or str(school_list.id)


def turmas_of(school_list) -> list[str]:
    try:
        value = json.loads(school_list.turmas or "[]")
    except ValueError:
        value = []
    return [str(t).strip()[:60] for t in value if str(t).strip()]


def clean_turmas(values: list[str]) -> str:
    seen, out = set(), []
    for value in values:
        name = " ".join(str(value).split())[:60]
        if name and name.lower() not in seen:
            seen.add(name.lower()); out.append(name)
    return json.dumps(out[:30], ensure_ascii=False)


def public_base() -> str:
    return os.getenv("APP_PUBLIC_URL", "http://localhost:8000").rstrip("/")


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def catalog_id(url: str) -> str:
    """Código do produto de catálogo do Mercado Livre (/p/MLB…): é o mesmo para todos os vendedores."""
    match = _CATALOG.search(url or "")
    return match.group(1).upper() if match else ""


def is_affiliate_link(url: str) -> bool:
    return bool(_AFFILIATE.match((url or "").strip()))


def buy_link(product: Product) -> str:
    """Link que vai para os pais: o de afiliado quando existe e abre o produto, senão o link comum."""
    ok = is_affiliate_link(product.affiliate_url) and product.affiliate_ok is not False
    return product.affiliate_url if ok else product.original_url


def is_unavailable(product: Product) -> bool:
    return (product.availability or "").startswith(UNAVAILABLE)


def effective_price(option: dict) -> float | None:
    """Preço que todos pagam: o do cartão quando o preço em destaque depende de Pix ou Mercado Pago."""
    price, regular = option.get("price"), option.get("regular_price")
    if price is None:
        return None
    return regular if regular and regular > price else price


def payment_kind(note: str) -> str:
    text = (note or "").lower()
    return "mp" if "mercado pago" in text else ("pix" if "pix" in text else "other")


def condition_label(option: dict) -> str:
    """Condição do preço menor ("no Pix", "com Mercado Pago"), quando ele é diferente do preço normal."""
    if effective_price(option) == option.get("price"):
        return ""
    conditions = [c for c in (option.get("price_conditions") or "").split(" · ") if c]
    return option.get("price_note") or (conditions[0] if conditions else "com desconto no pagamento")


def parse_lines(text: str) -> list[dict]:
    """Itens colados como texto, um por linha. "2 - Cola branca 90 g" ou "Cola branca 90 g | 2 unidades".

    O que vem depois de "|" (ou o número do começo) vira o "como a escola pede".
    """
    items = []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("•*-–·").strip()
        if not line:
            continue
        requested = ""
        if "|" in line:
            line, requested = (part.strip() for part in line.split("|", 1))
        else:
            match = re.match(r"^(\d{1,4})\s*(?:[-–x)]|un\.?|unid\.?)?\s+(.+)$", line, re.I)
            if match:
                requested, line = match.group(1), match.group(2).strip()
        if line:
            items.append({"name": line[:300], "requested": requested[:120]})
    return items


def option_price(option: dict) -> float | None:
    price = None if option.get("unavailable") else effective_price(option)
    return None if price is None else round(price * max(1, option.get("buy_qty") or 1), 2)


def totals(items: list[dict]) -> dict:
    """Total da lista em cada faixa (opção mais barata, a do meio/padrão e a mais cara) por seção."""
    out = {s: {"min": 0.0, "max": 0.0, "items": 0, "priced": 0} for s in SECTIONS}
    for item in items:
        bucket = out.setdefault(item["section"], {"min": 0.0, "max": 0.0, "items": 0, "priced": 0})
        bucket["items"] += 1
        prices = [p for p in (option_price(o) for o in item["options"]) if p is not None]
        if prices:
            bucket["priced"] += 1
            bucket["min"] = round(bucket["min"] + min(prices), 2)
            bucket["max"] = round(bucket["max"] + max(prices), 2)
    return out


# ---------------------------------------------------------------- banco

def option_read(option: SchoolListOption, product: Product) -> dict:
    return {
        "slot": option.slot, "label": option.label or DEFAULT_LABELS[option.slot], "buy_qty": option.buy_qty,
        "watch": option.watch, "last_error": option.last_error or "",
        "product_id": product.id, "title": product.title, "status": product.status,
        "price": product.price, "original_price": product.original_price, "price_note": product.price_note or "",
        "regular_price": product.regular_price, "price_conditions": product.price_conditions or "",
        "unavailable": is_unavailable(product), "affiliate_ok": product.affiliate_ok,
        "store": product.store, "image_url": product.image_url, "image_source_url": product.image_source_url or "",
        "original_url": product.original_url, "affiliate_url": product.affiliate_url,
        "has_affiliate_link": is_affiliate_link(product.affiliate_url), "catalog_id": catalog_id(product.original_url),
        "captured_at": aware(product.captured_at).isoformat() if product.captured_at else None,
    }


def list_detail(db: Session, school_list: SchoolList) -> dict:
    items = list(db.scalars(select(SchoolListItem).where(SchoolListItem.list_id == school_list.id)
                            .order_by(SchoolListItem.section, SchoolListItem.position, SchoolListItem.id)))
    ids = [i.id for i in items]
    rows = db.execute(select(SchoolListOption, Product).join(Product, Product.id == SchoolListOption.product_id)
                      .where(SchoolListOption.item_id.in_(ids)).order_by(SchoolListOption.slot)).all() if ids else []
    by_item: dict[int, list[dict]] = {}
    for option, product in rows:
        by_item.setdefault(option.item_id, []).append(option_read(option, product))
    searches = latest_searches(db, ids)
    out_items = []
    for i in items:
        options = by_item.get(i.id, [])
        out_items.append({"id": i.id, "section": i.section, "name": i.name, "requested": i.requested, "color": i.color,
                          "position": i.position, "options": options, "search": search_view(searches.get(i.id), i, options)})
    captured = [o["captured_at"] for i in out_items for o in i["options"] if o["captured_at"]]
    return {"id": school_list.id, "school": school_list.school, "grade": school_list.grade, "year": school_list.year,
            "notes": school_list.notes, "refresh_hours": school_list.refresh_hours, "items": out_items,
            "public": bool(school_list.public), "turmas": turmas_of(school_list), "contact": school_list.contact or "",
            "public_url": f"{public_base()}/escolas/{school_slug(school_list)}",
            "page_url": f"{public_base()}/escolas/{school_slug(school_list)}/{grade_slug(school_list)}",
            "totals": totals(out_items), "oldest_capture": min(captured) if captured else None,
            "missing_links": sum(1 for i in out_items for o in i["options"] if not o["has_affiliate_link"]),
            "broken_links": sum(1 for i in out_items for o in i["options"] if o["has_affiliate_link"] and o["affiliate_ok"] is False),
            "unavailable": sum(1 for i in out_items for o in i["options"] if o["unavailable"]),
            "suggestions": sum(1 for i in out_items if i["search"] and (any(i["search"]["slots"].values()) or i["search"]["cheaper"])),
            "empty_items": sum(1 for i in out_items if not i["options"]),
            "visitors": db.scalar(select(func.count()).select_from(SchoolVisitor).where(SchoolVisitor.list_id == school_list.id)) or 0}


def next_refresh(db: Session, owner_id: int) -> Product | None:
    """O próximo produto das listas deste perfil com preço vencido, reservado por alguns minutos."""
    moment = now()
    candidates = db.execute(
        select(SchoolListOption, Product, SchoolList.refresh_hours)
        .join(SchoolListItem, SchoolListItem.id == SchoolListOption.item_id)
        .join(SchoolList, SchoolList.id == SchoolListItem.list_id)
        .join(Product, Product.id == SchoolListOption.product_id)
        .where(SchoolList.owner_id == owner_id, SchoolListOption.watch.is_(True),
               or_(SchoolListOption.refresh_claimed_at.is_(None),
                   SchoolListOption.refresh_claimed_at < moment - timedelta(minutes=CLAIM_MINUTES)))
        .order_by(Product.captured_at.asc().nullsfirst(), Product.id)).all()
    for option, product, hours in candidates:
        captured = aware(product.captured_at)
        if captured is None or captured < moment - timedelta(hours=max(1, hours or 12)):
            for other in db.scalars(select(SchoolListOption).where(SchoolListOption.product_id == product.id)):
                other.refresh_claimed_at = moment
            db.commit()
            return product
    return None


def finish_refresh(db: Session, product_id: int, error: str = "", link_ok: bool | None = None,
                   unavailable: bool = False) -> None:
    """Fim da conferência de um produto. Nada sai da lista: com erro, o último preço continua e a próxima
    tentativa espera 2 h; indisponível some da página dos pais e dispara a busca de um substituto."""
    moment = now()
    product = db.get(Product, product_id)
    options = list(db.scalars(select(SchoolListOption).where(SchoolListOption.product_id == product_id)))
    for option in options:
        # A reserva vence CLAIM_MINUTES depois da data gravada: com erro, empurra para daqui a 2 h.
        option.refresh_claimed_at = moment + ERROR_BACKOFF - timedelta(minutes=CLAIM_MINUTES) if error else None
        option.last_error = error[:500]
    if product is not None:
        if link_ok is not None:
            product.affiliate_ok, product.affiliate_checked_at = link_ok, moment
        if unavailable:
            product.availability = UNAVAILABLE
            for option in options:
                item = db.get(SchoolListItem, option.item_id)
                school_list = db.get(SchoolList, item.list_id) if item else None
                if item and school_list and not _searched_recently(db, item.id, timedelta(hours=24), "indisponivel"):
                    queue_search(db, item, school_list.owner_id, reason="indisponivel")
    db.commit()


# ---------------------------------------------------------------- busca de equivalentes

def set_option(db: Session, item: SchoolListItem, slot: int, product: Product, label: str = "",
               buy_qty: int | None = None, watch: bool = True) -> SchoolListOption:
    option = db.scalar(select(SchoolListOption).where(SchoolListOption.item_id == item.id, SchoolListOption.slot == slot))
    if option is None:
        option = SchoolListOption(item_id=item.id, slot=slot, product_id=product.id)
        db.add(option)
    if buy_qty is None:      # mesmo produto em outra opção: mesma quantidade a comprar
        buy_qty = db.scalar(select(SchoolListOption.buy_qty).where(SchoolListOption.item_id == item.id,
                                                                   SchoolListOption.slot != slot).limit(1)) or 1
    option.product_id, option.label = product.id, (label or "").strip() or DEFAULT_LABELS[slot]
    option.buy_qty, option.watch, option.last_error, option.refresh_claimed_at = buy_qty, watch, "", None
    db.flush()
    return option


def _searched_recently(db: Session, item_id: int, window: timedelta, reason: str) -> bool:
    return db.scalar(select(func.count()).select_from(SchoolItemSearch).where(
        SchoolItemSearch.item_id == item_id, SchoolItemSearch.reason == reason,
        SchoolItemSearch.created_at > now() - window)) > 0


def queue_search(db: Session, item: SchoolListItem, owner_id: int, reference_product_id: int | None = None,
                 reason: str = "manual") -> SchoolItemSearch:
    """Põe a busca do item na fila da extensão (uma por vez por item)."""
    active = db.scalar(select(SchoolItemSearch).where(SchoolItemSearch.item_id == item.id,
                                                      SchoolItemSearch.status.in_(("queued", "running")))
                       .order_by(SchoolItemSearch.id.desc()).limit(1))
    if active is not None:
        if active.status == "queued" and reference_product_id:
            active.reference_product_id = reference_product_id
        if active.status == "queued" and reason == "indisponivel":
            active.reason = reason
        return active
    search = SchoolItemSearch(owner_id=owner_id, item_id=item.id, reference_product_id=reference_product_id,
                              reason=reason, status="queued", created_at=now())
    db.add(search); db.flush()
    return search


def _reference(db: Session, search: SchoolItemSearch, item: SchoolListItem) -> Product | None:
    product = db.get(Product, search.reference_product_id) if search.reference_product_id else None
    if product is not None and product.title:
        return product
    for candidate in db.scalars(select(Product).join(SchoolListOption, SchoolListOption.product_id == Product.id)
                                .where(SchoolListOption.item_id == item.id).order_by(SchoolListOption.slot)):
        if candidate.title:
            return candidate
    return product


def next_search(db: Session, owner_id: int) -> tuple[SchoolItemSearch, list[dict]] | None:
    """Para a extensão: a busca mais antiga na fila (ou presa há mais de 10 min), com as páginas a ler."""
    moment = now()
    stale = moment - timedelta(minutes=SEARCH_LEASE_MINUTES)
    rows = db.scalars(select(SchoolItemSearch).where(
        SchoolItemSearch.owner_id == owner_id,
        (SchoolItemSearch.status == "queued") | ((SchoolItemSearch.status == "running") & (SchoolItemSearch.started_at < stale)))
        .order_by(SchoolItemSearch.created_at, SchoolItemSearch.id))
    for search in rows:
        item = db.get(SchoolListItem, search.item_id)
        if item is None:
            search.status, search.error = "failed", "Item excluído."
            continue
        reference = _reference(db, search, item)
        # Produto acabou de entrar e ainda não foi lido: espera a leitura (até 3 min) para usar o nome dele.
        if reference is not None and not reference.title and aware(search.created_at) > moment - timedelta(minutes=3):
            continue
        terms = matching.build_terms(item.name, item.color, reference.title if reference else "")
        if not terms:
            search.status, search.error, search.finished_at = "failed", "Item sem nome para buscar.", moment
            continue
        search.terms = json.dumps(terms, ensure_ascii=False)
        search.status, search.started_at = "running", moment
        db.commit()
        return search, terms
    db.commit()
    return None


def _snapshot(listing: Listing) -> dict:
    return {"listing_id": listing.id, "external_id": listing.external_id, "url": normalize_product_url(listing.url),
            "link": listing.url, "title": listing.title, "price": listing.price, "original_price": listing.original_price,
            "price_note": listing.price_note or "", "regular_price": listing.regular_price,
            "image_url": listing.image_url, "seller": listing.seller,
            "rating": listing.rating, "sold": listing.sold, "official_store": bool(listing.official_store),
            "fulfillment": bool(listing.fulfillment), "free_shipping": bool(listing.free_shipping),
            "catalog_product_id": listing.catalog_product_id}


def _dismissed(item: SchoolListItem) -> set[str]:
    try:
        return set(json.loads(item.dismissed or "[]"))
    except ValueError:
        return set()


def receive_search(db: Session, search: SchoolItemSearch, items: list[dict], error: str = "") -> SchoolItemSearch:
    """Resultados lidos pela extensão: confere cada anúncio contra o item e escolhe as sugestões."""
    from app.campaigns.search_service import suspicious_term
    from app.searches.service import upsert_listing
    item = db.get(SchoolListItem, search.item_id)
    moment = now()
    if item is None:
        search.status, search.error, search.finished_at = "failed", "Item excluído.", moment
        db.commit()
        return search
    seen, candidates = set(), []
    dismissed = _dismissed(item)
    for raw in items:
        saved = upsert_listing(db, raw, status="campaign")       # fora da tela Achados
        if saved is None or saved[0].id in seen:
            continue
        seen.add(saved[0].id)
        if saved[0].external_id not in dismissed:
            candidates.append(_snapshot(saved[0]))
    rows = db.execute(select(SchoolListOption, Product).join(Product, Product.id == SchoolListOption.product_id)
                      .where(SchoolListOption.item_id == item.id)).all()
    existing = [{"slot": o.slot, "price": effective_price({"price": p.price, "regular_price": p.regular_price}),
                 "url": p.original_url, "catalog_id": catalog_id(p.original_url)} for o, p in rows if not is_unavailable(p)]
    empty = [slot for slot in (0, 1, 2) if slot not in {e["slot"] for e in existing}]
    reference = _reference(db, search, item)
    ref_title = reference.title if reference else ""
    result = matching.pick(matching.make_reference(item.name, item.color, ref_title), candidates, existing, empty,
                           reference_catalog=catalog_id(reference.original_url) if reference else "",
                           suspicious=suspicious_term)
    search.suggestions = json.dumps(result, ensure_ascii=False, default=str)
    search.result_count, search.error, search.finished_at = len(seen), error[:500], moment
    found = any(result["slots"].values()) or result["cheaper"]
    search.status = "failed" if error and not seen else ("done" if found else "no_results")
    db.commit()
    return search


def latest_searches(db: Session, item_ids: list[int]) -> dict[int, SchoolItemSearch]:
    out: dict[int, SchoolItemSearch] = {}
    if item_ids:
        for row in db.scalars(select(SchoolItemSearch).where(SchoolItemSearch.item_id.in_(item_ids))
                              .order_by(SchoolItemSearch.id.desc())):
            out.setdefault(row.item_id, row)
    return out


def search_view(search: SchoolItemSearch | None, item: SchoolListItem, options: list[dict]) -> dict | None:
    """Sugestões ainda válidas: sem as descartadas e sem as que já viraram opção."""
    if search is None:
        return None
    try:
        data = json.loads(search.suggestions or "{}")
    except ValueError:
        data = {}
    dismissed = _dismissed(item)
    in_use = {normalize_product_url(o["original_url"]) for o in options}
    keep = lambda rows: [r for r in rows or [] if r.get("external_id") not in dismissed and r.get("url") not in in_use]
    filled = {o["slot"] for o in options if not o["unavailable"]}
    slots = {k: keep(v) for k, v in (data.get("slots") or {}).items() if int(k) not in filled}
    return {"id": search.id, "status": search.status, "reason": search.reason, "error": search.error,
            "created_at": aware(search.created_at).isoformat() if search.created_at else None,
            "finished_at": aware(search.finished_at).isoformat() if search.finished_at else None,
            "result_count": search.result_count, "accepted": data.get("accepted", 0), "rejected": data.get("rejected", 0),
            "reasons": data.get("reasons", {}), "slots": slots, "cheaper": keep(data.get("cheaper"))}


def use_suggestion(db: Session, item: SchoolListItem, listing_id: int, slot: int) -> Product:
    """"Usar": o anúncio sugerido vira a opção escolhida (o link de afiliado é gerado em seguida pelo painel)."""
    from app.searches.service import product_for
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise LookupError("Sugestão não encontrada. Busque de novo.")
    product = product_for(db, listing)
    product.availability = ""
    set_option(db, item, slot, product)
    db.commit()
    return product


def dismiss_suggestion(db: Session, item: SchoolListItem, external_id: str) -> None:
    dismissed = _dismissed(item)
    dismissed.add(external_id.strip().upper()[:40])
    item.dismissed = json.dumps(sorted(dismissed)[-500:])
    db.commit()


# ---------------------------------------------------------------- página dos pais

def page_data(detail: dict) -> dict:
    """Só o que a página pública precisa (sem ids internos nem endereços locais)."""
    items = []
    for item in detail["items"]:
        options = [{"label": o["label"], "title": o["title"], "price": effective_price(o),
                    "original_price": o["original_price"] if (o["original_price"] or 0) > (effective_price(o) or 0) else None,
                    "pay_price": o["price"] if condition_label(o) else None, "pay_note": condition_label(o),
                    # "mp": só com saldo no Mercado Pago (a página pergunta); "pix": vale para todos que pagam no Pix.
                    "pay_kind": payment_kind(condition_label(o)) if condition_label(o) else "",
                    "qty": o["buy_qty"], "image": o["image_source_url"], "url": buy_link_from(o)}
                   for o in item["options"] if o["price"] is not None and not o.get("unavailable")]
        # Item sem opção com preço também aparece (fora do total), para a lista não ficar incompleta.
        items.append({"section": item["section"], "name": item["name"], "requested": item["requested"],
                      "color": item["color"], "options": options, "default": max(0, min(1, len(options) - 1))})
    return {"school": detail["school"], "grade": detail["grade"], "year": detail["year"], "items": items}


def buy_link_from(option: dict) -> str:
    ok = option["has_affiliate_link"] and option.get("affiliate_ok") is not False
    return option["affiliate_url"] if ok else option["original_url"]


def render_page(detail: dict, disclosure: str = "#publi", checked_at: datetime | None = None,
                greeting: str = "", switch_url: str = "") -> str:
    """Página única (HTML + CSS + JS, sem dependências) para publicar no seu site ou landing."""
    data = page_data(detail)
    stamp = (checked_at or now()).astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    # JSON dentro de <script>: "</" quebrado para não fechar a tag antes da hora.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"Material escolar {data['year']} – {data['grade']}".strip(" –"))
    school = html.escape(data["school"])
    return (PAGE_TEMPLATE.replace("{{TITLE}}", title).replace("{{SCHOOL}}", school)
            .replace("{{DISCLOSURE}}", html.escape(disclosure or "#publi")).replace("{{STAMP}}", html.escape(stamp))
            .replace("{{GREETING}}", _greeting(greeting, switch_url)).replace("{{DATA}}", payload))


def _greeting(greeting: str, switch_url: str) -> str:
    if not greeting:
        return ""
    link = f' · <a href="{html.escape(switch_url)}">trocar aluno</a>' if switch_url else ""
    return f'<p class="hello">{html.escape(greeting)}{link}</p>'


def render_landing(school: str, options: list[tuple[str, str]], action: str, contact: str = "", error: str = "",
                   student: str = "", disclosure: str = "#publi") -> str:
    """Entrada da escola: o responsável informa o nome do aluno e a turma e vai direto para a lista da série."""
    opts = "".join(f'<option value="{html.escape(v)}">{html.escape(label)}</option>' for v, label in options)
    contact_line = (f" Para pedir a exclusão dos dados, fale com {html.escape(contact)}." if contact
                    else " Você pode pedir a exclusão dos dados a qualquer momento a quem enviou este link.")
    return (LANDING_TEMPLATE.replace("{{SCHOOL}}", html.escape(school or "Material escolar"))
            .replace("{{ACTION}}", html.escape(action)).replace("{{OPTIONS}}", opts)
            .replace("{{ERROR}}", f'<p class="err" role="alert">{html.escape(error)}</p>' if error else "")
            .replace("{{STUDENT}}", html.escape(student)).replace("{{CONTACT}}", contact_line)
            .replace("{{DISCLOSURE}}", html.escape(disclosure or "#publi")))

LANDING_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<title>Material escolar · {{SCHOOL}}</title>
<style>
:root{--bg:#FBF8F1;--ink:#1C2340;--muted:#5F6478;--line:#ECE6D8;--line2:#D9D2C2;--navy:#24357A;--navy2:#1A275C;--sun:#FFC83D}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
.band{background:var(--navy);height:150px}
main{max-width:460px;margin:-118px auto 0;padding:0 16px 40px}
.top{display:flex;justify-content:flex-end;margin-bottom:14px}
.publi{font-size:12px;font-weight:700;color:#fff;border:1px solid rgba(255,255,255,.35);background:rgba(255,255,255,.08);border-radius:6px;padding:3px 8px}
.card{position:relative;background:#fff;border:1px solid var(--line);border-radius:20px;padding:22px 20px 22px 34px;display:flex;flex-direction:column;gap:16px;
  box-shadow:0 1px 2px rgba(28,35,64,.06),0 14px 34px rgba(28,35,64,.10)}
.card::before{content:"";position:absolute;left:20px;top:0;bottom:0;width:2px;background:#F2B1A6}
h1{display:inline;font-size:26px;line-height:1.3;margin:0;letter-spacing:-.015em;
  background:linear-gradient(transparent 58%,var(--sun) 58%,var(--sun) 90%,transparent 90%);-webkit-box-decoration-break:clone;box-decoration-break:clone}
.intro{margin:0;color:var(--muted)}
label{display:flex;flex-direction:column;gap:6px;font-size:14px;font-weight:700}
input[type=text],select{font:inherit;font-size:16px;min-height:50px;padding:10px 12px;border:1px solid var(--line2);border-radius:12px;background:#fff;color:var(--ink);width:100%}
input[type=text]:focus,select:focus{outline:3px solid var(--sun);outline-offset:1px;border-color:var(--navy)}
.consent{flex-direction:row;align-items:flex-start;gap:10px;font-weight:400;font-size:13px;color:var(--muted);line-height:1.45}
.consent input{width:22px;height:22px;margin:0;accent-color:var(--navy);flex:none}
button{font:inherit;font-size:16px;font-weight:800;min-height:52px;border-radius:12px;border:0;background:var(--navy);color:#fff;cursor:pointer;box-shadow:0 4px 12px rgba(36,53,122,.25)}
button:hover{background:var(--navy2)}button:focus-visible{outline:3px solid var(--sun);outline-offset:2px}
.err{color:#B3261E;background:#FCEEEE;border-radius:10px;padding:10px 12px;margin:0;font-size:14px}
@media (min-width:700px){.band{height:190px}main{margin-top:-150px}h1{font-size:32px}.card{padding:30px 30px 30px 50px}.card::before{left:30px}}
</style></head>
<body><div class="band"></div><main>
<div class="top"><span class="publi">{{DISCLOSURE}}</span></div>
<form class="card" method="post" action="{{ACTION}}">
<div><h1>{{SCHOOL}}</h1></div>
<p class="intro">Informe o nome do aluno e a turma para ver a lista de material da série, com os preços de hoje.</p>
{{ERROR}}
<label>Nome do aluno<input type="text" name="student_name" required maxlength="120" autocomplete="off" value="{{STUDENT}}"></label>
<label>Turma<select name="turma" required><option value="">Escolha a turma</option>{{OPTIONS}}</select></label>
<label class="consent"><input type="checkbox" name="consent" value="1" required>
<span>Sou responsável por este aluno e autorizo guardar o nome e a turma informados para montar a lista e controlar os acessos desta página. Nada mais é coletado.{{CONTACT}}</span></label>
<button type="submit">Ver a lista</button>
</form>
</main></body></html>
"""


PAGE_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{TITLE}}</title>
<style>
:root{--bg:#FBF8F1;--ink:#1C2340;--muted:#5F6478;--line:#ECE6D8;--line2:#D9D2C2;--navy:#24357A;--navy2:#1A275C;--sky:#EEF2FF;--sun:#FFC83D;--sun2:#FFF3CC;--coral:#D9472F;--coral2:#FDE7E2;--mint:#1E8A5A;--mint2:#E3F4EA;--on:#C9D1F0;--shadow:0 1px 2px rgba(28,35,64,.06),0 6px 18px rgba(28,35,64,.05)}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:92px}
a{color:var(--navy)}button{font:inherit;color:inherit}
header{background:var(--navy);color:#fff}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:54px}
.school{font-weight:800;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;gap:8px}
.school::before{content:"";flex:none;width:10px;height:10px;border-radius:3px;background:var(--sun)}
.publi{flex:none;font-size:12px;font-weight:700;color:#fff;border:1px solid rgba(255,255,255,.35);background:rgba(255,255,255,.08);border-radius:6px;padding:3px 8px}
.hero{position:relative;margin-top:16px;padding:18px 18px 20px 34px;background-color:#fff;border:1px solid var(--line);border-radius:18px;box-shadow:var(--shadow);
  background-image:repeating-linear-gradient(to bottom,transparent 0,transparent 27px,#E7ECF7 27px,#E7ECF7 28px)}
.hero::before{content:"";position:absolute;left:20px;top:0;bottom:0;width:2px;background:#F2B1A6}
.hello{font-size:13px;color:var(--muted);margin:0 0 8px}.hello a{font-weight:600}
h1{display:inline;font-size:25px;line-height:1.3;margin:0;letter-spacing:-.015em;color:var(--ink);
  background:linear-gradient(transparent 58%,var(--sun) 58%,var(--sun) 90%,transparent 90%);-webkit-box-decoration-break:clone;box-decoration-break:clone}
.lead{margin:10px 0 0;color:var(--muted);max-width:620px}
.tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0}
.tabs:empty{display:none}
.tab{text-align:left;padding:11px 12px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer;display:flex;justify-content:space-between;align-items:baseline;gap:6px;min-width:0}
.tab span{font-weight:800;font-size:15px}.tab small{font-size:13px;color:var(--muted);white-space:nowrap;font-weight:600}.tab em{display:none;font-style:normal;font-weight:400}
.tab[aria-selected=true]{background:var(--navy);border-color:var(--navy);color:#fff;box-shadow:0 4px 12px rgba(36,53,122,.25)}.tab[aria-selected=true] small{color:var(--sun)}
.layout{display:grid;gap:16px;padding:4px 0 24px}
.list{display:flex;flex-direction:column;gap:12px;min-width:0}
.card{background:#fff;border:1px solid var(--line);border-radius:18px;padding:14px;display:grid;gap:12px;align-items:start;box-shadow:var(--shadow);
  grid-template-columns:72px minmax(0,1fr);grid-template-areas:"img info" "opts opts" "foot foot" "acts acts"}
.card.done{border-color:#A9D9C0;box-shadow:inset 4px 0 0 var(--mint),var(--shadow)}
.img{grid-area:img;width:72px;height:72px;border-radius:12px;border:1px solid var(--line);background:#fff;object-fit:contain}
.ph{display:flex;align-items:center;justify-content:center;color:#8E9BD1;background:var(--sky);border-color:#DDE4FB}
.info{grid-area:info;min-width:0}
.name{font-size:16px;font-weight:800;margin:0;line-height:1.3}
.meta{margin:3px 0 0;font-size:13px;color:var(--muted)}
.prod{margin:4px 0 0;font-size:13px;color:#3C4260;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.opts{grid-area:opts;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin:0 -14px;padding:2px 14px}
.opts::-webkit-scrollbar{display:none}
.opt{flex:0 0 auto;min-width:108px;display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:8px 12px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer}
.opt span{font-size:12px;color:var(--muted)}.opt b{font-size:15px}
.opt[aria-pressed=true]{border-color:var(--navy);background:var(--sun2);box-shadow:inset 0 0 0 1px var(--navy)}.opt[aria-pressed=true] span{color:var(--navy);font-weight:700}
.foot{grid-area:foot;display:flex;align-items:center;justify-content:space-between;gap:12px}
.qty{display:flex;align-items:center;border:1px solid var(--line2);border-radius:12px;background:#fff}
.qty button{width:44px;height:44px;border:0;background:none;font-size:20px;cursor:pointer;color:var(--navy);font-weight:700}
.qty span{min-width:24px;text-align:center;font-weight:800}
.price{display:flex;flex-direction:column;align-items:flex-end;text-align:right;gap:2px}
.price b{font-size:21px;line-height:1.15;letter-spacing:-.01em}.was{font-size:12px;color:var(--muted)}.was s{margin-left:6px}
.ask{background:var(--sun2);border:1px solid #F3DC8B;border-radius:18px;padding:14px;display:flex;flex-direction:column;gap:10px}
.ask p{margin:0;font-size:14px}.ask .seg{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.ask .seg button{min-height:44px;border-radius:12px;border:1px solid var(--line2);background:#fff;font-weight:700;cursor:pointer}
.ask .seg button[aria-pressed=true]{background:var(--navy);border-color:var(--navy);color:#fff}
.alt{font-size:12px;color:var(--muted)}
.each{font-size:12px;color:var(--muted)}.pay{font-size:12px;font-weight:700;color:var(--mint);background:var(--mint2);border-radius:6px;padding:1px 6px}.pct{background:var(--coral2);color:var(--coral);border-radius:6px;padding:1px 6px;font-weight:800}
.acts{grid-area:acts;display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}
.buy{grid-column:1/-1;display:flex;align-items:center;justify-content:center;gap:8px;min-height:48px;border-radius:12px;background:var(--navy);color:#fff;font-weight:800;text-decoration:none;box-shadow:0 3px 10px rgba(36,53,122,.22)}
.buy::after{content:"→";font-weight:700}.buy:hover{background:var(--navy2)}
.tog{font-weight:700;font-size:14px;min-height:42px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer;padding:0 14px}
.tog[aria-pressed=true]{background:var(--mint2);border-color:var(--mint);color:var(--mint)}
.link{font-size:14px;font-weight:600;background:none;border:0;color:var(--muted);text-decoration:underline;cursor:pointer;padding:0 6px;min-height:42px}
.card.off{grid-template-areas:"img info" "undo undo";background:#FDFBF6;box-shadow:none}.card.off .img,.card.off .info{opacity:.5}
.undo{grid-area:undo;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;color:var(--muted);border-top:1px dashed var(--line2);padding-top:4px}
.card.nop{grid-template-areas:"img info"}
.empty{background:#fff;border:1px dashed var(--line2);border-radius:18px;padding:28px 20px;text-align:center;display:flex;flex-direction:column;gap:4px}
.sum{background:var(--navy);color:#fff;border-radius:18px;padding:20px;display:flex;flex-direction:column;gap:14px;box-shadow:0 10px 28px rgba(36,53,122,.25)}
.label{font-size:13px;color:var(--muted)}.sum .label{color:var(--on)}
.total{font-size:36px;font-weight:800;line-height:1.05;letter-spacing:-.02em}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:14px}
.bar{height:8px;background:rgba(255,255,255,.18);border-radius:999px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;width:0;background:var(--sun);border-radius:999px;transition:width .25s}
.split{display:flex;flex-direction:column;gap:6px;border-top:1px solid rgba(255,255,255,.18);padding-top:12px}.split:empty{display:none}.split .all{font-weight:800;color:var(--sun)}
.btn2{font-size:14px;font-weight:700;min-height:44px;border-radius:12px;border:1px solid rgba(255,255,255,.4);background:transparent;color:#fff;cursor:pointer}.btn2:hover{background:rgba(255,255,255,.08)}
.small{font-size:12px;line-height:1.5;color:var(--on);margin:0}
.mbar{transition:transform .2s}.mbar.hide{transform:translateY(110%)}
.mbar{position:fixed;left:0;right:0;bottom:0;z-index:10;background:var(--navy);color:#fff;box-shadow:0 -6px 20px rgba(28,35,64,.18);padding:10px 16px calc(12px + env(safe-area-inset-bottom));border-radius:18px 18px 0 0}
.mbar .in{max-width:1120px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px}
.mbar small{display:block;font-size:12px;color:var(--on)}.mbar b{font-size:23px;letter-spacing:-.01em}
.mbar .cart{text-align:right;font-size:13px;width:132px;color:var(--on)}
button:focus-visible,a:focus-visible{outline:3px solid var(--sun);outline-offset:2px}
@media (min-width:900px){
  body{padding-bottom:0}.mbar{display:none}
  .hero{margin-top:28px;padding:26px 28px 28px 52px}.hero::before{left:32px}h1{font-size:34px}
  .tabs{position:static;display:flex;padding:20px 0 12px}.tab{min-width:230px;flex-direction:column;align-items:flex-start;gap:1px}.tab em{display:inline}.tab small{font-size:12px}
  .layout{grid-template-columns:minmax(0,1fr) 320px;align-items:start}aside{position:sticky;top:16px}
  .card{grid-template-columns:96px minmax(0,1fr) 250px;grid-template-areas:"img info foot" "img opts acts";padding:16px 18px;gap:12px 20px}
  .img{width:96px;height:96px}.opts{margin:0;padding:0;flex-wrap:wrap;overflow:visible}.opt{min-width:0;padding:7px 11px}
  .card.off{grid-template-areas:"img info undo"}.undo{border:0;padding:0;flex-direction:column;align-items:flex-end}
  .card.nop{grid-template-areas:"img info info"}
}
@media print{
  body{padding:0;background:#fff}header,.tabs,.buy,.tog,.link,.qty button,.btn2,.mbar{display:none}
  .hero,.card{box-shadow:none}.layout{grid-template-columns:1fr}.card{break-inside:avoid}aside{position:static}
  .sum{background:#fff;color:var(--ink);border:1px solid var(--line);box-shadow:none}.sum .label,.small{color:var(--muted)}.split .all{color:var(--ink)}
}
</style>
</head>
<body>
<header><div class="wrap top"><span class="school">{{SCHOOL}}</span><span class="publi">{{DISCLOSURE}}</span></div></header>
<main class="wrap">
<div class="hero">{{GREETING}}<h1>{{TITLE}}</h1>
<p class="lead">Marque o que você já tem em casa, escolha uma opção de cada item e compre no Mercado Livre.</p></div>
<nav class="tabs" role="tablist" id="tabs"></nav>
<div class="layout"><section class="list" id="list" aria-live="polite"></section>
<aside><div class="sum" id="sum">
<div><div class="label" id="sumTitle"></div><div class="total" id="total"></div><div class="label" id="count" style="margin-top:6px"></div></div>
<div><div class="row"><span class="label">No carrinho</span><b id="cartLabel"></b></div><div class="bar"><i id="cartBar"></i></div></div>
<div class="split" id="split"></div>
<button class="btn2" onclick="window.print()">Imprimir ou salvar em PDF</button>
<p class="small">Preços conferidos em {{STAMP}}. O total usa o preço no Pix quando há promoção no Pix, e o preço com saldo no Mercado Pago só se você disse que tem saldo. O preço e o estoque finais são os do Mercado Livre na hora da compra. O Mercado Livre não deixa colocar vários produtos no carrinho de uma vez: abra cada item e marque "Pus no carrinho".</p>
</div></aside></div>
</main>
<div class="mbar"><div class="in"><div><small id="mbLabel"></small><b id="mbTotal"></b></div>
<div class="cart"><span id="mbCart"></span><div class="bar"><i id="mbBar"></i></div></div></div></div>
<script>
const D = {{DATA}};
const KEY = 'orcamento:' + D.school + ':' + D.grade + ':' + D.year;
const brl = v => v.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
let S = {};
try { S = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { S = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} };
// Saldo no Mercado Pago: algumas promoções valem só para quem paga com saldo. A resposta fica neste navegador.
let MP = '';
try { MP = localStorage.getItem('orcamento:mercado-pago') || ''; } catch (e) { MP = ''; }
const hasMpPromo = D.items.some(it => it.options.some(o => o.pay_kind === 'mp'));
// Preço que esta pessoa paga: Pix vale para todos; saldo no Mercado Pago só se ela disse que tem.
const unit = o => (o.pay_kind === 'pix' || (o.pay_kind === 'mp' && MP === 'yes')) && o.pay_price ? o.pay_price : o.price;
function payLine(o, qty) {
  if (!o.pay_price) return '';
  if (o.pay_kind === 'pix') return `<span class="pay">no Pix</span><span class="alt">${brl(o.price * qty)} no cartão</span>`;
  if (o.pay_kind === 'mp' && MP === 'yes') return `<span class="pay">com saldo no Mercado Pago</span><span class="alt">sem saldo: ${brl(o.price * qty)}</span>`;
  if (o.pay_kind === 'mp') return `<span class="alt">com saldo no Mercado Pago: ${brl(o.pay_price * qty)}</span>`;
  return `<span class="alt">${brl(o.pay_price * qty)} ${esc(o.pay_note)}</span>`;
}
function askCard() {
  if (!hasMpPromo) return '';
  return `<div class="ask"><p><b>Você tem saldo no Mercado Pago?</b> Algumas promoções desta lista valem só para quem paga com saldo no Mercado Pago. Sem saldo, mostramos o preço no Pix ou o normal.</p>
    <div class="seg"><button data-mp="yes" aria-pressed="${MP === 'yes'}">Tenho saldo</button><button data-mp="no" aria-pressed="${MP === 'no'}">Não tenho</button></div></div>`;
}
const st = i => {
  const it = D.items[i], s = S[i] || (S[i] = {inc: true, opt: it.default, qty: (it.options[it.default] || {qty: 1}).qty, cart: false});
  if (!it.options[s.opt]) s.opt = 0;
  return s;
};
const sections = [...new Set(D.items.map(i => i.section))];
let tab = sections.includes('coletivo') ? 'coletivo' : (sections[0] || '');
const LABEL = {coletivo: ['Coletivo', 'vai para a escola'], individual: ['Individual', 'fica com a criança']};
const nameOf = s => (LABEL[s] || [s || ''])[0];
const PH = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h16M6 16l10-10 3 3-10 10H6z"/></svg>';
function sum(section) {
  const r = {total: 0, n: 0, c: 0, priced: 0, all: 0};
  D.items.forEach((it, i) => {
    if (it.section !== section) return;
    r.all++;
    if (!it.options.length) return;
    r.priced++;
    const s = st(i);
    if (s.inc) { r.total += unit(it.options[s.opt]) * s.qty; r.n++; if (s.cart) r.c++; }
  });
  return r;
}
function card(it, i) {
  const meta = [it.requested ? 'Pedido: ' + esc(it.requested) : '', it.color ? 'Cor: ' + esc(it.color) : ''].filter(Boolean).join(' · ');
  const head = title => `<div class="info"><h3 class="name">${esc(it.name)}</h3>${meta ? `<p class="meta">${meta}</p>` : ''}${title}</div>`;
  if (!it.options.length) return `<article class="card nop"><span class="img ph">${PH}</span>${head('<p class="meta">Ainda sem preço conferido; fica fora do total.</p>')}</article>`;
  const s = st(i), o = it.options[s.opt];
  const img = o.image ? `<img class="img" src="${esc(o.image)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : `<span class="img ph">${PH}</span>`;
  const info = head(`<p class="prod">${esc(o.title)}</p>`);
  if (!s.inc) return `<article class="card off">${img}${info}<div class="undo"><span>Você já tem este item.</span><button class="link" data-i="${i}" data-act="have">Desfazer</button></div></article>`;
  const price = unit(o);
  const pct = o.original_price && o.original_price > price ? Math.round((1 - price / o.original_price) * 100) : 0;
  const opts = it.options.length > 1 ? `<div class="opts" role="group" aria-label="Opções">${it.options.map((x, j) =>
    `<button class="opt" aria-pressed="${j === s.opt}" data-i="${i}" data-opt="${j}"><span>${esc(x.label || 'Opção ' + (j + 1))}</span><b>${brl(unit(x))}</b></button>`).join('')}</div>` : '';
  const each = s.qty > 1 ? brl(price) + ' cada' : '';
  return `<article class="card${s.cart ? ' done' : ''}">${img}${info}${opts}
    <div class="foot"><div class="qty"><button data-i="${i}" data-act="minus" aria-label="Diminuir quantidade">−</button><span>${s.qty}</span><button data-i="${i}" data-act="plus" aria-label="Aumentar quantidade">+</button></div>
    <div class="price">${pct >= 5 ? `<span class="was"><span class="pct">-${pct}%</span><s>${brl(o.original_price * s.qty)}</s></span>` : ''}<b>${brl(price * s.qty)}</b>${payLine(o, s.qty)}${each ? `<span class="each">${each}</span>` : ''}</div></div>
    <div class="acts"><a class="buy" href="${esc(o.url)}" target="_blank" rel="noopener sponsored">Comprar no Mercado Livre</a>
    <button class="tog" data-i="${i}" data-act="cart" aria-pressed="${s.cart}">${s.cart ? '✓ No carrinho' : 'Pus no carrinho'}</button>
    <button class="link" data-i="${i}" data-act="have">Já tenho</button></div></article>`;
}
function render() {
  const sums = Object.fromEntries(sections.map(s => [s, sum(s)]));
  document.getElementById('tabs').innerHTML = sections.length < 2 ? '' : sections.map(s =>
    `<button class="tab" role="tab" aria-selected="${s === tab}" data-tab="${s}"><span>${esc(nameOf(s))}</span><small><em>${esc((LABEL[s] || ['', ''])[1])} · </em>${brl(sums[s].total)}</small></button>`).join('');
  const cards = D.items.map((it, i) => it.section === tab ? card(it, i) : '').join('');
  document.getElementById('list').innerHTML = cards ? askCard() + cards : ''
    || '<div class="empty"><b>A lista ainda está sendo preparada.</b><span class="label">Os preços estão sendo conferidos. Volte daqui a pouco.</span></div>';
  const t = sums[tab] || {total: 0, n: 0, c: 0, priced: 0, all: 0};
  const label = ['Seu orçamento', nameOf(tab)].filter(Boolean).join(' · ');
  const width = (t.n ? Math.round(t.c / t.n * 100) : 0) + '%';
  document.getElementById('sumTitle').textContent = label;
  document.getElementById('total').textContent = brl(t.total);
  document.getElementById('count').textContent = t.n + ' de ' + t.all + ' itens no orçamento';
  document.getElementById('cartLabel').textContent = t.c + ' de ' + t.n;
  document.getElementById('cartBar').style.width = width;
  document.getElementById('mbLabel').textContent = label;
  document.getElementById('mbTotal').textContent = brl(t.total);
  document.getElementById('mbCart').textContent = t.c + ' de ' + t.n + ' no carrinho';
  document.getElementById('mbBar').style.width = width;
  const all = sections.reduce((a, s) => a + sums[s].total, 0);
  document.getElementById('split').innerHTML = sections.length < 2 ? '' : sections.map(s =>
    `<div class="row"><span>${esc(nameOf(s))}</span><span>${brl(sums[s].total)}</span></div>`).join('')
    + `<div class="row all"><span>Total da série</span><span>${brl(all)}</span></div>`;
}
document.addEventListener('click', e => {
  const t = e.target.closest('[data-tab],[data-opt],[data-act],[data-mp]');
  if (!t) return;
  if (t.dataset.mp) { MP = t.dataset.mp; try { localStorage.setItem('orcamento:mercado-pago', MP); } catch (e) {} render(); return; }
  if (t.dataset.tab) { tab = t.dataset.tab; render(); window.scrollTo({top: document.getElementById('tabs').offsetTop - 4}); return; }
  const i = Number(t.dataset.i), s = st(i), act = t.dataset.act;
  if (t.dataset.opt) { s.opt = Number(t.dataset.opt); s.qty = D.items[i].options[s.opt].qty; }
  if (act === 'minus') s.qty = Math.max(1, s.qty - 1);
  if (act === 'plus') s.qty = s.qty + 1;
  if (act === 'cart') s.cart = !s.cart;
  if (act === 'have') { s.inc = !s.inc; if (!s.inc) s.cart = false; }
  save(); render();
});
render();
// No celular, a barra de baixo some quando o resumo completo já está na tela.
if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(e =>
  document.querySelector('.mbar').classList.toggle('hide', e.isIntersecting))).observe(document.getElementById('sum'));
</script>
</body>
</html>
"""
