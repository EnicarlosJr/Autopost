"""Listas escolares: itens, opções por produto, conferência automática e página de orçamento."""
from datetime import datetime, timedelta, timezone
from app.models.product import Product
from app.school_lists import service
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_catalog import _second_user


def test_parse_lines_reads_quantity_and_requested():
    items = service.parse_lines("2 - Cola branca 90 g\n• Folhas de ofício | 500 folhas\n\n  TNT laranja  ")
    assert items == [{"name": "Cola branca 90 g", "requested": "2"},
                     {"name": "Folhas de ofício", "requested": "500 folhas"},
                     {"name": "TNT laranja", "requested": ""}]


def test_catalog_id_and_affiliate_link():
    assert service.catalog_id("https://www.mercadolivre.com.br/cola-branca/p/MLB28405051") == "MLB28405051"
    assert service.catalog_id("https://produto.mercadolivre.com.br/MLB-123-cola-_JM") == ""
    assert service.is_affiliate_link("https://meli.la/AbC123")
    assert not service.is_affiliate_link("https://www.mercadolivre.com.br/cola/p/MLB1")


def test_totals_use_quantity_and_skip_unpriced():
    items = [{"section": "coletivo", "options": [{"price": 18.0, "buy_qty": 2}, {"price": 19.0, "buy_qty": 2}, {"price": None, "buy_qty": 1}]},
             {"section": "coletivo", "options": []},
             {"section": "individual", "options": [{"price": 10.5, "buy_qty": 1}]}]
    t = service.totals(items)
    assert t["coletivo"] == {"min": 36.0, "max": 38.0, "items": 2, "priced": 1}
    assert t["individual"]["min"] == 10.5


def test_page_escapes_and_hides_unpriced_options():
    detail = {"school": "Colégio <X>", "grade": "Maternal II", "year": 2027, "items": [
        {"section": "coletivo", "name": "Cola </script>", "requested": "2", "color": "", "options": [
            {"label": "Econômica", "title": "Cola", "price": 18.0, "original_price": None, "buy_qty": 2, "image_source_url": "https://http2.mlstatic.com/a.jpg",
             "affiliate_url": "https://meli.la/x", "original_url": "https://www.mercadolivre.com.br/p/MLB1", "has_affiliate_link": True},
            {"label": "Premium", "title": "Sem preço", "price": None, "original_price": None, "buy_qty": 1, "image_source_url": "",
             "affiliate_url": "", "original_url": "https://www.mercadolivre.com.br/p/MLB2", "has_affiliate_link": False}]}]}
    page = service.render_page(detail, "#publi", datetime(2026, 11, 26, 11, 0, tzinfo=timezone.utc))
    assert "Colégio &lt;X&gt;" in page and "Cola <\\/script>" in page and "</script>\",\"requested" not in page
    assert "https://meli.la/x" in page and "Sem preço" not in page
    assert "26/11/2026 às 08:00" in page and "#publi" in page


def test_list_items_options_and_isolation(env):
    client, Session = env
    r = client.post("/api/school-lists", json={"school": "CPCM", "grade": "Maternal II", "year": 2027})
    assert r.status_code == 201
    lid = r.json()["id"]
    r = client.post(f"/api/school-lists/{lid}/items/import", json={"section": "coletivo", "text": "2 Cola branca 90 g\nTNT laranja | 4 metros"})
    assert r.json()["imported"] == 2
    item = r.json()["items"][0]
    r = client.put(f"/api/school-lists/items/{item['id']}/options/0",
                   json={"url": "https://www.mercadolivre.com.br/cola-branca-lavavel-bic-90g/p/MLB28405051?pdp_filters=x", "buy_qty": 2})
    assert r.status_code == 200
    option = r.json()["items"][0]["options"][0]
    assert option["label"] == "Econômica" and option["catalog_id"] == "MLB28405051" and option["status"] == "pending"
    assert option["original_url"].endswith("/p/MLB28405051") and not option["has_affiliate_link"]
    # o mesmo link em outra opção reaproveita o produto
    r = client.put(f"/api/school-lists/items/{item['id']}/options/1", json={"url": "https://www.mercadolivre.com.br/cola-branca-lavavel-bic-90g/p/MLB28405051"})
    opts = r.json()["items"][0]["options"]
    assert opts[0]["product_id"] == opts[1]["product_id"]
    assert client.put(f"/api/school-lists/items/{item['id']}/options/3", json={"url": "https://x.example/p"}).status_code == 422
    other = _second_user(Session, client)
    assert other.get(f"/api/school-lists/{lid}").status_code == 404
    assert other.get("/api/school-lists").json() == []


