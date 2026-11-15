"""Fase C: regras de automação, distribuição por categoria oficial, conjuntos de grupos, status do painel e o fluxo completo."""
from datetime import datetime, timedelta, timezone
from app.models.product import Product
from app.models.publication import Publication
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_campaigns import ZONE, _base, _preview, _seed
from tests.test_catalog import tree, _second_user
from tests.test_campaign_search import _item, _no_downloads  # noqa: F401  (fixture)

def _official(Session, n, cat, start=0):
    with Session() as db:
        for i in range(start, start + n):
            db.add(Product(original_url=f"https://loja.example/{cat}/{i}", affiliate_url=f"https://meli.la/{cat}{i}", title=f"Item {cat} {i}",
                           price=50.0, original_price=100.0, category="", ml_category_id=cat, status="processed"))
        db.commit()

def _times(plan):
    return [datetime.fromisoformat(i["at"]).astimezone(ZONE) for i in plan["items"]]

def test_message_gap_and_execution_interval(env):
    client, Session = env
    _seed(Session, 10, "Academia")
    plan = _preview(client, groups=[{"group": "A"}], total_limit=6, block_size=3, interval_minutes=15, message_gap_seconds=45)
    t = _times(plan)
    assert plan["errors"] == [] and len(t) == 6
    assert [b - a for a, b in zip(t, t[1:])] == [timedelta(seconds=45)] * 2 + [timedelta(minutes=15) - timedelta(seconds=90)] + [timedelta(seconds=45)] * 2
    # 3 mensagens com 5 min entre elas não cabem em execuções de 10 min.
    assert _preview(client, groups=[{"group": "A"}], block_size=3, interval_minutes=10, message_gap_seconds=300)["errors"]
    assert client.post("/api/campaigns/preview", json=_base(message_gap_seconds=5)).status_code == 422

def test_end_date_cuts_the_plan(env):
    client, Session = env
    _seed(Session, 30, "Academia")
    start = datetime.fromisoformat(_base()["start_at"])
    plan = _preview(client, groups=[{"group": "A"}], total_limit=30, interval_minutes=60, start_hour=9, end_hour=12,
                    end_at=(start + timedelta(days=1, hours=1)).isoformat())
    # Dia 1: 9h, 10h, 11h. Dia 2: 9h e 10h (o término é às 10h do dia seguinte).
    assert plan["messages"] == 5 and max(_times(plan)) <= start + timedelta(days=1, hours=1)
    assert any("data de término" in w for w in plan["warnings"])
    assert _preview(client, end_at=(start - timedelta(hours=1)).isoformat())["errors"]

def test_group_daily_limit_and_reuse_days(env):
    client, Session = env
    _seed(Session, 12, "Academia")
    plan = _preview(client, strategy="sequential", groups=[{"group": "A"}, {"group": "B"}], total_limit=8,
                    interval_minutes=10, group_daily_limit=2)
    per = {}
    for item, t in zip(plan["items"], _times(plan)):
        per[(t.date(), item["group"])] = per.get((t.date(), item["group"]), 0) + 1
    assert plan["messages"] == 8 and max(per.values()) == 2 and len({d for d, _ in per}) == 2
    # Produto enviado ontem ao grupo A: o prazo do grupo (7 dias) bloqueia; reuse_days=0 libera.
    with Session() as db:
        pid = db.query(Product).filter(Product.title.like("Academia%")).order_by(Product.id).first().id
        db.add(Publication(product_id=pid, group_name="A", message="x", status="sent", sent_at=datetime.now(timezone.utc) - timedelta(days=1)))
        db.commit()
    blocked = _preview(client, groups=[{"group": "A"}], total_limit=12)
    assert pid not in [i["product_id"] for i in blocked["items"]]
    free = _preview(client, groups=[{"group": "A"}], total_limit=12, reuse_days=0)
    assert pid in [i["product_id"] for i in free["items"]], (pid, free["matching"], free["warnings"], blocked["warnings"])

