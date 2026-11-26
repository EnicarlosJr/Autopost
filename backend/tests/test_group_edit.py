"""Grupos: renomear e remover do cadastro levando junto publicações, buscas, conjuntos e campanhas."""
from datetime import datetime, timezone
from app.models.publication import Publication
from app.models.product import Product
from tests.test_publication_flow import env  # noqa: F401  (fixture)

SCHEDULE = {"categories": [], "active": True, "start_hour": 8, "end_hour": 22, "max_per_day": 12, "gap_minutes": 40, "repost_days": 7}


def _names(client):
    return [g["group_name"] for g in client.get("/api/group-schedules").json()]


def _publication(Session, group, status, **extra):
    with Session() as db:
        pid = db.query(Product).first().id
        db.add(Publication(product_id=pid, group_name=group, message="x", status=status, **extra)); db.commit()


def test_rename_group_moves_everything(env):
    client, Session = env
    client.put("/api/group-schedules/Antigo", json={"group_name": "Antigo", **SCHEDULE, "max_per_day": 20})
    client.put("/api/group-schedules/Outro", json={"group_name": "Outro", **SCHEDULE})
    _publication(Session, "Antigo", "sent", sent_at=datetime.now(timezone.utc))
    _publication(Session, "Antigo", "scheduled")
    client.post("/api/group-sets", json={"name": "Conjunto", "groups": ["Antigo", "Outro"]})
    assert client.post("/api/group-schedules/Antigo/rename", json={"new_name": "Outro"}).status_code == 409
    r = client.post("/api/group-schedules/Antigo/rename", json={"new_name": "  Novo   nome "})
    assert r.status_code == 200 and r.json()["group_name"] == "Novo nome" and r.json()["max_per_day"] == 20
    assert "Antigo" not in _names(client) and "Novo nome" in _names(client)
    with Session() as db:
        assert {p.group_name for p in db.query(Publication)} == {"Novo nome"}   # histórico vai junto (regra de repostagem)
    assert client.get("/api/group-sets").json()[0]["groups"] == ["Novo nome", "Outro"]


def test_remove_group_asks_before_cancelling_and_does_not_come_back(env):
    client, Session = env
    client.put("/api/group-schedules/Velho", json={"group_name": "Velho", **SCHEDULE})
    _publication(Session, "Velho", "sent", sent_at=datetime.now(timezone.utc))
    _publication(Session, "Velho", "scheduled")
    assert client.get("/api/group-schedules/Velho/usage").json() == {"active": 1, "sending": 0}
    assert client.delete("/api/group-schedules/Velho").status_code == 409
    assert client.delete("/api/group-schedules/Velho", params={"cancel_pending": "true"}).status_code == 204
    # O histórico de enviadas não traz o grupo de volta à lista.
    assert "Velho" not in _names(client)
    with Session() as db:
        assert sorted(p.status for p in db.query(Publication)) == ["cancelled", "sent"]