def test_refresh_queue_claims_and_releases(env):
    client, Session = env
    lid = client.post("/api/school-lists", json={"grade": "Maternal II", "refresh_hours": 12}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Cola"}).json()["items"][0]
    client.put(f"/api/school-lists/items/{item['id']}/options/0", json={"url": "https://www.mercadolivre.com.br/cola/p/MLB1"})
    first = client.get("/api/school-lists/refresh/next").json()["product"]
    assert first and first["url"].endswith("/p/MLB1")
    assert client.get("/api/school-lists/refresh/next").json()["product"] is None      # reservado
    r = client.post(f"/api/products/{first['id']}/browser-data", json={"title": "Cola Bic", "price": 19.0,
                    "page_url": "https://www.mercadolivre.com.br/cola/p/MLB1"})
    assert r.status_code == 200
    client.post(f"/api/school-lists/refresh/{first['id']}/done", json={})
    assert client.get("/api/school-lists/refresh/next").json()["product"] is None      # preço novo
    with Session() as db:
        p = db.get(Product, first["id"]); p.captured_at = datetime.now(timezone.utc) - timedelta(hours=13); db.commit()
    assert client.get("/api/school-lists/refresh/next").json()["product"]["id"] == first["id"]


def test_export_page_downloads_html(env):
    client, Session = env
    lid = client.post("/api/school-lists", json={"school": "CPCM", "grade": "Maternal II"}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Cola branca", "requested": "2 unidades"}).json()["items"][0]
    pid = client.put(f"/api/school-lists/items/{item['id']}/options/0", json={"url": "https://www.mercadolivre.com.br/cola/p/MLB9"}).json()["product_id"]
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Cola Bic 90 g", "price": 19.0})
    r = client.get(f"/api/school-lists/{lid}/page.html")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert 'filename="orcamento-maternal-ii-2027.html"' in r.headers["content-disposition"]
    assert "Cola Bic 90 g" in r.text and "Cola branca" in r.text


def _published_list(client):
    lid = client.post("/api/school-lists", json={"school": "Colégio CPCM", "grade": "Maternal II", "year": 2027}).json()["id"]
    item = client.post(f"/api/school-lists/{lid}/items", json={"name": "Cola branca", "requested": "2 unidades"}).json()["items"][0]
    pid = client.put(f"/api/school-lists/items/{item['id']}/options/0", json={"url": "https://www.mercadolivre.com.br/cola/p/MLB7"}).json()["product_id"]
    client.post(f"/api/products/{pid}/browser-data", json={"title": "Cola Bic 90 g", "price": 19.0})
    r = client.put(f"/api/school-lists/{lid}", json={"school": "Colégio CPCM", "grade": "Maternal II", "year": 2027,
                                                     "public": True, "turmas": ["A", "B", "a"], "contact": "contato@site.com"})
    assert r.json()["turmas"] == ["A", "B"] and r.json()["page_url"].endswith("/escolas/colegio-cpcm/maternal-ii-2027")
    return lid


def test_public_page_requires_identification_and_records_visitor(env):
    client, Session = env
    lid = _published_list(client)
    public = type(client)(client.app)          # navegador dos pais: sem login
    landing = public.get("/escolas/colegio-cpcm")
    assert landing.status_code == 200 and "Maternal II – Turma A" in landing.text and "contato@site.com" in landing.text
    page = public.get("/escolas/colegio-cpcm/maternal-ii-2027", follow_redirects=False)
    assert page.status_code == 303 and page.headers["location"] == "/escolas/colegio-cpcm"
    bad = public.post("/escolas/colegio-cpcm", data={"student_name": "Ana", "turma": f"{lid}:Z", "consent": "1"}, follow_redirects=False)
    assert bad.status_code == 422
    no_consent = public.post("/escolas/colegio-cpcm", data={"student_name": "Ana", "turma": f"{lid}:A"}, follow_redirects=False)
    assert no_consent.status_code == 422
    ok = public.post("/escolas/colegio-cpcm", data={"student_name": "  Ana   Souza ", "turma": f"{lid}:A", "consent": "1"}, follow_redirects=False)
    assert ok.status_code == 303 and ok.headers["location"] == "/escolas/colegio-cpcm/maternal-ii-2027"
    page = public.get("/escolas/colegio-cpcm/maternal-ii-2027")
    assert page.status_code == 200 and "Lista de Ana Souza · Maternal II A" in page.text and "Cola Bic 90 g" in page.text
    assert public.get("/escolas/colegio-cpcm", follow_redirects=False).status_code == 303      # volta direto para a lista
    rows = client.get("/api/school-visitors", params={"list_id": lid})
    assert rows.headers["x-total-count"] == "1"
    v = rows.json()[0]
    assert v["student_name"] == "Ana Souza" and v["turma"] == "Maternal II A" and v["visits"] == 1
    assert "Ana Souza" in client.get("/api/school-visitors/export.csv").text
    assert public.get("/api/school-visitors").status_code == 401
    client.post("/api/school-visitors/bulk/delete", json={"ids": [v["id"]]})
    assert public.get("/escolas/colegio-cpcm/maternal-ii-2027", follow_redirects=False).status_code == 303


def test_unpublished_school_is_not_found(env):
    client, _ = env
    client.post("/api/school-lists", json={"school": "Escola X", "grade": "1º Ano"})
    assert type(client)(client.app).get("/escolas/escola-x").status_code == 404
