"""Planejamento e controle das campanhas.

Uma campanha confirmada vira publicações agendadas comuns (com campaign_id). O envio usa a mesma
fila e a mesma extensão das publicações avulsas; pausar, retomar e cancelar agem sobre essas publicações.
"""
import json
import math
import random
import unicodedata
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.campaign import Campaign
from app.models.catalog import MlCategory
from app.models.product import Product
from app.models.publication import Publication
from app.models.search import GroupSchedule
from app.publications.service import as_utc, conflict_reason, now, offer_text, record_event
from app.searches.service import local_zone
from app.catalog.service import subtree_ids

MIN_SEND_SECONDS = 20          # trava da extensão entre duas mensagens quaisquer
UNSENT = ("scheduled", "approved", "paused", "awaiting_approval", "pending")   # ainda não saíram
DONE = ("sent", "sending", "failed")
MAX_MESSAGES = 500


def jload(text: str | None) -> list:
    try:
        value = json.loads(text or "[]")
        return value if isinstance(value, list) else []
    except ValueError:
        return []


def key(text: str) -> str:
    """Comparação sem acento e sem diferença de maiúsculas."""
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def tags_of(product: Product) -> list[str]:
    return [t for t in jload(product.tags) if isinstance(t, str) and t.strip()]


def clean_list(values) -> list[str]:
    seen, out = set(), []
    for value in values or []:
        text = " ".join(str(value).split())[:60]
        if text and key(text) not in seen:
            seen.add(key(text)); out.append(text)
    return out


# ---------------------------------------------------------------- produtos

def discount(product: Product) -> int:
    if product.price is None or not product.original_price or product.original_price <= product.price:
        return 0
    return int((product.original_price - product.price) / product.original_price * 100)


def matches(product: Product, c: Campaign) -> bool:
    category = key(product.category)
    tags = {key(t) for t in tags_of(product)}
    categories = {key(x) for x in jload(c.categories)}
    if categories and category not in categories and not (c.include_uncategorized and not category):
        return False
    if category and category in {key(x) for x in jload(c.exclude_categories)}:
        return False
    wanted = {key(x) for x in jload(c.tags)}
    if wanted:
        if c.tag_mode == "all" and not wanted <= tags:
            return False
        if c.tag_mode != "all" and not wanted & tags:
            return False
    if tags & {key(x) for x in jload(c.exclude_tags)}:
        return False
    return discount(product) >= (c.min_discount or 0)


def candidates(db: Session, c: Campaign) -> list[Product]:
    """Produtos prontos que entram na campanha, do melhor desconto para o pior."""
    stmt = select(Product).where(Product.status == "processed", Product.price.is_not(None), Product.title != "")
    chosen = []
    if c.id:
        from app.models.campaign import CampaignProduct
        chosen = list(db.scalars(select(CampaignProduct.product_id).where(CampaignProduct.campaign_id == c.id)
                                 .order_by(CampaignProduct.added_at, CampaignProduct.product_id)))
    chosen = chosen or [int(x) for x in jload(c.product_ids) if str(x).isdigit()]
    if chosen:
        rows = {p.id: p for p in db.scalars(stmt.where(Product.id.in_(chosen)))}
        return [rows[i] for i in chosen if i in rows]
    rows = [p for p in db.scalars(stmt) if matches(p, c)]
    rows.sort(key=lambda p: (-discount(p), -(as_utc(p.created_at) or now()).timestamp()))
    return rows


# ---------------------------------------------------------------- ordem dos envios

def category_bucket(db: Session, c: Campaign, product: Product, cache: dict) -> str:
    """Grupo de categoria do produto para intercalar os envios: a categoria oficial escolhida na campanha
    que contém o produto; sem ela, a categoria raiz do Mercado Livre; sem categoria oficial, a categoria antiga ou a 1ª tag."""
    if product.ml_category_id:
        if product.ml_category_id not in cache:
            row = db.get(MlCategory, product.ml_category_id)
            cache[product.ml_category_id] = row.path_ids.split("/") if row and row.path_ids else [product.ml_category_id]
        path = cache[product.ml_category_id]
        chosen = [x.get("id") for x in jload(c.ml_categories) if isinstance(x, dict)]
        for cat_id in reversed(path):                      # a escolha mais específica da campanha
            if cat_id in chosen:
                return cat_id
        return path[0]
    return key(product.category) or key((tags_of(product) or [""])[0]) or "sem categoria"


