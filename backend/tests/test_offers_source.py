"""Ofertas do dia do Mercado Livre como fonte das buscas (campanha, nicho e busca automática)."""
from app.searches.service import offer_pages, pages_for
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_campaign_search import _item, _no_downloads, _setup  # noqa: F401  (fixture)

LINK = ("https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1#filter_applied=container_id"
        "&filter_position=1&is_recommended_domain=false&origin=scut")


def test_offer_pages_and_only_mercado_livre_links():
    pages = pages_for(LINK)
    assert [p["url"] for p in pages] == ["https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1",
                                         "https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1&page=2",
                                         "https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1&page=3"]
    assert pages_for("Ofertas do dia") == pages and len(offer_pages(pages=9)) == 5
    assert pages_for("https://lista.mercadolivre.com.br/mochila#x")[0]["url"] == "https://lista.mercadolivre.com.br/mochila"
    assert pages_for("https://outro-site.com/ofertas")[0]["url"].startswith("https://lista.mercadolivre.com.br/")   # nunca abre outro site


def test_campaign_search_from_offers_filters_by_keywords_and_category(env):
    client, _ = env
    niche, camp = _setup(client)
    cid = camp["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"categories": [{"id": "MLB1648", "include_children": True}],
                    "keywords": ["ssd", "memória ram"], "filters": {"source": "offers", "offers_pages": 2}}).json()
    assert s["terms"] == ["Ofertas do dia (2 páginas)"]
    due = client.get("/api/campaign-searches/due").json()
    assert [t["url"] for t in due["terms"]] == [p["url"] for p in offer_pages(pages=2)]
    items = [_item(1, "MLB1672"), _item(2, "MLB1672", title="Memória RAM DDR4 8GB"), _item(3, "MLB1672", title="Pendrive 64GB"),
             _item(4, "MLB1338", title="SSD Halteres")]
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": items})
    results = client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results", params={"matched": "all"}).json()
    reasons = {r["external_id"]: r["reason"] for r in results}
    assert reasons["MLB1"] == "" and reasons["MLB2"] == "" and reasons["MLB3"] == "não cita as palavras-chave"
    assert reasons["MLB4"].startswith("fora das categorias")
    # Sem palavras e sem categorias vale nas ofertas (todas as ofertas, com os outros filtros).
    assert client.post(f"/api/campaigns/{cid}/searches", json={"filters": {"source": "offers"}}).status_code == 201
    assert client.post(f"/api/campaigns/{cid}/searches", json={}).status_code == 422


def test_niche_search_from_offers_is_one_search_per_niche(env):
    client, _ = env
    niche, camp = _setup(client)
    words = [f"palavra{i}" for i in range(14)]
    client.put(f"/api/niches/{niche['id']}", json={"name": "Informática", "categories": [{"id": "MLB1648", "include_children": True}],
                                                  "include_keywords": words, "exclude_keywords": []})
    r = client.post(f"/api/campaigns/{camp['id']}/searches/by-niches", json={"niche_ids": [niche["id"]], "filters": {"source": "offers"}})
    created = r.json()["searches"]
    assert len(created) == 1 and len(created[0]["keywords"]) == 14 and created[0]["terms"] == ["Ofertas do dia (3 páginas)"]


def test_automatic_search_accepts_offers(env):
    client, _ = env
    s = client.post("/api/searches", json={"name": "Ofertas", "terms": "ofertas do dia\nparafusadeira", "interval_minutes": 60}).json()
    client.post(f"/api/searches/{s['id']}/run")
    due = client.get("/api/searches/due").json()
    assert [t["url"] for t in due["terms"]][-1] == "https://lista.mercadolivre.com.br/parafusadeira"
    assert len(due["terms"]) == 4 and due["terms"][0]["url"].startswith("https://www.mercadolivre.com.br/ofertas")


def test_mercado_pago_balance_price_keeps_other_methods_price(env):
    # Cartão da Central/Ofertas: R$ 26,51 "com saldo no Mercado Pago", "ou R$ 33,14 em outros meios".
    client, Session = env
    niche, camp = _setup(client)
    cid = camp["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"filters": {"source": "offers", "trust": "off", "min_sold": 0,
                                                                        "min_rating": None, "exclude_suspicious": False}}).json()
    client.get("/api/campaign-searches/due")
    item = _item(9, "MLB1672", title="Óleo Elseve 100ml", price=26.51, original_price=64.19,
                 price_note="com saldo no Mercado Pago", regular_price=33.14)
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": [item]})
    r = client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results").json()[0]
    client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [r["listing_id"]], "search_id": s["id"]})
    from app.models.product import Product
    prods = client.get(f"/api/campaigns/{cid}/products").json()
    assert prods[0]["price"] == 26.51 and prods[0]["price_note"] == "com saldo no Mercado Pago"
    with Session() as db:
        assert db.get(Product, prods[0]["product_id"]).regular_price == 33.14
