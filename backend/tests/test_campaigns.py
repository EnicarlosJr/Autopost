"""Campanhas: segmentação, distribuição entre grupos, ritmo, pausa/retomada e ações em massa."""
import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from app.models.product import Product
from app.models.publication import Publication
from tests.test_publication_flow import env  # noqa: F401  (fixture)

ZONE = ZoneInfo("America/Sao_Paulo")
GROUPS = ["Promoções Gerais", "Ofertas de Tecnologia", "Academia e Suplementos", "Ferramentas e Construção"]

def _seed(Session, n, category, tags=(), start=0, price=50.0):
    with Session() as db:
        for i in range(start, start + n):
            db.add(Product(original_url=f"https://loja.example/{category or 'sem'}/{i}", affiliate_url=f"https://meli.la/{i}",
                           title=f"{category or 'Produto'} {i}", price=price, original_price=price * 2, category=category,
                           tags=json.dumps(list(tags)), status="processed"))
        db.commit()

def _base(**extra):
    tomorrow = (datetime.now(ZONE) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    return {"name": "Teste", "groups": [{"group": g} for g in GROUPS], "strategy": "balanced", "total_limit": 20,
            "block_size": 1, "interval_minutes": 2, "start_at": tomorrow.isoformat(), "start_hour": 8, "end_hour": 22, **extra}

def _preview(client, **extra):
    r = client.post("/api/campaigns/preview", json=_base(**extra))
    assert r.status_code == 200, r.text
    return r.json()

def test_20_products_4_groups_5_each_with_interval(env):
    client, _ = env
    _seed(env[1], 25, "Academia")
    plan = _preview(client)
    assert plan["errors"] == [] and plan["messages"] == 20 and plan["selected"] == 20
    assert {g["group"]: g["count"] for g in plan["per_group"]} == {g: 5 for g in GROUPS}
    times = [datetime.fromisoformat(i["at"]) for i in plan["items"]]
    assert all(b - a == timedelta(minutes=2) for a, b in zip(times, times[1:]))
    assert plan["duration_minutes"] == 38
    # Alterna os grupos (não concentra os 5 primeiros no mesmo grupo).
    assert len({i["group"] for i in plan["items"][:4]}) == 4

def test_per_group_limits_and_no_repeats(env):
    client, _ = env
    _seed(env[1], 10, "Academia")
    plan = _preview(client, groups=[{"group": GROUPS[0], "limit": 2}, {"group": GROUPS[1], "limit": 6}], total_limit=50)
    assert {g["group"]: g["count"] for g in plan["per_group"]} == {GROUPS[0]: 2, GROUPS[1]: 6}
    pairs = [(i["product_id"], i["group"]) for i in plan["items"]]
    assert len(pairs) == len(set(pairs))
    # Sequencial: cada produto vai para todos os grupos, sem repetir no mesmo grupo.
    seq = _preview(client, strategy="sequential", groups=[{"group": GROUPS[0]}, {"group": GROUPS[1]}], total_limit=6)
    assert [i["group"] for i in seq["items"]] == [GROUPS[0], GROUPS[1]] * 3
    assert seq["items"][0]["product_id"] == seq["items"][1]["product_id"]

def test_category_filters_include_and_exclude(env):
    client, Session = env
    _seed(Session, 3, "Academia", tags=["suplemento"])
    _seed(Session, 4, "Ferramentas", tags=["obra"])
    _seed(Session, 5, "Informática", tags=["notebook"])
    _seed(Session, 2, "")
    only_gym = _preview(client, categories=["academia"])          # sem diferença de maiúsculas
    assert only_gym["matching"] == 3 and all(i["category"] == "Academia" for i in only_gym["items"])
    tools_it = _preview(client, categories=["Ferramentas", "Informática"])
    assert tools_it["matching"] == 9
    gym_tools_not_it = _preview(client, categories=["Academia", "Ferramentas", "Informática"], exclude_categories=["Informática"])
    assert gym_tools_not_it["matching"] == 7
    with_uncategorized = _preview(client, categories=["Academia"], include_uncategorized=True)
    assert with_uncategorized["matching"] == 5
    by_tags = _preview(client, tags=["obra", "notebook"], tag_mode="any", exclude_tags=["notebook"])
    assert by_tags["matching"] == 4

def test_custom_and_category_distribution(env):
    client, Session = env
    _seed(Session, 4, "Academia")
    _seed(Session, 4, "Ferramentas")
    custom = _preview(client, strategy="custom", groups=[
        {"group": "Academia e Suplementos", "categories": ["Academia"]},
        {"group": "Ferramentas e Construção", "categories": ["Ferramentas"]}])
    by_group = {}
    for i in custom["items"]:
        by_group.setdefault(i["group"], set()).add(i["category"])
    assert by_group == {"Academia e Suplementos": {"Academia"}, "Ferramentas e Construção": {"Ferramentas"}}
    # Por categoria: usa as categorias do cadastro do grupo.
    client.put("/api/group-schedules/Academia e Suplementos", json={"categories": ["Academia"]})
    cat = _preview(client, strategy="category", groups=[{"group": "Academia e Suplementos"}, {"group": "Ferramentas e Construção"}])
    assert {i["group"] for i in cat["items"]} == {"Academia e Suplementos"} and cat["messages"] == 4
    assert any("já" in w or "produtos para" in w for w in cat["warnings"])

def test_contradictory_settings_are_rejected(env):
    client, _ = env
    _seed(env[1], 3, "Academia")
    assert _preview(client, start_hour=20, end_hour=8)["errors"]
    assert _preview(client, block_size=10, interval_minutes=2)["errors"]       # 10 mensagens não cabem em 2 min
    assert _preview(client, interval_minutes=10, interval_max_minutes=5)["errors"]
    assert _preview(client, weekdays=[])["errors"]
    ok = _preview(client, block_size=3, interval_minutes=10)
    assert ok["errors"] == []
    first = [datetime.fromisoformat(i["at"]) for i in ok["items"][:3]]
    assert [b - a for a, b in zip(first, first[1:])] == [timedelta(seconds=20)] * 2      # mesma execução, 20 s entre mensagens

def test_window_weekdays_daily_limit_and_pauses(env):
    client, _ = env
    _seed(env[1], 30, "Academia")
    plan = _preview(client, total_limit=12, interval_minutes=30, start_hour=9, end_hour=11, daily_limit=3,
                    weekdays=[0, 2, 4], pause_every=2, pause_minutes=60, groups=[{"group": GROUPS[0]}])
    local = [datetime.fromisoformat(i["at"]).astimezone(ZONE) for i in plan["items"]]
    assert len(local) == 12
    assert all(t.weekday() in (0, 2, 4) and 9 <= t.hour < 11 for t in local)
    per_day = {}
    for t in local:
        per_day[t.date()] = per_day.get(t.date(), 0) + 1
    assert max(per_day.values()) <= 3

def test_confirm_pause_resume_cancel_and_history(env):
    client, Session = env
    _seed(Session, 8, "Ferramentas")
    created = client.post("/api/campaigns", json=_base(groups=[{"group": GROUPS[3]}], total_limit=6)).json()
    assert created["display_status"] == "draft"
    confirmed = client.post(f"/api/campaigns/{created['id']}/confirm").json()
    assert confirmed["display_status"] == "scheduled" and confirmed["pending"] == 6 and confirmed["next_send"]
    cid = created["id"]
    # Simula um envio feito pela extensão.
    with Session() as db:
        first = db.query(Publication).filter(Publication.campaign_id == cid).order_by(Publication.scheduled_at).first()
        first.status, first.sent_at = "sent", datetime.now(timezone.utc); db.commit()
        sent_product = first.product_id
    assert client.get(f"/api/campaigns/{cid}").json()["display_status"] == "running"
    # Não dá para editar em execução; pausa e edita.
    assert client.put(f"/api/campaigns/{cid}", json=_base(name="X")).status_code == 409
    paused = client.post(f"/api/campaigns/{cid}/pause").json()
    assert paused["display_status"] == "paused" and paused["counts"]["paused"] == 5
    assert client.get("/api/publications/queue").json() == []
    client.put(f"/api/campaigns/{cid}", json=_base(groups=[{"group": GROUPS[3]}], total_limit=6, interval_minutes=10))
    resumed = client.post(f"/api/campaigns/{cid}/resume").json()
    assert resumed["display_status"] == "running" and resumed["sent"] == 1 and resumed["pending"] == 5
    history = client.get("/api/publications", params={"campaign_id": cid, "limit": 50}).json()
    assert sum(1 for p in history if p["product_id"] == sent_product) == 1     # não repete o que já saiu
    cancelled = client.post(f"/api/campaigns/{cid}/cancel").json()
    assert cancelled["display_status"] == "cancelled" and cancelled["counts"]["cancelled"] == 5
    copy = client.post(f"/api/campaigns/{cid}/duplicate").json()
    assert copy["display_status"] == "draft" and copy["name"].endswith("(cópia)")
    assert client.delete(f"/api/campaigns/{cid}").status_code == 204

def test_manual_selection_and_bulk_product_actions(env):
    client, Session = env
    _seed(Session, 6, "Informática")
    ids = [p["id"] for p in client.get("/api/products", params={"category": "Informática"}).json()]
    plan = _preview(client, product_ids=ids[:2], groups=[{"group": GROUPS[1]}])
    assert plan["matching"] == 2 and plan["messages"] == 2
    assert client.post("/api/products/bulk/update", json={"ids": ids[:3], "category": "Eletrônicos", "add_tags": ["promo"]}).json() == {"updated": 3}
    assert len(client.get("/api/products", params={"tag": "promo"}).json()) == 3
    assert client.post("/api/products/bulk/update", json={"ids": ids[:3], "remove_tags": ["PROMO"]}).json()["updated"] == 3
    assert client.get("/api/products", params={"tag": "promo"}).json() == []
    assert client.post("/api/products/bulk/delete", json={"ids": ids[3:]}).json() == {"deleted": 3, "skipped": 0}
    assert len(client.get("/api/products", params={"category": "Informática"}).json()) == 0

def test_options_and_queue_bulk_cancel(env):
    client, Session = env
    _seed(Session, 2, "Academia", tags=["whey"])
    opts = client.get("/api/campaigns/options").json()
    assert {"name": "Academia", "count": 2} in opts["categories"] and {"name": "whey", "count": 2} in opts["tags"]
    c = client.post("/api/campaigns", json=_base(groups=[{"group": GROUPS[2]}], total_limit=2)).json()
    client.post(f"/api/campaigns/{c['id']}/confirm")
    ids = [p["id"] for p in client.get("/api/publications", params={"campaign_id": c["id"]}).json()]
    assert client.post("/api/publications/bulk/cancel", json={"ids": ids}).json() == {"cancelled": 2}

def test_warns_when_campaign_passes_group_daily_limit(env):
    client, _ = env
    _seed(env[1], 30, "Academia")
    client.put(f"/api/group-schedules/{GROUPS[0]}", json={"group_name": GROUPS[0], "categories": [], "active": True, "start_hour": 8,
                                                          "end_hour": 22, "max_per_day": 12, "gap_minutes": 40, "repost_days": 7})
    plan = _preview(client, groups=[{"group": GROUPS[0]}], total_limit=20, interval_minutes=10)
    assert plan["group_limits"] == [{"group": GROUPS[0], "limit": 12, "max_day": 20}]
    assert any("limite de 12 por dia" in w for w in plan["warnings"])
    # Com "Limite por grupo por dia" = 12, cabe no cadastro e o aviso some (a campanha passa para o dia seguinte).
    plan = _preview(client, groups=[{"group": GROUPS[0]}], total_limit=20, interval_minutes=10, group_daily_limit=12)
    assert plan["group_limits"] == [] and plan["messages"] == 20

def test_many_niche_keywords_are_accepted(env):
    client, _ = env
    words = [f"palavra {i}" for i in range(82)]
    assert client.post("/api/campaigns/preview", json=_base(include_keywords=words)).status_code == 200