def mix_categories(db: Session, c: Campaign, products: list[Product]) -> list[Product]:
    """Intercala as categorias na ordem de envio, proporcionalmente ao tamanho de cada uma
    (ex.: 6 calçados e 3 ferramentas viram C F C C F C C F C), sem repetir a mesma categoria em sequência
    quando há outra disponível. Dentro de cada categoria, os maiores descontos saem primeiro."""
    if len(products) < 3:
        return products
    cache: dict = {}
    buckets: dict[str, list[Product]] = {}
    for p in products:
        buckets.setdefault(category_bucket(db, c, p, cache), []).append(p)
    if len(buckets) < 2:
        return products
    for items in buckets.values():
        items.sort(key=lambda p: -discount(p))             # sort estável: empate mantém a ordem anterior
    # Posição ideal de cada item = (i + 0.5) / tamanho da categoria; categorias maiores desempatam primeiro.
    slots = sorted(((i + 0.5) / len(items), -len(items), name, i)
                   for name, items in buckets.items() for i in range(len(items)))
    queue = [(name, buckets[name][i]) for _, _, name, i in slots]
    out: list[Product] = []
    last = None
    while queue:
        pick = next((k for k, (name, _) in enumerate(queue) if name != last), 0)
        last, product = queue.pop(pick)
        out.append(product)
    return out


# ---------------------------------------------------------------- grupos e distribuição

def group_registry(db: Session) -> dict[str, GroupSchedule]:
    return {g.group_name: g for g in db.scalars(select(GroupSchedule))}


def group_targets(db: Session, c: Campaign) -> list[dict]:
    """Grupos da campanha com limite e categorias (da campanha, ou do cadastro do grupo na estratégia por categoria)."""
    registry = group_registry(db)
    out = []
    for item in jload(c.groups):
        if not isinstance(item, dict):
            continue
        name = " ".join(str(item.get("group", "")).split())
        if not name or (name in registry and not registry[name].active):
            continue
        cats = item.get("categories") or []
        official = item.get("ml_categories") or []
        if c.strategy == "category":
            cats = jload(registry[name].categories) if name in registry else []
            official = jload(getattr(registry[name], "ml_categories", "[]")) if name in registry else []
        out.append({"group": name, "limit": max(0, int(item.get("limit") or 0)), "categories": clean_list(cats),
                    "ml_categories": [o for o in official if isinstance(o, dict) and o.get("id")],
                    "allowed": official_ids(db, official)})
    return out


def official_ids(db: Session, picks: list) -> set[str]:
    """IDs aceitos por uma lista de categorias oficiais (com ou sem as subcategorias)."""
    allowed: set[str] = set()
    for pick in picks or []:
        if isinstance(pick, dict) and pick.get("id"):
            allowed |= subtree_ids(db, pick["id"]) if pick.get("include_children", True) else {pick["id"]}
    return allowed


def _fits_group(product: Product, target: dict) -> bool:
    """Categoria oficial do produto dentro das categorias oficiais do grupo, ou nome/tag nas categorias antigas."""
    if target.get("allowed") and product.ml_category_id in target["allowed"]:
        return True
    wanted = {key(x) for x in target["categories"]}
    if not wanted:
        return False
    return key(product.category) in wanted or bool(wanted & {key(t) for t in tags_of(product)})


def _recently_sent(db: Session, product_id: int, group: str, days: int) -> bool:
    if days <= 0:
        return False
    return bool(db.scalar(select(Publication.id).where(
        Publication.product_id == product_id, Publication.group_name == group, Publication.status == "sent",
        Publication.sent_at >= now() - timedelta(days=days))))


