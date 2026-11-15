"""Origem dos dados, Mercado Livre pelo navegador, conferência de preço, modelo e senha."""
from datetime import datetime, timedelta, timezone
import pytest
from app.models.automation import AutomationRule
from app.models.product import Product
from app.models.publication import Publication
from app.products.service import apply_server_fields
import app.products.service as product_service
import app.products.router as products_router
import app.workers.tasks as tasks
from tests.test_publication_flow import env  # noqa: F401  (fixture)

ML = "https://www.mercadolivre.com.br/moto/p/MLB123"

@pytest.fixture(autouse=True)
def _no_external_calls(monkeypatch):
    monkeypatch.setattr(product_service, "download_product_image", lambda url, pid: f"http://localhost:8000/media/products/{pid}.jpg?v=1")
    monkeypatch.setattr(products_router.process_product, "delay", lambda *a, **k: None)

def _browser(client, url=ML, **extra):
    payload = {"original_url": url, "affiliate_url": "https://meli.la/abc", "title": "Moto", "price": 4435,
               "original_price": 7999.9, "price_note": "no Pix", **extra}
    return client.post("/api/products/from-browser", json=payload).json()

def test_server_extraction_never_erases_browser_prices():
    product = Product(original_url="x", affiliate_url="y", title="Moto", price=4435, original_price=7999.9,
                      price_note="no Pix", data_source="browser", description="boa")
    apply_server_fields(product, {"title": "Moto 2", "price": 4435, "original_price": None, "price_note": "", "description": ""})
    assert (product.price, product.original_price, product.price_note) == (4435, 7999.9, "no Pix")
    assert product.title == "Moto 2" and product.description == "boa"

def test_mercado_livre_registered_in_panel_waits_for_browser(env):
    client, Session = env
    created = client.post("/api/products", json={"original_url": ML, "affiliate_url": "https://meli.la/abc"}).json()
    assert created["status"] == "awaiting_browser"
    with Session() as db:
        db.query(AutomationRule).update({"generate_publication": True}); db.commit()
    # O worker também não tenta o Mercado Livre.
    assert tasks.process_product.run(created["id"])["status"] == "awaiting_browser"
    assert client.get("/api/publications").json() == []
    # A leitura pelo navegador conclui o produto e gera a publicação completa.
    done = client.post(f"/api/products/{created['id']}/browser-data",
                       json={"title": "Moto", "price": 4435, "original_price": 7999.9, "price_note": "no Pix"}).json()
    assert done["status"] == "processed" and done["data_source"] == "browser"
    pubs = client.get("/api/publications").json()
    assert len(pubs) == 1 and "❌ De R$ 7.999,90" in pubs[0]["message"]

def test_enqueue_from_extension_creates_approved_publication_for_group(env):
    client, _ = env
    result = _browser(client, enqueue=True, group_name="Floripa 2032")
    assert result["publication_status"] == "approved"
    queue = client.get("/api/publications/queue").json()
    assert queue[0]["group_name"] == "Floripa 2032" and queue[0]["product"]["original_price"] == 7999.9

def test_stale_price_must_be_checked_before_sending(env):
    client, Session = env
    pub_id = _browser(client, enqueue=True, group_name="G")["publication_id"]
    with Session() as db:
        product = db.get(Publication, pub_id).product
        product.captured_at = datetime.now(timezone.utc) - timedelta(hours=7); db.commit()
    stale = client.post(f"/api/publications/{pub_id}/claim")
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "stale_price"
    # Relida no navegador com o mesmo preço: pode enviar.
    product_id = stale.json()["detail"]["product_id"]
    client.post(f"/api/products/{product_id}/browser-data", json={"title": "Moto", "price": 4435, "original_price": 7999.9, "price_note": "no Pix"})
    assert client.post(f"/api/publications/{pub_id}/claim").json()["status"] == "sending"

def test_price_change_updates_standard_text_and_holds_edited_text(env):
    client, _ = env
    first = _browser(client, enqueue=True, group_name="G1")
    product_id = first["product"]["id"]
    edited = client.post("/api/publications", json={"product_id": product_id, "message": "Só hoje por 4.435!", "group_name": "G2"}).json()
    client.post(f"/api/publications/{edited['id']}/approve")
    client.post(f"/api/products/{product_id}/browser-data", json={"title": "Moto", "price": 3999, "original_price": 7999.9})
    rows = {p["id"]: p for p in client.get("/api/publications").json()}
    assert "R$ 3.999,00" in rows[first["publication_id"]]["message"]
    assert rows[edited["id"]]["status"] == "failed" and "O preço mudou" in rows[edited["id"]]["last_error"]

def test_message_template_is_editable_and_validated(env):
    client, _ = env
    settings = client.get("/api/automations/settings").json()
    bad = client.put("/api/automations/settings", json={**settings, "message_template": "Oi {nome}"})
    assert bad.status_code == 422 and "{nome}" in bad.json()["detail"]
    template = "{titulo}\nDe {preco_de}\nPor {preco_por}{condicao}{desconto}\n{link}"
    client.put("/api/automations/settings", json={**settings, "message_template": template})
    product_id = _browser(client)["product"]["id"]
    message = client.get(f"/api/publications/preview/{product_id}").json()["message"]
    assert message == "Moto\nDe 7.999,90\nPor 4.435,00 no Pix (44% OFF)\nhttps://meli.la/abc"

def test_missing_required_variable_drops_only_its_line(env):
    client, _ = env
    preview = client.post("/api/automations/template-preview", json={"template": "A\nDe {preco_de}\nPor {preco_por}", "product_id": 1}).json()
    assert preview["message"] == "A\nPor 80,00"

def test_product_list_is_paginated(env):
    client, _ = env
    for i in range(3):
        _browser(client, url=f"https://www.mercadolivre.com.br/p/MLB{i}")
    page = client.get("/api/products?limit=2")
    assert page.headers["X-Total-Count"] == "4" and len(page.json()) == 2

def test_password_change(env):
    client, _ = env
    assert client.post("/api/auth/password", json={"current_password": "errada", "new_password": "nova-senha-forte-1"}).status_code == 400
    assert client.post("/api/auth/password", json={"current_password": "senha-forte-123", "new_password": "nova-senha-forte-1"}).json()["changed"]
    assert client.post("/api/auth/login", json={"email": "admin@localhost", "password": "nova-senha-forte-1"}).status_code == 200
