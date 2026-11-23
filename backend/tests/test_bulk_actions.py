"""Ações em massa e limpeza: excluir publicações do histórico, restaurar achados, apagar buscas da campanha e o histórico do worker."""
from app.models.automation import AutomationLog
from app.models.search import Listing
from app.products.sources import marketplace_of
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_campaign_search import _no_downloads, _setup, _item  # noqa: F401  (fixture)


def test_marketplace_comes_from_the_link():
    assert marketplace_of("https://produto.mercadolivre.com.br/MLB-123") == "Mercado Livre"
    assert marketplace_of("https://amzn.to/abc") == "Amazon"
    assert marketplace_of("https://www.loja.example/p1") == "loja.example"


def test_product_without_marketplace_gets_it_from_the_link(env):
    client, _ = env
    p = client.post("/api/products", json={"original_url": "https://www.amazon.com.br/dp/B0TESTE", "affiliate_url": "https://amzn.to/x"}).json()
    assert p["marketplace"] == "Amazon"


def test_bulk_delete_only_cancelled_or_failed(env):
    client, _ = env
    first = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    client.post(f"/api/publications/{first['id']}/cancel")
    second = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    result = client.post("/api/publications/bulk/delete", json={"ids": [first["id"], second["id"]]}).json()
    assert result == {"deleted": 1, "skipped": 1}
    assert client.get(f"/api/publications/{first['id']}").status_code == 404
    assert client.get(f"/api/publications/{second['id']}").json()["status"] == "awaiting_approval"


def test_restore_discarded_listings(env):
    client, Session = env
    with Session() as db:
        db.add_all([Listing(external_id="MLB1", url="https://produto.mercadolivre.com.br/MLB-1", title="A", status="discarded", matches=True),
                    Listing(external_id="MLB2", url="https://produto.mercadolivre.com.br/MLB-2", title="B", status="new", matches=True)])
        db.commit()
        ids = [l.id for l in db.query(Listing).order_by(Listing.id)]
    assert client.post("/api/listings/restore", json={"ids": ids}).json() == {"restored": 1}
    assert {l["external_id"] for l in client.get("/api/listings").json()} == {"MLB1", "MLB2"}


def test_clear_worker_logs(env):
    client, Session = env
    with Session() as db:
        db.add(AutomationLog(task_id="t1", task_type="teste", status="ok")); db.commit()
    assert client.delete("/api/automations/logs").json() == {"deleted": 1}
    assert client.get("/api/automations/logs").json() == []


def test_remove_campaign_searches_keeps_products(env):
    client, _ = env
    _, camp = _setup(client)
    cid = camp["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"keywords": ["ssd"], "categories": [{"id": "MLB1648", "include_children": True}]}).json()
    client.get("/api/campaign-searches/due")
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": [_item(1, "MLB1672")]})
    listing = client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results").json()[0]
    client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [listing["listing_id"]], "search_id": s["id"]})
    assert client.post(f"/api/campaigns/{cid}/searches/remove", json={"ids": [s["id"]]}).json() == {"deleted": 1, "skipped": 0}
    assert client.get(f"/api/campaigns/{cid}/searches").json() == []
    products = client.get(f"/api/campaigns/{cid}/products").json()
    assert len(products) == 1 and products[0]["search_id"] is None
