from datetime import datetime, timedelta, timezone
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.security import create_access_token, hash_password
from app.database.session import Base, get_db
from app.models.automation import AutomationRule
from app.models.product import Product
from app.models.publication import Publication
from app.models.user import User
import app.workers.tasks as tasks

@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("JWT_SECRET", "t" * 40)
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with Session() as db:
        db.add(AutomationRule(name="Regra principal", enabled=True, process_on_create=False, generate_publication=False,
                              require_approval=True, whatsapp_group_name="Ofertas"))
        db.add(User(email="admin@localhost", password_hash=hash_password("senha-forte-123"), is_active=True))
        db.add(Product(original_url="https://loja.example/p1", affiliate_url="https://afiliado.example/p1", title="Cafeteira", price=80))
        db.commit()
    from app.main import app
    def override():
        db = Session()
        try: yield db
        finally: db.close()
    app.dependency_overrides[get_db] = override
    monkeypatch.setattr(tasks, "SessionLocal", Session)
    client = TestClient(app)
    client.headers["Authorization"] = f"Bearer {create_access_token('admin@localhost')}"
    yield client, Session
    app.dependency_overrides.clear()

def _set_approval(Session, value):
    with Session() as db:
        db.query(AutomationRule).update({"require_approval": value}); db.commit()

def test_requests_without_valid_user_are_rejected(env):
    client, Session = env
    assert client.get("/api/products", headers={"Authorization": ""}).status_code == 401
    with Session() as db:
        db.query(User).update({"is_active": False}); db.commit()
    assert client.get("/api/products").status_code == 401

def test_approval_claim_and_sent_flow(env):
    client, _ = env
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    assert pub["status"] == "awaiting_approval" and pub["group_name"] == "Ofertas"
    assert client.post(f"/api/publications/{pub['id']}/claim").status_code == 409
    assert client.post(f"/api/publications/{pub['id']}/approve").json()["status"] == "approved"
    assert [p["id"] for p in client.get("/api/publications/queue").json()] == [pub["id"]]
    claimed = client.post(f"/api/publications/{pub['id']}/claim")
    assert claimed.json()["status"] == "sending" and claimed.json()["send_attempts"] == 1
    assert client.post(f"/api/publications/{pub['id']}/claim").status_code == 409  # não envia duas vezes
    assert client.post(f"/api/publications/{pub['id']}/sent", json={}).json()["status"] == "sent"

def test_without_required_approval_publication_is_ready_to_send(env):
    client, Session = env
    _set_approval(Session, False)
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    assert pub["status"] == "approved"

def test_failure_can_be_approved_again(env):
    client, Session = env
    _set_approval(Session, False)
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    client.post(f"/api/publications/{pub['id']}/claim")
    failed = client.post(f"/api/publications/{pub['id']}/failed", json={"error": "grupo não encontrado"}).json()
    assert failed["status"] == "failed" and failed["last_error"] == "grupo não encontrado"
    assert client.post(f"/api/publications/{pub['id']}/approve").json()["status"] == "approved"

def test_same_product_can_go_to_two_groups_but_not_twice_to_the_same(env):
    client, _ = env
    assert client.post("/api/publications", json={"product_id": 1, "message": "A", "group_name": "G1"}).status_code == 201
    assert client.post("/api/publications", json={"product_id": 1, "message": "A", "group_name": "G2"}).status_code == 201
    assert client.post("/api/publications", json={"product_id": 1, "message": "A", "group_name": "G1"}).status_code == 409

def test_repost_window_can_be_forced(env):
    client, Session = env
    _set_approval(Session, False)
    pub = client.post("/api/publications", json={"product_id": 1, "message": "A"}).json()
    client.post(f"/api/publications/{pub['id']}/claim"); client.post(f"/api/publications/{pub['id']}/sent", json={})
    again = client.post("/api/publications", json={"product_id": 1, "message": "A"})
    assert again.status_code == 409 and "últimas" in again.json()["detail"]
    assert client.post("/api/publications", json={"product_id": 1, "message": "A", "force_repost": True}).status_code == 201

def test_edit_message_and_group(env):
    client, _ = env
    pub = client.post("/api/publications", json={"product_id": 1, "message": "A"}).json()
    edited = client.patch(f"/api/publications/{pub['id']}", json={"message": "Novo texto", "group_name": "Outro"}).json()
    assert edited["message"] == "Novo texto" and edited["group_name"] == "Outro"

def test_scheduled_approved_publication_is_released_ready_to_send(env):
    client, Session = env
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    pub = client.post("/api/publications", json={"product_id": 1, "message": "A", "scheduled_at": future}).json()
    assert pub["status"] == "scheduled"
    assert client.post(f"/api/publications/{pub['id']}/approve").json()["status"] == "scheduled"
    with Session() as db:
        db.get(Publication, pub["id"]).scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1); db.commit()
    # SQLite não suporta FOR UPDATE SKIP LOCKED; o SQLAlchemy ignora a cláusula nele.
    assert tasks.release_due_publications()["released"] == 1
    assert client.get("/api/publications").json()[0]["status"] == "approved"

def test_stuck_sending_becomes_failed(env):
    client, Session = env
    _set_approval(Session, False)
    pub = client.post("/api/publications", json={"product_id": 1, "message": "A"}).json()
    client.post(f"/api/publications/{pub['id']}/claim")
    with Session() as db:
        db.get(Publication, pub["id"]).updated_at = datetime.now(timezone.utc) - timedelta(hours=1); db.commit()
    assert tasks.recover_stuck_items()["publications"] == 1
    assert client.get("/api/publications").json()[0]["status"] == "failed"

