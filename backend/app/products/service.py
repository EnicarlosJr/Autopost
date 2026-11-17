"""Regras dos produtos: de onde vêm os dados e como eles podem ser substituídos."""
import json
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.publication import Publication
from app.products.image_fetch import download_product_image
from app.products.sources import BROWSER_NOTICE
from app.publications.messages import normalize_offer_text
from app.publications.service import maybe_generate_publication, offer_text

VERIFICATION_NOTICE = ("A loja solicitou verificação de tráfego e não forneceu a página do produto. "
                       "Abra o link no navegador e revise os dados manualmente.")
PRICE_FIELDS = ("price", "original_price", "price_note")
# Publicações que ainda podem mudar de texto ou ser seguradas quando o preço muda.
OPEN_STATUSES = ("pending", "awaiting_approval", "approved", "scheduled", "failed")


def now() -> datetime:
    return datetime.now(timezone.utc)


def add_note(product: Product, line: str) -> None:
    """Acrescenta uma nota sem repetir a mesma linha a cada nova tentativa."""
    line = line.strip()
    lines = [x for x in (product.notes or "").splitlines() if x.strip() and x.strip() != line]
    product.notes = "\n".join(lines + [line]).strip()


def remove_notes(product: Product, *fragments: str) -> None:
    product.notes = "\n".join(x for x in (product.notes or "").splitlines()
                              if x.strip() and not any(f in x for f in fragments)).strip()


def _money(value: float | None) -> str:
    return "sem preço" if value is None else f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def apply_server_fields(product: Product, fields: dict) -> None:
    """Grava o que o servidor extraiu sem apagar dados melhores que já existem.

    - Nunca troca um valor preenchido por vazio.
    - Preços lidos pelo navegador não são substituídos pela extração do servidor
      (a prévia do link de afiliado não traz o preço anterior).
    """
    keep_prices = product.data_source == "browser"
    for name, value in fields.items():
        if name in PRICE_FIELDS and keep_prices:
            continue
        if value in (None, "") and getattr(product, name) not in (None, ""):
            continue
        setattr(product, name, value)
    if not keep_prices and fields.get("price") is not None:
        product.data_source = "server"
        product.captured_at = now()


def _refresh_publications(db: Session, product: Product, previous_text: str, old_price: float | None,
                          old_original: float | None) -> None:
    """Atualiza o texto padrão das publicações abertas; segura as editadas à mão se o preço mudou."""
    new_text = offer_text(db, product)
    price_changed = (old_price, old_original) != (product.price, product.original_price)
    rows = db.scalars(select(Publication).where(Publication.product_id == product.id,
                                                Publication.status.in_(OPEN_STATUSES)))
    for publication in rows:
        if normalize_offer_text(publication.message) == previous_text:
            publication.message = new_text
        elif price_changed and publication.status in ("approved", "scheduled"):
            publication.status = "failed"
            publication.last_error = (f"O preço mudou ({_money(old_price)} para {_money(product.price)}) e o texto "
                                      "desta publicação foi editado à mão. Revise o texto e libere de novo.")


def _swap_link(db: Session, product: Product, old_links: list[str], new_link: str) -> None:
    """Link de afiliado novo: troca o link antigo também nas mensagens editadas à mão (que não são
    reescritas pelo texto padrão). Sem isso a mensagem sairia com o link comum, sem comissão."""
    old_links = [u for u in old_links if u and u != new_link]
    if not old_links:
        return
    for publication in db.scalars(select(Publication).where(Publication.product_id == product.id,
                                                            Publication.status.in_(OPEN_STATUSES))):
        text = publication.message
        for old in sorted(old_links, key=len, reverse=True):
            text = text.replace(old, new_link)
        publication.message = text


def apply_capture(db: Session, product: Product, data, *, generate: bool = False) -> None:
    """Grava os dados lidos no navegador do usuário (fonte mais confiável para lojas que bloqueiam o servidor)."""
    previous_text = normalize_offer_text(offer_text(db, product))
    old_price, old_original = product.price, product.original_price
    if data.title.strip(): product.title = data.title.strip()
    if data.description.strip(): product.description = data.description.strip()
    if data.store.strip(): product.store = data.store.strip()
    link = (getattr(data, "affiliate_link", "") or "").strip()
    old_links = [u for u in (product.affiliate_url, product.original_url) if u]
    if link.startswith("https://") and " " not in link:
        product.affiliate_url = link
    if data.price is not None:
        product.price = data.price
        product.original_price = data.original_price if data.original_price and data.original_price > data.price else None
        product.price_note = data.price_note.strip()
        product.data_source = "browser"
        product.captured_at = now()
    remove_notes(product, VERIFICATION_NOTICE, BROWSER_NOTICE, "solicitou verificação", "Falha na extração:",
                 "Imagem do navegador", "Prévia do link de afiliado", "Aguardando leitura")
    if data.image_url.startswith(("http://", "https://")):
        try:
            product.image_url = download_product_image(data.image_url, product.id)
        except Exception as exc:  # a imagem é opcional; os preços continuam valendo
            add_note(product, f"Imagem do navegador não pôde ser baixada: {str(exc)[:200]}")
    product.status = "processed" if product.title else "needs_review"
    product.processing_started_at = None
    _refresh_publications(db, product, previous_text, old_price, old_original)
    if link and link == product.affiliate_url:
        _swap_link(db, product, old_links, link)
    if generate:
        maybe_generate_publication(db, product)


def apply_manual_edit(db: Session, product: Product, changes: dict) -> None:
    """Edição feita pelo usuário no painel: vale como leitura confirmada dos preços."""
    previous_text = normalize_offer_text(offer_text(db, product))
    old_price, old_original = product.price, product.original_price
    for key, value in changes.items():
        if key == "tags":
            from app.campaigns.service import clean_list
            value = json.dumps(clean_list(value or []), ensure_ascii=False)
        setattr(product, key, str(value) if key == "affiliate_url" and value is not None else value)
    if any(key in changes for key in PRICE_FIELDS):
        product.data_source = "manual"
        product.captured_at = now()
    if product.status in ("needs_review", "awaiting_browser") and product.title.strip() and product.price is not None:
        product.status = "processed"
        remove_notes(product, BROWSER_NOTICE, "Aguardando leitura")
    _refresh_publications(db, product, previous_text, old_price, old_original)
