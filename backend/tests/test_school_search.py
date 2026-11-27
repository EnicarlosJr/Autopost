"""Listas escolares: busca de equivalentes, preço normal x Pix e conferência que não tira nada da lista."""
from app.models.product import Product
from app.campaigns.search_service import suspicious_term
from app.school_lists import matching, service
from tests.test_publication_flow import env  # noqa: F401  (fixture)


def test_compare_rejects_any_difference_that_changes_the_product():
    ref = matching.make_reference("Caderno 96 folhas", "", "Caderno Brochura Tilibra 96 Folhas Capa Dura")
    assert matching.compare(ref, "Caderno Brochura Foroni 96 Folhas Capa Dura")[0] == ""
    assert "200 folhas" in matching.compare(ref, "Caderno Brochura 200 Folhas Capa Dura")[0]
    assert "espiral" in matching.compare(ref, "Caderno Espiral 96 Folhas Capa Dura")[0]
    assert "kit" in matching.compare(ref, "Kit 5 Cadernos Brochura 96 Folhas")[0]
    assert "acessório" in matching.compare(ref, "Capa Para Caderno Brochura")[0]
    cola = matching.make_reference("Cola branca 90 g", "", "Cola Branca Escolar Tenaz 90g")
    assert "110 g" in matching.compare(cola, "Cola Branca 110g Tenaz")[0]
    assert matching.compare(cola, "Cola Bastão 90g")[0] and matching.compare(cola, "Cola Colorida Glitter 90g")[0]
    lapis = matching.make_reference("Lápis preto nº 2", "", "Lápis Grafite Faber-Castell Nº2")
    assert "nº 1" in matching.compare(lapis, "Lápis Grafite nº 1")[0]
    assert matching.compare(lapis, "Lapis De Cor 12 Cores")[0]
    estojo = matching.make_reference("Estojo duplo", "azul", "Estojo Duplo Com Zíper Azul")
    assert "rosa" in matching.compare(estojo, "Estojo Duplo Rosa")[0]
    assert matching.compare(estojo, "Estojo Duplo Kipling Azul")[0] == ""


def _cand(i, title, price, **extra):
    return {"listing_id": i, "external_id": f"MLB{i}", "url": f"https://produto.mercadolivre.com.br/MLB-{i}", "title": title,
            "price": price, "rating": 4.7, "sold": 500, "official_store": False, "fulfillment": False, "free_shipping": True,
            "catalog_product_id": None, **extra}


def test_pick_fills_empty_slots_and_finds_cheaper():
    ref = matching.make_reference("Cola branca 90 g", "", "Cola Branca Tenaz 90g")
    cands = [_cand(1, "Cola Branca Pritt 90g", 6.5), _cand(2, "Cola Branca Acrilex 90g", 4.2),
             _cand(3, "Cola Branca Tenaz 90g Original", 7.9, official_store=True, sold=20000),
             _cand(4, "Cola Branca 90g", 3.1, rating=3.2),                       # nota baixa
             _cand(5, "Cola Branca 1kg", 20.0), _cand(6, "Cola Branca 90g Réplica", 2.0)]
    out = matching.pick(ref, cands, [{"slot": 1, "price": 5.5, "url": "https://x/1"}], [0, 2], suspicious=suspicious_term)
    assert [c["listing_id"] for c in out["slots"]["0"]][0] == 2                 # mais barato que a opção atual
    assert out["slots"]["2"][0]["listing_id"] == 3                              # loja oficial, muito vendido
    assert "1" not in out["slots"] and out["cheaper"] == []                      # a Econômica estava vazia
    assert out["rejected"] == 3
    full = matching.pick(ref, cands, [{"slot": s, "price": 5.5, "url": f"https://x/{s}"} for s in (0, 1, 2)], [], suspicious=suspicious_term)
    assert [c["listing_id"] for c in full["cheaper"]] == [2]


