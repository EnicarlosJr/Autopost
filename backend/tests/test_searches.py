"""Buscas automáticas: filtros, nota, histórico de preço, aprovação com agenda e modo automático."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import pytest
from app.models.publication import Publication
from app.models.search import Listing, PricePoint
import app.searches.service as search_service
from tests.test_publication_flow import env  # noqa: F401  (fixture)

ZONE = ZoneInfo("America/Sao_Paulo")

@pytest.fixture(autouse=True)
def _no_downloads(monkeypatch):
    monkeypatch.setattr(search_service, "download_product_image", lambda url, pid: f"http://localhost:8000/media/products/{pid}.jpg")

def _search(client, **extra):
    payload = {"name": "Ferramentas", "terms": "lanterna tática\nparafusadeira", "exclude_terms": "usado",
               "min_discount": 20, "min_rating": 4.0, "group_name": "Garimpo", **extra}
    response = client.post("/api/searches", json=payload)
    assert response.status_code == 201, response.text
    return response.json()

def _item(n, **extra):
    return {"external_id": f"MLB{n}", "url": f"https://www.mercadolivre.com.br/item-{n}/up/MLBU{n}",
            "term": "lanterna tática", "title": f"Lanterna {n}", "price": 53.84, "original_price": 159.9,
            "rating": 4.6, "sold": 10000, "free_shipping": True, **extra}

def _send(client, search_id, items, error=""):
    return client.post(f"/api/searches/{search_id}/results", json={"items": items, "error": error}).json()

def test_due_search_gives_urls_and_is_reserved(env):
    client, _ = env
    search = _search(client)
    due = client.get("/api/searches/due").json()
    assert due["id"] == search["id"]
    assert due["terms"][0]["url"] == "https://lista.mercadolivre.com.br/lanterna-t%C3%A1tica"
    # Reservada: não volta a aparecer enquanto a extensão trabalha.
    assert client.get("/api/searches/due").json() is None

def test_filters_score_and_listing(env):
    client, _ = env
    search = _search(client)
    result = _send(client, search["id"], [
        _item(1),
        _item(2, title="Lanterna USADO bom"),
        _item(3, original_price=60),           # desconto pequeno
        _item(4, rating=3.9),                  # nota baixa
        _item(5, external_id="", url=""),      # inválido
    ])
    assert result["read"] == 4 and result["matching"] == 1
    listed = client.get("/api/listings").json()
    assert [x["external_id"] for x in listed] == ["MLB1"]
    assert listed[0]["discount_pct"] == 66 and listed[0]["score"] > 60
    rejected = {x["external_id"]: x["reject_reason"] for x in client.get("/api/listings", params={"matches": "false"}).json()}
    assert rejected == {"MLB2": 'contém "usado"', "MLB3": "desconto menor que 20%", "MLB4": "nota menor que 4"}
    assert "1 na lista" in client.get("/api/searches").json()[0]["last_result"]

def test_price_history_marks_lowest_price(env):
    client, Session = env
    search = _search(client)
    _send(client, search["id"], [_item(1, price=70)])
    with Session() as db:
        listing = db.query(Listing).one()
        for point in db.query(PricePoint).all():
            point.seen_at = datetime.now(timezone.utc) - timedelta(days=2)
        db.add(PricePoint(listing_id=listing.id, price=65, seen_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.commit()
    before = client.get("/api/listings").json()[0]["score"]
    _send(client, search["id"], [_item(1, price=50)])
    after = client.get("/api/listings").json()[0]
    assert after["min_price_30d"] == 50 and after["score"] > before
    assert len(client.get(f"/api/listings/{after['id']}/history").json()) == 3

def test_approve_distributes_in_group_window(env):
    client, Session = env
    search = _search(client)
    client.put("/api/group-schedules/Garimpo", json={"start_hour": 9, "end_hour": 21, "max_per_day": 2, "gap_minutes": 60})
    _send(client, search["id"], [_item(1), _item(2, sold=10), _item(3, sold=100)])
    ids = [x["id"] for x in client.get("/api/listings").json()]
    result = client.post("/api/listings/approve", json={"ids": ids}).json()
    assert len(result["scheduled"]) == 3 and not result["skipped"]
    with Session() as db:
        pubs = db.query(Publication).filter(Publication.group_name == "Garimpo").order_by(Publication.scheduled_at).all()
        times = [p.scheduled_at.replace(tzinfo=timezone.utc).astimezone(ZONE) for p in pubs]
        assert all(p.approved_at and p.status == "scheduled" for p in pubs)
        assert all(9 <= t.hour < 21 for t in times)
        assert times[1] - times[0] >= timedelta(minutes=60)
        assert len({t.date() for t in times}) == 2          # no máximo 2 por dia
        # Sem link de afiliado ainda: a extensão gera antes de enviar.
        assert pubs[0].product.affiliate_url == "" and "R$ 53,84" in pubs[0].message
    assert client.get("/api/listings").json() == []

def test_approve_at_chosen_time_and_discard(env):
    client, Session = env
    search = _search(client)
    _send(client, search["id"], [_item(1), _item(2)])
    first, second = client.get("/api/listings").json()
    when = (datetime.now(timezone.utc) + timedelta(hours=3)).replace(microsecond=0)
    result = client.post("/api/listings/approve", json={"ids": [first["id"]], "scheduled_at": when.isoformat()}).json()
    assert result["scheduled"][0]["scheduled_at"].startswith(when.isoformat()[:16])
    assert client.post("/api/listings/discard", json={"ids": [second["id"]]}).json() == {"discarded": 1}
    # Descartado não volta mesmo aparecendo de novo na busca.
    _send(client, search["id"], [_item(2)])
    assert client.get("/api/listings").json() == []

def test_auto_mode_schedules_best_listings(env):
    client, Session = env
    search = _search(client, mode="auto", max_per_run=2)
    result = _send(client, search["id"], [_item(1, sold=5), _item(2), _item(3, sold=50000)])
    assert result["auto_scheduled"] == 2
    with Session() as db:
        titles = {p.product.title for p in db.query(Publication).filter(Publication.group_name == "Garimpo")}
    assert titles == {"Lanterna 2", "Lanterna 3"}

def test_already_scheduled_listing_does_not_come_back(env):
    client, _ = env
    search = _search(client)
    _send(client, search["id"], [_item(1)])
    client.post("/api/listings/accept-all", json={})
    _send(client, search["id"], [_item(1, price=40)])
    assert client.get("/api/listings").json() == []

def test_affiliate_link_from_extension_updates_message(env):
    client, Session = env
    search = _search(client)
    _send(client, search["id"], [_item(1)])
    client.post("/api/listings/accept-all", json={})
    with Session() as db:
        pub = db.query(Publication).filter(Publication.group_name == "Garimpo").one()
        product_id, pub_id = pub.product_id, pub.id
        assert "meli.la" not in pub.message
    client.post(f"/api/products/{product_id}/browser-data",
                json={"title": "Lanterna 1", "price": 53.84, "original_price": 159.9, "affiliate_link": "https://meli.la/1bHv3sa"})
    assert "https://meli.la/1bHv3sa" in client.get(f"/api/publications/{pub_id}").json()["message"]

def test_validation(env):
    client, _ = env
    assert client.post("/api/searches", json={"name": "x", "terms": "a", "mode": "auto"}).status_code == 422
    assert client.post("/api/searches", json={"name": "x", "terms": "a", "min_price": 50, "max_price": 10}).status_code == 422

def test_due_schedule_is_released_by_queue_even_without_beat(env):
    """Se o agendador (Celery beat) estiver parado, a própria fila libera o que venceu."""
    client, Session = env
    search = _search(client)
    _send(client, search["id"], [_item(1)])
    listing_id = client.get("/api/listings").json()[0]["id"]
    soon = datetime.now(timezone.utc) + timedelta(minutes=2)
    client.post("/api/listings/approve", json={"ids": [listing_id], "scheduled_at": soon.isoformat()})
    assert client.get("/api/publications/queue").json() == []          # ainda não chegou a hora
    with Session() as db:
        pub = db.query(Publication).filter(Publication.group_name == "Garimpo").one()
        pub.scheduled_at = datetime.now(timezone.utc) - timedelta(minutes=1); db.commit()
        pub_id = pub.id
    queue = client.get("/api/publications/queue").json()
    assert [p["id"] for p in queue] == [pub_id] and queue[0]["status"] == "approved"
    # Mesmo fluxo de um produto manual: reserva, envio confirmado e registro no histórico.
    with Session() as db:
        db.get(Publication, pub_id).product.captured_at = datetime.now(timezone.utc); db.commit()
    assert client.post(f"/api/publications/{pub_id}/claim").json()["status"] == "sending"
    sent = client.post(f"/api/publications/{pub_id}/sent", json={"detail": "Prévia do link: com imagem."}).json()
    assert sent["status"] == "sent"
    logs = client.get("/api/automations/logs").json()
    details = [l["detail"] for l in (logs if isinstance(logs, list) else logs.get("items", []))]
    assert any("liberada para envio" in d for d in details) and any("com imagem" in d for d in details)
