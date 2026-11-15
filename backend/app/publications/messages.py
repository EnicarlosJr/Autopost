"""Texto das ofertas: modelo com variáveis, sem inventar preços ou links ausentes."""
import re

from app.models.product import Product

DEFAULT_TEMPLATE = """🔥 OFERTA IMPERDÍVEL! 🔥

Olha essa oportunidade que encontramos! 👀
Preço especial por tempo limitado. Aproveite antes que acabe! 🛒

👇 Confira aqui:

❌ De R$ {preco_de}
💸 Por R$ {preco_por}{condicao}{desconto}

🛒 Compre aqui: {link}"""

# Variáveis obrigatórias na linha: se o produto não tiver o dado, a linha inteira some.
LINE_VARIABLES = {
    "titulo": "Nome do produto",
    "preco_de": "Preço anterior (só aparece quando é maior que o atual)",
    "preco_por": "Preço atual",
    "link": "Link de compra (afiliado)",
    "loja": "Loja ou vendedor",
    "categoria": "Categoria do produto",
}
# Variáveis opcionais: viram texto vazio quando não há dado, sem apagar a linha.
INLINE_VARIABLES = {
    "condicao": 'Condição do preço com espaço antes, por exemplo " no Pix"',
    "desconto": 'Desconto com espaço antes, por exemplo " (44% OFF)"',
    "desconto_pct": 'Só o número do desconto, por exemplo "44"',
}
VARIABLES = {**LINE_VARIABLES, **INLINE_VARIABLES}
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def _money(value: float) -> str:
    return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def discount_percent(price: float | None, original_price: float | None) -> int | None:
    """Percentual de desconto, só quando os dois preços existem e o anterior é maior."""
    if price is None or original_price is None or original_price <= price or original_price <= 0:
        return None
    # Arredonda para baixo, como o Mercado Livre exibe (44,6% aparece como 44% OFF).
    return int((original_price - price) / original_price * 100)


def unknown_variables(template: str) -> list[str]:
    return sorted({name for name in _PLACEHOLDER.findall(template) if name not in VARIABLES})


def _values(product: Product) -> dict[str, str]:
    price, original = product.price, product.original_price
    discount = discount_percent(price, original)
    note = (getattr(product, "price_note", "") or "").strip()
    return {
        "titulo": (product.title or "").strip(),
        "preco_de": _money(original) if discount is not None else "",
        "preco_por": _money(price) if price is not None else "",
        "link": (product.affiliate_url or "").strip(),
        "loja": (product.store or "").strip(),
        "categoria": (product.category or "").strip(),
        "condicao": f" {note}" if note and price is not None else "",
        "desconto": f" ({discount}% OFF)" if discount else "",
        "desconto_pct": str(discount) if discount else "",
    }


def render_template(template: str, product: Product) -> str:
    values = _values(product)
    lines = []
    for line in template.splitlines():
        names = _PLACEHOLDER.findall(line)
        if any(name in LINE_VARIABLES and not values[name] for name in names):
            continue  # falta um dado obrigatório desta linha: a linha não aparece
        lines.append(_PLACEHOLDER.sub(lambda m: values.get(m.group(1), m.group(0)), line))
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)  # linhas removidas não deixam buracos
    return text.strip()


def standard_offer_text(product: Product, template: str | None = None) -> str:
    """Monta a mensagem de oferta com o modelo configurado (ou o padrão)."""
    return render_template(template.strip() if template and template.strip() else DEFAULT_TEMPLATE, product)


def normalize_offer_text(message: str) -> str:
    """Remove textos promocionais antigos sem acrescentar conteúdo à mensagem."""
    legacy_lines = {
        "Link de afiliado: posso receber comissão pela compra, sem custo adicional para você.",
        "Link de afiliado: posso receber comissÃƒÂ£o pela compra, sem custo adicional para vocÃƒÂª.",
        "Link de afiliado: posso receber comissÃ£o pela compra, sem custo adicional para vocÃª.",
    }
    lines = [line for line in message.splitlines() if line.strip() not in legacy_lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and lines[0].strip().casefold() == "#publi":
        lines.pop(0)
    return "\n".join(lines).strip()


def is_legacy_offer_text(message: str) -> bool:
    first_line = next((line.strip() for line in message.splitlines() if line.strip()), "")
    return first_line.casefold() == "#publi"
