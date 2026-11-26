"""Ofertas do dia do Mercado Livre como fonte das buscas (campanha, nicho e busca automática)."""
from app.models.publication import Publication
from app.searches.service import offer_pages, offer_urls, pages_for
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_campaign_search import _item, _no_downloads, _setup  # noqa: F401  (fixture)

LINK = ("https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1#filter_applied=container_id"
        "&filter_position=1&is_recommended_domain=false&origin=scut")


def test_offer_pages_and_only_mercado_livre_links():
    pages = pages_for(LINK)
    assert [p["url"] for p in pages] == ["https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1",
                                         "https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1&page=2",
                                         "https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1&page=3"]
    assert len(offer_pages(pages=9)) == 5
    assert pages_for("Ofertas do dia")[0]["url"] == "https://www.mercadolivre.com.br/ofertas?promotion_type=deal_of_the_day"
    assert pages_for("ofertas relâmpago")[1]["url"] == "https://www.mercadolivre.com.br/ofertas?promotion_type=lightning&page=2"
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
    # A própria página de ofertas já vem filtrada pela categoria da busca.
    assert [t["url"] for t in due["terms"]] == ["https://www.mercadolivre.com.br/ofertas?promotion_type=deal_of_the_day&category=MLB1648",
                                                "https://www.mercadolivre.com.br/ofertas?promotion_type=deal_of_the_day&category=MLB1648&page=2"]
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
    # Nicho com categorias: as palavras não precisam aparecer no título (as categorias já filtram).
    assert created[0]["filters"]["offers_match_keywords"] is False


def test_automatic_search_accepts_offers(env):
    client, _ = env
    s = client.post("/api/searches", json={"name": "Ofertas", "terms": "ofertas do dia\nparafusadeira", "interval_minutes": 60}).json()
    client.post(f"/api/searches/{s['id']}/run")
    due = client.get("/api/searches/due").json()
    assert [t["url"] for t in due["terms"]][-1] == "https://lista.mercadolivre.com.br/parafusadeira"
    assert len(due["terms"]) == 4 and due["terms"][0]["url"].startswith("https://www.mercadolivre.com.br/ofertas")


def test_offer_sections_categories_and_page_cap():
    urls = [p["url"] for p in offer_urls(["lightning", "outlet"], ["MLB23332"], pages=2, start=4)]
    assert urls == ["https://www.mercadolivre.com.br/ofertas?promotion_type=lightning&category=MLB23332&page=4",
                    "https://www.mercadolivre.com.br/ofertas?promotion_type=lightning&category=MLB23332&page=5",
                    "https://www.mercadolivre.com.br/ofertas?container_id=MLB916440-2&category=MLB23332&page=4",
                    "https://www.mercadolivre.com.br/ofertas?container_id=MLB916440-2&category=MLB23332&page=5"]
    assert offer_urls(["all"], [], 1)[0]["url"] == "https://www.mercadolivre.com.br/ofertas"
    # Muitas combinações: lê menos páginas por combinação e nunca passa de 12 páginas (600 anúncios).
    many = offer_urls(["all", "lightning", "deal_of_the_day", "unbeatable", "outlet"], [f"MLB{i}" for i in range(6)], pages=5)
    assert len(many) == 12 and all("page=" not in p["url"] for p in many)
    assert offer_urls(["nada"], ["xx"], 1)[0]["url"] == "https://www.mercadolivre.com.br/ofertas"


def test_offer_searches_rotate_pages_and_skip_used_products(env):
    client, Session = env
    _, camp = _setup(client)
    cid = camp["id"]
    body = {"filters": {"source": "offers", "offer_kinds": ["lightning"], "offers_pages": 2, "skip_used_days": 7}}
    first = client.post(f"/api/campaigns/{cid}/searches", json=body).json()
    second = client.post(f"/api/campaigns/{cid}/searches", json=body).json()
    assert first["filters"]["offers_start"] == 1 and second["filters"]["offers_start"] == 3
    assert second["terms"] == ["Ofertas relâmpago (páginas 3 a 4)"]
    assert client.post(f"/api/campaigns/{cid}/searches", json={"filters": {"source": "offers", "offer_kinds": ["xyz"]}}).status_code == 422
    # Produto já anunciado (na fila) é pulado nas buscas com "pular já anunciados".
    client.get("/api/campaign-searches/due")
    client.post(f"/api/campaign-searches/{first['id']}/results", json={"items": [_item(31, "MLB1672"), _item(32, "MLB1672", title="SSD Outro")]})
    found = client.get(f"/api/campaigns/{cid}/searches/{first['id']}/results").json()
    assert client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [found[0]["listing_id"]]}).status_code in (200, 201)
    pid = client.get(f"/api/campaigns/{cid}/products").json()[0]["product_id"]
    with Session() as db:
        db.add(Publication(product_id=pid, group_name="Grupo X", message="oi", status="scheduled")); db.commit()
    client.get("/api/campaign-searches/due")
    client.post(f"/api/campaign-searches/{second['id']}/results", json={"items": [_item(31, "MLB1672"), _item(32, "MLB1672", title="SSD Outro")]})
    reasons = {r["external_id"]: r["reason"] for r in client.get(f"/api/campaigns/{cid}/searches/{second['id']}/results",
                                                                 params={"matched": "all"}).json()}
    used = "MLB31" if found[0]["external_id"] == "MLB31" else "MLB32"
    assert reasons[used] == "já anunciado nos últimos 7 dias" and sum(1 for r in reasons.values() if r == "") == 1


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