def test_search_queue_suggestions_use_and_dismiss(env):
    client, Session = env
    lid = client.post("/api/school-lists", json={"grade": "1º ano"}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Cola branca 90 g", "requested": "2"}).json()["items"][0]
    pid = client.put(f"/api/school-lists/items/{item['id']}/options/1",
                     json={"url": "https://www.mercadolivre.com.br/cola/p/MLB77", "buy_qty": 2}).json()["product_id"]
    assert client.get("/api/school-searches/due").json() is None        # espera a leitura do produto
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Cola Branca Tenaz 90g", "price": 5.5})
    due = client.get("/api/school-searches/due").json()
    assert due["item_id"] == item["id"] and len(due["terms"]) == 3
    assert due["terms"][1]["url"].endswith("_OrderId_PRICE_ASC_NoIndex_True")
    items = [{"external_id": "MLB101", "url": "https://produto.mercadolivre.com.br/MLB-101", "title": "Cola Branca Acrilex 90g",
              "price": 4.2, "rating": 4.8, "sold": 900},
             {"external_id": "MLB102", "url": "https://produto.mercadolivre.com.br/MLB-102", "title": "Cola Branca 110g", "price": 3.0}]
    r = client.post(f"/api/school-searches/{due['id']}/results", json={"items": items})
    assert r.json()["status"] == "done"
    detail = client.get(f"/api/school-lists/{lid}").json()
    search = detail["items"][0]["search"]
    assert [c["external_id"] for c in search["slots"]["0"]] == ["MLB101"] and detail["suggestions"] == 1
    used = client.post(f"/api/school-lists/items/{item['id']}/suggestions/use", json={"listing_id": search["slots"]["0"][0]["listing_id"], "slot": 0})
    opts = used.json()["items"][0]["options"]
    assert {o["slot"] for o in opts} == {0, 1} and opts[0]["buy_qty"] == 2 and opts[0]["price"] == 4.2
    assert not opts[0]["has_affiliate_link"]                                     # o painel gera o link em seguida
    assert used.json()["items"][0]["search"]["slots"].get("0") is None           # opção preenchida
    client.post(f"/api/school-lists/items/{item['id']}/suggestions/dismiss", json={"external_id": "MLB101"})
    with Session() as db:
        from app.models.school import SchoolListItem
        assert "MLB101" in db.get(SchoolListItem, item["id"]).dismissed


def test_pix_price_is_a_note_and_unavailable_product_stays(env):
    client, Session = env
    lid = client.post("/api/school-lists", json={"school": "CPCM", "grade": "1º ano"}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Mochila"}).json()["items"][0]
    pid = client.put(f"/api/school-lists/items/{item['id']}/options/0", json={"url": "https://www.mercadolivre.com.br/m/p/MLB5"}).json()["product_id"]
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Mochila", "price": 4435, "price_note": "no Pix",
                                                           "regular_price": 4580, "price_conditions": "no Pix"})
    detail = client.get(f"/api/school-lists/{lid}").json()
    assert detail["totals"]["coletivo"]["min"] == 4580                         # total no cartão
    data = service.page_data(detail)
    assert data["items"][0]["options"][0]["price"] == 4580 and data["items"][0]["options"][0]["pay_price"] == 4435
    assert data["items"][0]["options"][0]["pay_note"] == "no Pix"
    # conferência: link quebrado e produto esgotado não apagam nada
    client.get("/api/school-lists/refresh/next")
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Mochila", "available": False})
    r = client.post(f"/api/school-lists/refresh/{pid}/done", json={"error": "Produto indisponível no Mercado Livre agora.",
                                                                   "unavailable": True, "link_ok": False})
    assert r.status_code == 200
    detail = client.get(f"/api/school-lists/{lid}").json()
    option = detail["items"][0]["options"][0]
    assert option["unavailable"] and option["price"] == 4435 and option["affiliate_ok"] is False
    assert detail["unavailable"] == 1 and detail["items"][0]["search"]["reason"] == "indisponivel"
    assert service.page_data(detail)["items"][0]["options"] == []                # some da página, o item fica
    assert client.get("/api/school-lists/refresh/next").json()["product"] is None   # espera 2 h para tentar de novo
    with Session() as db:
        assert db.get(Product, pid).availability == "indisponível"
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Mochila", "price": 4300})
    assert not client.get(f"/api/school-lists/{lid}").json()["items"][0]["options"][0]["unavailable"]