def test_duplicate_product_with_tracking_params_is_rejected(env, monkeypatch):
    client, _ = env
    payload = {"original_url": "https://loja.example/p1?utm_source=insta#x", "affiliate_url": "https://a.example/x"}
    assert client.post("/api/products", json=payload).status_code == 409

def test_summary_counts(env):
    client, _ = env
    data = client.get("/api/publications/summary").json()
    assert data["total_products"] == 1 and data["publications"] == 0

def test_browser_capture_fills_previous_price_and_note(env, monkeypatch):
    client, _ = env
    import app.products.service as products_router
    monkeypatch.setattr(products_router, "download_product_image", lambda url, pid: f"http://localhost:8000/media/products/{pid}.jpg?v=1")
    data = {"title": "Motocicleta Elétrica", "price": 4435, "original_price": 7999.9, "price_note": "no Pix",
            "image_url": "https://http2.mlstatic.com/x.jpg", "store": "Mercado Livre"}
    product = client.post("/api/products/1/browser-data", json=data).json()
    assert (product["price"], product["original_price"], product["price_note"]) == (4435, 7999.9, "no Pix")
    assert product["image_url"].startswith("http://localhost:8000/media/products/1.jpg")
    preview = client.get("/api/publications/preview/1").json()["message"]
    assert "❌ De R$ 7.999,90\n💸 Por R$ 4.435,00 no Pix (44% OFF)" in preview

def test_browser_capture_updates_standard_text_of_pending_publications(env, monkeypatch):
    client, _ = env
    import app.products.service as products_router
    monkeypatch.setattr(products_router, "download_product_image", lambda url, pid: "")
    standard = client.get("/api/publications/preview/1").json()["message"]
    auto = client.post("/api/publications", json={"product_id": 1, "message": standard, "group_name": "G1"}).json()
    manual = client.post("/api/publications", json={"product_id": 1, "message": "Texto meu", "group_name": "G2"}).json()
    client.post("/api/products/1/browser-data", json={"title": "Cafeteira", "price": 80, "original_price": 100})
    rows = {p["id"]: p["message"] for p in client.get("/api/publications").json()}
    assert "❌ De R$ 100,00" in rows[auto["id"]] and "(20% OFF)" in rows[auto["id"]]
    assert rows[manual["id"]] == "Texto meu"

def test_browser_capture_without_data_is_rejected(env):
    client, _ = env
    assert client.post("/api/products/1/browser-data", json={}).status_code == 422

def test_product_registered_from_browser_extension(env, monkeypatch):
    client, Session = env
    import app.products.service as products_router
    monkeypatch.setattr(products_router, "download_product_image", lambda url, pid: f"http://localhost:8000/media/products/{pid}.jpg?v=1")
    with Session() as db:
        db.query(AutomationRule).update({"generate_publication": True, "require_approval": False}); db.commit()
    payload = {"original_url": "https://www.mercadolivre.com.br/moto/p/MLB123?pdp_filters=x#reviews",
               "affiliate_url": "https://meli.la/abc", "category": "Mobilidade", "marketplace": "Mercado Livre",
               "title": "Motocicleta Elétrica", "price": 4435, "original_price": 7999.9, "price_note": "no Pix",
               "image_url": "https://http2.mlstatic.com/x.jpg"}
    first = client.post("/api/products/from-browser", json=payload).json()
    assert first["created"] is True
    product = first["product"]
    assert product["original_url"] == "https://www.mercadolivre.com.br/moto/p/MLB123"
    assert (product["status"], product["original_price"], product["price_note"]) == ("processed", 7999.9, "no Pix")
    pubs = client.get("/api/publications").json()
    assert len(pubs) == 1 and pubs[0]["status"] == "approved" and "(44% OFF)" in pubs[0]["message"]
    # Mesmo produto de novo: atualiza em vez de duplicar.
    again = client.post("/api/products/from-browser", json={**payload, "price": 4000}).json()
    assert again["created"] is False and again["product"]["id"] == product["id"] and again["product"]["price"] == 4000
    assert len(client.get("/api/publications").json()) == 1

def test_product_from_browser_without_affiliate_link_uses_product_link(env, monkeypatch):
    client, _ = env
    import app.products.service as products_router
    monkeypatch.setattr(products_router, "download_product_image", lambda url, pid: "")
    r = client.post("/api/products/from-browser", json={"original_url": "https://loja.example/p9", "title": "Fone", "price": 50}).json()
    assert r["product"]["affiliate_url"] == "https://loja.example/p9"

def test_postpone_when_whatsapp_has_no_preview(env):
    """Sem prévia do link, a extensão não envia: a publicação volta para a fila e desiste depois de 3 tentativas."""
    client, Session = env
    _set_approval(Session, False)
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta https://meli.la/x"}).json()
    assert client.post(f"/api/publications/{pub['id']}/postpone", json={}).status_code == 409     # não está em envio
    for attempt in (1, 2):
        client.post(f"/api/publications/{pub['id']}/claim")
        back = client.post(f"/api/publications/{pub['id']}/postpone", json={"minutes": 5, "reason": "sem prévia"}).json()
        assert back["status"] == "scheduled" and back["last_error"] == "sem prévia"
        at = datetime.fromisoformat(back["scheduled_at"].replace("Z", "+00:00"))
        assert (at if at.tzinfo else at.replace(tzinfo=timezone.utc)) > datetime.now(timezone.utc) + timedelta(minutes=4)
        assert client.get("/api/publications/queue").json() == []                                  # ainda não liberada
        with Session() as db:
            db.get(Publication, pub["id"]).scheduled_at = datetime.now(timezone.utc) - timedelta(seconds=5); db.commit()
    client.post(f"/api/publications/{pub['id']}/claim")
    assert client.post(f"/api/publications/{pub['id']}/postpone", json={"reason": "sem prévia"}).json()["status"] == "failed"