def assign(db: Session, c: Campaign, products: list[Product], targets: list[dict],
           done: dict[tuple[int, str], bool] | None = None) -> tuple[list[tuple[Product, str]], list[str]]:
    """Decide qual produto vai para qual grupo, na ordem de envio. Nunca repete produto no mesmo grupo."""
    done = done or {}
    warnings: list[str] = []
    if not targets:
        return [], ["Selecione pelo menos um grupo ativo."]
    registry = group_registry(db)
    already = {g: sum(1 for (_, gg) in done if gg == g) for g in (t["group"] for t in targets)}
    total_left = max(0, c.total_limit - len(done))
    auto = math.ceil(c.total_limit / len(targets)) if c.strategy == "balanced" else c.total_limit
    limits = {t["group"]: (t["limit"] or auto) for t in targets}
    counts = {t["group"]: already.get(t["group"], 0) for t in targets}
    skipped_recent = 0

    def eligible(p: Product, t: dict) -> bool:
        nonlocal skipped_recent
        g = t["group"]
        if counts[g] >= limits[g] or (p.id, g) in done:
            return False
        if c.strategy in ("category", "custom") and not _fits_group(p, t):
            return False
        days = c.reuse_days if c.reuse_days is not None else (registry[g].repost_days if g in registry else 7)
        conflict = conflict_reason(db, p.id, g)
        # Com intervalo de reutilização próprio, a campanha decide o "enviado recentemente"; publicação ativa sempre bloqueia.
        if (conflict and (conflict[0] == "active" or c.reuse_days is None)) or _recently_sent(db, p.id, g, days):
            skipped_recent += 1
            return False
        return True

    plan: list[tuple[Product, str]] = []
    for p in products:
        if len(plan) >= total_left:
            break
        if c.strategy == "balanced":
            # Um grupo por produto, sempre o que recebeu menos até agora.
            for t in sorted(targets, key=lambda t: (counts[t["group"]], targets.index(t))):
                if eligible(p, t):
                    plan.append((p, t["group"])); counts[t["group"]] += 1
                    break
        else:
            # sequential: o produto vai para todos os grupos; category/custom: para os grupos da categoria dele.
            for t in targets:
                if len(plan) >= total_left:
                    break
                if eligible(p, t):
                    plan.append((p, t["group"])); counts[t["group"]] += 1
    if c.strategy in ("category", "custom") and not any(t["categories"] or t["allowed"] for t in targets):
        warnings.append("Nenhum grupo tem categorias definidas para esta estratégia.")
    if len(plan) < total_left:
        warnings.append(f"Só há produtos para {len(plan) + len(done)} de {c.total_limit} anúncios com os filtros e limites atuais.")
    if skipped_recent:
        warnings.append(f"{skipped_recent} combinação(ões) de produto e grupo ficaram de fora porque já estão na fila ou foram enviadas recentemente.")
    return plan, warnings


# ---------------------------------------------------------------- ritmo

def validate(c: Campaign) -> list[str]:
    """Erros que tornam a campanha impossível de executar."""
    errors = []
    if not 0 <= c.start_hour < c.end_hour <= 24:
        errors.append("O horário de encerramento precisa ser depois do horário de início.")
    if not jload(c.weekdays):
        errors.append("Escolha pelo menos um dia da semana.")
    if c.block_size < 1:
        errors.append("Envie pelo menos 1 anúncio por execução.")
    if c.interval_minutes < 1:
        errors.append("O intervalo entre execuções precisa ser de pelo menos 1 minuto.")
    if c.interval_max_minutes and c.interval_max_minutes < c.interval_minutes:
        errors.append("O intervalo máximo não pode ser menor que o mínimo.")
    gap = gap_of(c)
    if (c.message_gap_seconds or 0) and c.message_gap_seconds < MIN_SEND_SECONDS:
        errors.append(f"O intervalo entre mensagens precisa ser de pelo menos {MIN_SEND_SECONDS} segundos.")
    if c.block_size * gap > c.interval_minutes * 60:
        errors.append(f"{c.block_size} anúncios por execução, com {gap} s entre mensagens, precisam de pelo menos "
                      f"{math.ceil(c.block_size * gap / 60)} min entre execuções.")
    start = as_utc(c.start_at)
    if c.end_at and as_utc(c.end_at) <= max(start or now(), now()):
        errors.append("A data de término precisa ser depois do início e no futuro.")
    if not 1 <= c.total_limit <= MAX_MESSAGES:
        errors.append(f"A campanha pode ter de 1 a {MAX_MESSAGES} anúncios.")
    if c.pause_every and c.pause_minutes < 1:
        errors.append("Informe a duração da pausa entre blocos.")
    window = (c.end_hour - c.start_hour) * 60
    if c.start_hour < c.end_hour and c.interval_minutes > window:
        errors.append("O intervalo é maior que a janela de horário do dia.")
    return errors


def gap_of(c: Campaign) -> int:
    return max(MIN_SEND_SECONDS, c.message_gap_seconds or MIN_SEND_SECONDS)


