"""Qualidade das ofertas: nota ponderada, desconto conferido, agrupamento de parecidos e escolha dos melhores."""
from app.searches.ranking import Offer, group_offers, offer_score, pick_best, same_product, title_tokens, weighted_rating


def test_tokens_join_units_and_drop_noise():
    assert title_tokens("SSD Kingston 480 GB NV2 Original Frete Grátis") == {"ssd", "kingston", "480gb", "nv2"}
    assert title_tokens("Fones de Ouvido Bluetooth") == {"fone", "ouvido", "bluetooth"}


def test_weighted_rating_needs_volume():
    assert weighted_rating(5.0, 3) < weighted_rating(4.8, 10000)
    assert weighted_rating(None, 0) == 4.3


def test_flat_price_halves_the_announced_discount():
    common = dict(discount_pct=50, rating=4.7, sold=2000, price=100)
    fresh = offer_score(**common)
    flat = offer_score(**common, history_points=5, min_30d=100, max_30d=101, history_days=10)
    dropped = offer_score(**common, history_points=5, min_30d=100, max_30d=150, history_days=10)
    assert flat < fresh < dropped           # caiu de verdade e está no menor preço: ganha mais


def test_trust_and_volume_raise_the_score():
    base = dict(discount_pct=30, rating=4.6, price=50)
    assert offer_score(**base, sold=5000, official_store=True, fulfillment=True) > offer_score(**base, sold=5000) > offer_score(**base, sold=5)


def test_same_product_rules():
    a = Offer(1, "Fone de Ouvido Bluetooth JBL Tune 520BT Preto", 199.9, "MLB1")
    assert same_product(a, Offer(2, "Fone Ouvido Bluetooth JBL Tune 520BT Azul", 189.9, "MLB1"))           # outra cor
    assert same_product(a, Offer(3, "JBL Tune 520BT Fone Bluetooth", 210, "MLB1"))                          # título curto
    assert not same_product(a, Offer(4, "Fone de Ouvido Bluetooth JBL Tune 520BT", 199.9, "MLB2"))           # outra categoria
    assert not same_product(a, Offer(5, "Fone de Ouvido Bluetooth JBL Tune 520BT", 599.9, "MLB1"))           # preço muito diferente
    assert not same_product(Offer(6, "SSD Kingston NV2 480GB", 200), Offer(7, "SSD Kingston NV2 1TB", 220))  # capacidade
    assert not same_product(Offer(10, "Camiseta Básica Masculina Algodão", 50), Offer(11, "Camiseta Básica Feminina Algodão", 50))
    assert same_product(Offer(8, "Qualquer título", 10, catalog="MLB999"), Offer(9, "Outro título", 12, catalog="MLB999"))


def _offers():
    return [
        Offer(1, "Fone de Ouvido Bluetooth JBL Tune 520BT Preto", 199.9, "FONE", seller="Loja A", score=80),
        Offer(2, "Fone Ouvido Bluetooth JBL Tune 520BT Azul", 169.9, "FONE", seller="Loja B", score=78),
        Offer(3, "JBL Tune 520BT Fone Bluetooth Branco", 205.0, "FONE", seller="Loja C", score=70),
        Offer(4, "Smartwatch Amazfit Bip 5 Preto", 399.0, "RELOGIO", seller="Loja A", score=75),
        Offer(5, "Caixa de Som JBL Go 3 Bluetooth", 229.0, "CAIXA", seller="Loja A", score=74),
        Offer(6, "Caixa de Som JBL Go 3 Bluetooth Azul", 215.0, "CAIXA", seller="Loja D", score=60, eligible=False),
        Offer(7, "Carregador Turbo Samsung 25W USB-C", 79.0, "CARREG", seller="Loja E", score=72),
    ]


def test_group_keeps_one_representative_and_prefers_cheaper():
    info = group_offers(_offers())
    assert info[1].key == info[2].key == info[3].key and info[1].size == 3
    assert info[2].best and info[2].cheapest and not info[1].best      # 2 pontos a menos, 30 reais mais barato
    assert info[5].best and info[5].size == 1 and info[6].key == info[5].key   # o fora dos filtros não representa
    order = sorted(info, key=lambda i: info[i].order)
    assert order[:3] == [2, 1, 3]                                         # grupo do fone primeiro, parecidos em seguida


def test_pick_best_skips_repeats_and_varies_seller():
    offers = _offers()
    info = group_offers(offers)
    picked = pick_best(offers, info, 3, per_seller=1)
    assert len(picked) == 3 and 1 not in picked and 3 not in picked       # um fone só
    sellers = [o.seller for o in offers if o.id in picked]
    assert len(set(sellers)) == 3
    assert set(pick_best(offers, info, 10)) == {2, 4, 5, 7}              # completa sem limites, sem repetir grupo


def test_pick_best_ignores_groups_already_in_campaign():
    offers = _offers() + [Offer(-50, "Fone Bluetooth JBL Tune 520BT", 189.0, "FONE", taken=True)]
    info = group_offers(offers)
    assert info[2].taken and 2 not in pick_best(offers, info, 10)