def test_mercado_pago_promo_is_explained_in_message_and_parents_page(env):
    from app.publications.messages import standard_offer_text
    product = Product(title="Óleo Elseve", price=26.51, original_price=64.19, price_note="com saldo no Mercado Pago",
                      regular_price=33.14, affiliate_url="https://meli.la/x")
    text = standard_offer_text(product)
    assert "*R$ 26,51* com saldo no Mercado Pago (sem saldo: R$ 33,14)" in text
    pix = Product(title="Moto", price=4435, original_price=7999.9, price_note="no Pix", regular_price=4580, affiliate_url="https://meli.la/y")
    assert "no Pix (44% OFF)" in standard_offer_text(pix) and "sem saldo" not in standard_offer_text(pix)
    # Página dos pais: cada opção diz o tipo de promoção; a página pergunta se a pessoa tem saldo.
    client, Session = env
    lid = client.post("/api/school-lists", json={"school": "CPCM", "grade": "1º ano"}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Mochila"}).json()["items"][0]
    pid = client.put(f"/api/school-lists/items/{item['id']}/options/0", json={"url": "https://www.mercadolivre.com.br/m/p/MLB8"}).json()["product_id"]
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Mochila", "price": 44.99, "price_note": "com saldo no Mercado Pago",
                                                           "regular_price": 54.99})
    option = service.page_data(client.get(f"/api/school-lists/{lid}").json())["items"][0]["options"][0]
    assert option["pay_kind"] == "mp" and option["pay_price"] == 44.99 and option["price"] == 54.99
    page = service.render_page(client.get(f"/api/school-lists/{lid}").json())
    assert "Você tem conta no Mercado Pago?" in page


def test_turmas_can_be_renamed_and_removed(env):
    client, _ = env
    lid = client.post("/api/school-lists", json={"grade": "1º ano", "turmas": ["A", "A ", "a", "B"]}).json()["id"]
    body = {"grade": "1º ano", "turmas": ["A", "Turma B"]}
    r = client.put(f"/api/school-lists/{lid}", json=body).json()
    assert r["turmas"] == ["A", "Turma B"]
    assert client.put(f"/api/school-lists/{lid}", json={"grade": "1º ano", "turmas": ["Turma B"]}).json()["turmas"] == ["Turma B"]


def test_mp_help_whatsapp_link_and_settings(env):
    assert service.whatsapp_number("(11) 99999-0000") == "5511999990000"
    assert service.whatsapp_number("123") == ""
    link = service.whatsapp_link("11999990000", "", "Colégio CPCM", "1º ano")
    assert link.startswith("https://wa.me/5511999990000?text=") and "Col%C3%A9gio%20CPCM" in link
    client, _ = env
    assert client.put("/api/school-lists/settings/mp-help", json={"whatsapp": "123"}).status_code == 422
    r = client.put("/api/school-lists/settings/mp-help", json={"whatsapp": "(11) 99999-0000", "message": "Oi, sou da {escola}"}).json()
    assert r["whatsapp"] == "5511999990000" and r["preview_url"].endswith("Oi%2C%20sou%20da%20Col%C3%A9gio%20Exemplo")
    page = service.render_page({"school": "X", "grade": "1", "year": 2027, "items": []}, help_url=link)
    assert "https://wa.me/5511999990000" in page and "Quero ajuda pelo WhatsApp" in page
    assert "wa.me" not in service.render_page({"school": "X", "grade": "1", "year": 2027, "items": []}, help_url="https://evil.example")