def test_distribution_by_official_category(env):
    client, Session = env
    client.post("/api/ml-categories/import", json={"categories": tree()})
    _official(Session, 3, "MLB1672")          # HDs e SSDs (Informática)
    _official(Session, 3, "MLB1338")          # Academia e Fitness
    # Por categoria: categorias oficiais no cadastro do grupo (com subcategorias).
    client.put("/api/group-schedules/Tech", json={"ml_categories": [{"id": "MLB1648", "include_children": True}]})
    client.put("/api/group-schedules/Gym", json={"ml_categories": [{"id": "MLB1338", "include_children": False}]})
    groups = client.get("/api/group-schedules").json()
    assert [g["ml_categories"][0]["id"] for g in groups if g["group_name"] == "Tech"] == ["MLB1648"]
    plan = _preview(client, strategy="category", groups=[{"group": "Tech"}, {"group": "Gym"}])
    got = {(i["title"].split()[1], i["group"]) for i in plan["items"]}
    assert got == {("MLB1672", "Tech"), ("MLB1338", "Gym")} and plan["messages"] == 6
    # Personalizada: categorias oficiais definidas dentro da campanha.
    custom = _preview(client, strategy="custom", groups=[{"group": "X", "ml_categories": [{"id": "MLB1338"}]}])
    assert {i["title"].split()[1] for i in custom["items"]} == {"MLB1338"}

def test_group_sets_crud_and_isolation(env):
    client, Session = env
    created = client.post("/api/group-sets", json={"name": "Floripa", "groups": ["Floripa 2032", " Floripa  2032 ", "Floripa Ofertas"]})
    assert created.status_code == 201 and created.json()["groups"] == ["Floripa 2032", "Floripa Ofertas"]
    sid = created.json()["id"]
    assert client.post("/api/group-sets", json={"name": "floripa", "groups": ["A"]}).status_code == 409
    assert client.post("/api/group-sets", json={"name": "Vazio", "groups": []}).status_code == 422
    assert client.put(f"/api/group-sets/{sid}", json={"name": "Floripa", "groups": ["A"]}).json()["groups"] == ["A"]
    other = _second_user(Session, client)
    assert other.get("/api/group-sets").json() == []
    assert other.delete(f"/api/group-sets/{sid}").status_code == 404
    assert client.delete(f"/api/group-sets/{sid}").status_code == 204 and client.get("/api/group-sets").json() == []

def test_panel_statuses(env):
    client, Session = env
    _seed(Session, 4, "Academia")
    c = client.post("/api/campaigns", json=_base(groups=[{"group": "A"}], total_limit=3)).json()
    cid = c["id"]
    assert client.post(f"/api/campaigns/{cid}/confirm").json()["display_status"] == "scheduled"   # aguardando execução
    with Session() as db:
        rows = db.query(Publication).filter(Publication.campaign_id == cid).order_by(Publication.scheduled_at).all()
        rows[0].status, rows[0].sent_at = "sent", datetime.now(timezone.utc)
        db.commit()
    assert client.get(f"/api/campaigns/{cid}").json()["display_status"] == "running"
    with Session() as db:
        for p in db.query(Publication).filter(Publication.campaign_id == cid, Publication.status != "sent"):
            p.status = "failed"
        db.commit()
    assert client.get(f"/api/campaigns/{cid}").json()["display_status"] == "completed_with_failures"
    with Session() as db:
        db.query(Publication).filter(Publication.campaign_id == cid).update({"status": "failed"}); db.commit()
    assert client.get(f"/api/campaigns/{cid}").json()["display_status"] == "failed"