def schedule(c: Campaign, pairs: list, start: datetime | None = None) -> list[tuple]:
    """Horário de cada par (produto, grupo). Respeita janela diária, dias da semana, limite diário geral e por grupo,
    execuções com N anúncios separados pelo intervalo entre mensagens, intervalo entre execuções, pausas e data de término.
    Pares que não cabem até o término ficam de fora. A ordem dos pares é mantida, salvo quando um grupo já bateu o limite do dia."""
    zone = local_zone()
    rng = random.Random(c.id or 7)
    weekdays = {int(d) for d in jload(c.weekdays)} or set(range(7))
    begin = max(as_utc(start or c.start_at) or now(), now() + timedelta(minutes=1))
    end_at = as_utc(c.end_at)
    t = begin.replace(second=0, microsecond=0) + (timedelta(minutes=1) if begin.second else timedelta())
    gap = timedelta(seconds=gap_of(c))
    queue = list(pairs)
    out: list[tuple] = []
    per_day: dict = {}
    per_group: dict = {}
    guard = 0
    while queue and guard < 20000:
        guard += 1
        if end_at and t > end_at:
            break
        local = t.astimezone(zone)
        day_start = local.replace(hour=c.start_hour, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(hours=c.end_hour - c.start_hour)
        today = local.date()
        next_day = (day_start + timedelta(days=1)).astimezone(timezone.utc)
        if local.weekday() not in weekdays or local >= day_end or (c.daily_limit and per_day.get(today, 0) >= c.daily_limit):
            t = next_day; continue
        if local < day_start:
            t = day_start.astimezone(timezone.utc); continue
        room = c.daily_limit - per_day.get(today, 0) if c.daily_limit else c.block_size
        block = max(1, min(c.block_size, room))
        sent_now = 0
        for _ in range(block):
            at = t + gap * sent_now
            if at.astimezone(zone) >= day_end or (end_at and at > end_at):
                break
            idx = next((i for i, (_, g) in enumerate(queue)
                        if not c.group_daily_limit or per_group.get((today, g), 0) < c.group_daily_limit), None)
            if idx is None:
                break
            pair = queue.pop(idx)
            out.append((pair, at)); sent_now += 1
            per_group[(today, pair[1])] = per_group.get((today, pair[1]), 0) + 1
        if not sent_now:
            t = next_day; continue
        per_day[today] = per_day.get(today, 0) + sent_now
        minutes = c.interval_minutes if not c.interval_max_minutes else rng.randint(c.interval_minutes, c.interval_max_minutes)
        t = t + timedelta(minutes=minutes)
        if c.pause_every and len(out) % c.pause_every < sent_now and len(out) >= c.pause_every and queue:
            t = t + timedelta(minutes=c.pause_minutes)
    return out


def schedule_times(c: Campaign, count: int, start: datetime | None = None) -> list[datetime]:
    """Compatibilidade: horários para `count` anúncios sem distinção de grupo."""
    return [at for _, at in schedule(c, [(i, "") for i in range(count)], start)]


# ---------------------------------------------------------------- plano, confirmação e controle

def counts_of(db: Session, c: Campaign) -> dict[str, int]:
    rows = db.execute(select(Publication.status, func.count()).where(Publication.campaign_id == c.id)
                      .group_by(Publication.status)).all() if c.id else []
    return {status: n for status, n in rows}


def done_pairs(db: Session, c: Campaign) -> dict[tuple[int, str], bool]:
    if not c.id:
        return {}
    rows = db.execute(select(Publication.product_id, Publication.group_name)
                      .where(Publication.campaign_id == c.id, Publication.status.in_(DONE))).all()
    return {(pid, g): True for pid, g in rows}


def plan(db: Session, c: Campaign) -> dict:
    """Prévia completa: o que seria agendado agora com esta configuração (não grava nada)."""
    errors = validate(c)
    products = mix_categories(db, c, candidates(db, c))
    targets = group_targets(db, c)
    pairs, warnings = assign(db, c, products, targets, done_pairs(db, c)) if not errors else ([], [])
    timed = schedule(c, pairs) if pairs else []
    if len(timed) < len(pairs):
        reason = "até a data de término" if c.end_at else "nos próximos dias com estas regras"
        warnings.append(f"Só cabem {len(timed)} de {len(pairs)} anúncios {reason}.")
    pairs, times = [p for p, _ in timed], [t for _, t in timed]
    per_group: dict[str, int] = {t["group"]: 0 for t in targets}
    for _, g in pairs:
        per_group[g] = per_group.get(g, 0) + 1
    if times and times[-1] - times[0] > timedelta(days=30):
        warnings.append("A campanha levaria mais de 30 dias para terminar. Aumente o ritmo ou reduza a quantidade.")
    return {
        "errors": errors, "warnings": warnings,
        "matching": len(products), "selected": len({p.id for p, _ in pairs}), "messages": len(pairs),
        "per_group": [{"group": g, "count": n} for g, n in per_group.items()],
        "start": times[0].isoformat() if times else None, "end": times[-1].isoformat() if times else None,
        "duration_minutes": int((times[-1] - times[0]).total_seconds() // 60) if len(times) > 1 else 0,
        "items": [{"product_id": p.id, "title": p.title, "category": p.category, "group": g, "at": t.isoformat()}
                  for (p, g), t in list(zip(pairs, times))[:300]],
        "_pairs": pairs, "_times": times,
    }


def _drop_unsent(db: Session, c: Campaign) -> int:
    rows = list(db.scalars(select(Publication).where(Publication.campaign_id == c.id, Publication.status.in_(UNSENT))))
    for p in rows:
        db.delete(p)
    db.flush()
    return len(rows)


def apply(db: Session, c: Campaign, source: str = "painel") -> dict:
    """Confirma (ou replaneja) a campanha: troca as publicações ainda não enviadas pelo plano atual."""
    _drop_unsent(db, c)
    result = plan(db, c)
    if result["errors"]:
        return result
    created = 0
    for (product, group), at in zip(result["_pairs"], result["_times"]):
        publication = Publication(product_id=product.id, group_name=group, message=offer_text(db, product),
                                  approved_at=now(), scheduled_at=at, campaign_id=c.id)
        publication.status = "scheduled" if at > now() else "approved"
        try:
            with db.begin_nested():
                db.add(publication); db.flush()
            created += 1
        except IntegrityError:
            continue
    c.status = "scheduled"
    c.confirmed_at = c.confirmed_at or now()
    record_event(db, source, "campaigns.schedule", None, "scheduled",
                 f'Campanha #{c.id} "{c.name}": {created} anúncio(s) agendado(s) de {result["start"]} a {result["end"]}')
    result["created"] = created
    return result


def pause(db: Session, c: Campaign) -> int:
    rows = list(db.scalars(select(Publication).where(Publication.campaign_id == c.id,
                                                     Publication.status.in_(("scheduled", "approved")))))
    for p in rows:
        p.status = "paused"
    c.status = "paused"
    record_event(db, "painel", "campaigns.pause", None, "paused", f'Campanha #{c.id} "{c.name}" pausada ({len(rows)} anúncio(s) em espera)')
    return len(rows)


def cancel(db: Session, c: Campaign) -> int:
    rows = list(db.scalars(select(Publication).where(Publication.campaign_id == c.id, Publication.status.in_(UNSENT))))
    for p in rows:
        p.status = "cancelled"
    c.status = "cancelled"
    record_event(db, "painel", "campaigns.cancel", None, "cancelled", f'Campanha #{c.id} "{c.name}" cancelada ({len(rows)} anúncio(s) não enviados)')
    return len(rows)


def display_status(c: Campaign, counts: dict[str, int]) -> str:
    """draft, scheduled (aguardando execução), running, paused, completed, completed_with_failures, failed, cancelled."""
    if c.status in ("draft", "paused", "cancelled"):
        return c.status
    pending = sum(counts.get(s, 0) for s in ("scheduled", "approved", "sending", "awaiting_approval", "pending"))
    total = sum(n for s, n in counts.items() if s != "cancelled")
    if total and not pending:
        if counts.get("failed"):
            return "completed_with_failures" if counts.get("sent") else "failed"
        return "completed"
    if counts.get("sent") or counts.get("failed") or counts.get("sending"):
        return "running"
    return "scheduled"


def next_send(db: Session, c: Campaign) -> datetime | None:
    return db.scalar(select(func.min(Publication.scheduled_at)).where(
        Publication.campaign_id == c.id, Publication.status.in_(("scheduled", "approved"))))
