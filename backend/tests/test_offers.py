from app.publications.messages import (
    discount_percent,
    is_legacy_offer_text,
    normalize_offer_text,
    standard_offer_text,
)
from app.models.product import Product

HEADER = (
    "🔥 OFERTA IMPERDÍVEL! 🔥\n\n"
    "Olha essa oportunidade que encontramos! 👀\n"
    "Preço especial por tempo limitado. Aproveite antes que acabe! 🛒\n\n"
    "👇 Confira aqui:\n\n"
)

def test_offer_with_previous_price_shows_discount():
    product = Product(title="Tênis Puma 180", price=193.90, original_price=599.90, affiliate_url="https://meli.la/2T8VGbS")
    assert standard_offer_text(product) == HEADER + (
        "❌ De R$ 599,90\n"
        "💸 Por R$ 193,90 (67% OFF)\n\n"
        "🛒 Compre aqui: https://meli.la/2T8VGbS"
    )

def test_offer_without_previous_price_has_no_discount_line():
    product = Product(title="Cafeteira", price=80, affiliate_url="https://example.com/a")
    assert standard_offer_text(product) == HEADER + "💸 Por R$ 80,00\n\n🛒 Compre aqui: https://example.com/a"

def test_offer_does_not_invent_missing_prices():
    product = Product(title="Fone", affiliate_url="https://example.com/afiliado")
    text = standard_offer_text(product)
    assert "R$" not in text and "OFF" not in text
    assert text.endswith("🛒 Compre aqui: https://example.com/afiliado")

def test_thousands_are_formatted_in_brazilian_style():
    product = Product(price=1299.9, original_price=1999, affiliate_url="https://x.example")
    text = standard_offer_text(product)
    assert "❌ De R$ 1.999,00" in text and "💸 Por R$ 1.299,90 (34% OFF)" in text

def test_discount_ignores_equal_or_lower_previous_price():
    assert discount_percent(100, 100) is None
    assert discount_percent(100, 90) is None
    assert discount_percent(None, 90) is None

def test_normalize_removes_legacy_prefix_and_affiliate_footer():
    message = (
        "#publi\n\nOferta antiga\n\n"
        "Link de afiliado: posso receber comissão pela compra, sem custo adicional para você."
    )
    assert normalize_offer_text(message) == "Oferta antiga"

def test_normalize_preserves_publi_text_after_the_first_line():
    assert normalize_offer_text("#publi\n\nOferta\n\n#publi") == "Oferta\n\n#publi"

def test_legacy_offer_detection_only_matches_a_leading_label():
    assert is_legacy_offer_text("#publi\n\nOferta antiga")
    assert not is_legacy_offer_text("Oferta\n\n#publi")

def test_price_condition_is_shown_next_to_the_price():
    product = Product(price=4435, original_price=7999.9, price_note="no Pix", affiliate_url="https://meli.la/23TfLf1")
    text = standard_offer_text(product)
    assert "❌ De R$ 7.999,90\n💸 Por R$ 4.435,00 no Pix (44% OFF)" in text
