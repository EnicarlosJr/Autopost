"""Regras do ciclo de vida das publicações, compartilhadas por API e worker."""
import json
import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.models.automation import AutomationLog, AutomationRule
from app.models.product import Product
from app.models.publication import ACTIVE_STATUSES, Publication
from app.products.sources import needs_browser
from app.publications.messages import standard_offer_text

def now() -> datetime:
    return datetime.now(timezone.utc)

def as_utc(value: datetime | None) -> datetime | None:
    """SQLite devolve datas sem fuso; tratamos como UTC."""
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

def main_rule(db: Session) -> AutomationRule | None:
    """A configuração do sistema é uma só: a primeira regra."""
    return db.scalar(select(AutomationRule).order_by(AutomationRule.id).limit(1))

def approval_required(db: Session) -> bool:
    rule = main_rule(db)
    return True if rule is None or not rule.enabled else bool(rule.require_approval)

def offer_text(db: Session, product: Product) -> str:
    rule = main_rule(db)
    return standard_offer_text(product, rule.message_template if rule else None)

def ready_status(publication: Publication, require_approval: bool) -> str:
    """Estado de uma publicação que já pode sair (sem agendamento pendente)."""
    return "approved" if publication.approved_at or not require_approval else "awaiting_approval"

def initial_status(publication: Publication, require_approval: bool) -> str:
    if not require_approval and publication.approved_at is None:
        publication.approved_at = now()
    scheduled = as_utc(publication.scheduled_at)
    if scheduled and scheduled > now():
        return "scheduled"
    return ready_status(publication, require_approval)

def record_event(db: Session, source: str, task_type: str, product_id: int | None, status: str, detail: str) -> None:
    """Registra um evento no histórico (tela Configurações > Histórico), para diagnóstico posterior."""
    db.add(AutomationLog(task_id=source[:80], task_type=task_type[:80], product_id=product_id, status=status[:30],
                         attempt=1, detail=str(detail)[:2000]))

def release_due(db: Session, source: str) -> list[Publication]:
    """Libera as publicações agendadas cujo horário chegou: aprovadas vão para a fila de envio.

    Usada pelo agendador (Celery beat) e também pela própria fila da API, para que um
    agendamento vencido nunca fique preso se o agendador estiver parado.
    """
    require_approval = approval_required(db)
    due = list(db.scalars(select(Publication)
                          .where(Publication.status == "scheduled", Publication.scheduled_at <= now())
                          .with_for_update(skip_locked=True)))
    for publication in due:
        publication.status = ready_status(publication, require_approval)
        note = "liberada para envio" if publication.status == "approved" else "aguardando aprovação"
        record_event(db, source, "publications.release_due", publication.product_id, "released",
                     f"Publicação #{publication.id} agendada para {as_utc(publication.scheduled_at).isoformat()} {note}")
    return due

def repost_window_hours() -> float:
    try:
        return max(0.0, float(os.getenv("REPOST_WINDOW_HOURS", "24")))
    except ValueError:
        return 24.0

def price_max_age_hours() -> float:
    try:
        return max(0.0, float(os.getenv("PRICE_MAX_AGE_HOURS", "6")))
    except ValueError:
        return 6.0

def price_needs_check(product: Product) -> bool:
    """Preço lido pelo navegador há mais tempo que o limite: reler antes de enviar."""
    hours = price_max_age_hours()
    if not hours:
        return False
    if product.data_source != "browser" and not needs_browser(product.original_url):
        return False
    captured = as_utc(product.captured_at)
    return captured is None or captured < now() - timedelta(hours=hours)

def conflict_reason(db: Session, product_id: int, group_name: str, exclude_id: int | None = None) -> tuple[str, str] | None:
    """Retorna (tipo, mensagem) quando não pode existir outra publicação deste produto neste grupo.

    tipo "active": já há uma publicação em andamento (bloqueio definitivo).
    tipo "recent": já foi enviada dentro da janela de repost (pode ser forçado).
    """
    active = select(Publication.id).where(Publication.product_id == product_id, Publication.group_name == group_name,
                                          Publication.status.in_(ACTIVE_STATUSES))
    if exclude_id:
        active = active.where(Publication.id != exclude_id)
    if db.scalar(active):
        return "active", "Já existe uma publicação ativa deste produto para este grupo"
    hours = repost_window_hours()
    if hours:
        recent = select(Publication.id).where(Publication.product_id == product_id, Publication.group_name == group_name,
                                              Publication.status == "sent", Publication.sent_at >= now() - timedelta(hours=hours))
        if exclude_id:
            recent = recent.where(Publication.id != exclude_id)
        if db.scalar(recent):
            return "recent", f"Este produto já foi enviado para este grupo nas últimas {hours:g} h. Marque \"repostar mesmo assim\" para continuar."
    return None

def maybe_generate_publication(db: Session, product: Product, *, force: bool = False, group: str | None = None,
                               approve: bool = False) -> Publication | None:
    """Cria a publicação de um produto pronto.

    Sem `force`, segue a configuração (gerar publicação, filtros de categoria e loja).
    Com `force` (o usuário pediu "pôr na fila"), cria mesmo assim; `approve` aprova na hora.
    """
    rule = main_rule(db)
    if not product.title:
        return None
    if not force:
        if not (rule and rule.enabled and rule.generate_publication):
            return None
        categories = json.loads(rule.categories or "[]")
        marketplaces = json.loads(rule.marketplaces or "[]")
        if categories and product.category not in categories:
            return None
        if marketplaces and product.marketplace not in marketplaces:
            return None
    target = (group if group is not None else (rule.whatsapp_group_name if rule else "")).strip()
    if conflict_reason(db, product.id, target):
        return None
    publication = Publication(product_id=product.id, message=offer_text(db, product), group_name=target)
    if approve:
        publication.approved_at = now()
    publication.status = initial_status(publication, approval_required(db))
    try:
        with db.begin_nested():
            db.add(publication)
            db.flush()
    except IntegrityError:
        return None
    return publication