def test_full_flow_from_niche_to_queue_without_sending(env):
    """Perfil > nicho > campanha > busca > seleção > grupos (conjunto) > regras > confirmação > fila. Nada é enviado."""
    client, Session = env
    client.post("/api/ml-categories/import", json={"categories": tree()})
    niche = client.post("/api/niches", json={"name": "Informática", "categories": [{"id": "MLB1648", "include_children": True}],
                                              "include_keywords": ["ssd"]}).json()
    gset = client.post("/api/group-sets", json={"name": "Floripa", "groups": ["Floripa 2032", "Floripa Ofertas"]}).json()
    start = datetime.fromisoformat(_base()["start_at"])
    c = client.post("/api/campaigns", json={"name": "Floripa Teste", "niche_ids": [niche["id"]], "ml_categories": niche["categories"],
                                            "include_keywords": ["ssd"], "groups": [{"group": g} for g in gset["groups"]],
                                            "strategy": "balanced", "total_limit": 4, "block_size": 2, "interval_minutes": 30,
                                            "message_gap_seconds": 30, "group_daily_limit": 1, "reuse_days": 3,
                                            "start_at": start.isoformat(), "end_at": (start + timedelta(days=5)).isoformat()}).json()
    cid = c["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"categories": niche["categories"], "keywords": ["ssd"]}).json()
    assert client.get("/api/campaign-searches/due").json()["id"] == s["id"]
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": [_item(n, "MLB1672") for n in range(1, 6)]})
    results = client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results").json()
    assert len(results) == 5
    client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [r["listing_id"] for r in results], "search_id": s["id"]})
    plan = client.post("/api/campaigns/preview", params={"campaign_id": cid}, json={k: v for k, v in c.items() if k in _base() or k in (
        "niche_ids", "ml_categories", "include_keywords", "message_gap_seconds", "group_daily_limit", "reuse_days", "end_at")}).json()
    assert plan["errors"] == [] and plan["messages"] == 4 and plan["matching"] == 5
    confirmed = client.post(f"/api/campaigns/{cid}/confirm").json()
    assert confirmed["display_status"] == "scheduled" and confirmed["pending"] == 4
    with Session() as db:
        pubs = db.query(Publication).filter(Publication.campaign_id == cid).all()
        assert all(p.status == "scheduled" and p.sent_at is None for p in pubs)
        local = sorted(as_local(p.scheduled_at) for p in pubs)
        per_day_group = {}
        for p in pubs:
            k = (as_local(p.scheduled_at).date(), p.group_name)
            per_day_group[k] = per_day_group.get(k, 0) + 1
    assert max(per_day_group.values()) == 1 and local[1] - local[0] == timedelta(seconds=30)
    listed = client.get("/api/campaigns").json()[0]
    assert listed["products_count"] == 5 and listed["niche_names"] == ["Informática"] and listed["end_at"]

def as_local(t):
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).astimezone(ZONE)

def test_send_order_mixes_categories(env):
    """Ao programar, as categorias saem intercaladas (proporcionais), não uma categoria inteira e depois a outra."""
    client, Session = env
    _seed(Session, 6, "Calçados")
    _seed(Session, 3, "Ferramentas")
    _seed(Session, 3, "Academia")
    plan = _preview(client, groups=[{"group": "A"}], total_limit=12)
    order = [i["category"] for i in plan["items"]]
    assert sorted(order) == sorted(["Calçados"] * 6 + ["Ferramentas"] * 3 + ["Academia"] * 3)
    assert all(a != b for a, b in zip(order, order[1:]))                    # nunca a mesma categoria duas vezes seguidas
    assert set(order[:3]) == {"Calçados", "Ferramentas", "Academia"}         # as três aparecem logo no começo
    # Categorias oficiais: agrupa pela categoria escolhida na campanha (subcategorias contam como ela).
    client.post("/api/ml-categories/import", json={"categories": tree()})
    _official(Session, 4, "MLB1672")          # Informática > ... > HDs e SSDs
    _official(Session, 4, "MLB1338")          # Esportes e Fitness > Academia e Fitness
    official = _preview(client, groups=[{"group": "B"}], total_limit=8, product_ids=[],
                        ml_categories=[{"id": "MLB1648"}, {"id": "MLB1276"}], categories=["__nenhuma__"], include_uncategorized=True)
    cats = [i["title"].split()[1] for i in official["items"]]
    assert sorted(cats) == ["MLB1338"] * 4 + ["MLB1672"] * 4 and all(a != b for a, b in zip(cats, cats[1:]))
