"""Catálogo oficial do Mercado Livre, favoritas e nichos (com isolamento entre perfis)."""
import requests
from app.core.security import create_access_token, hash_password
from app.models.catalog import MlCategory
from app.models.user import User
import app.catalog.service as catalog
from tests.test_publication_flow import env  # noqa: F401  (fixture)

def tree(extra=0, drop=()):
    """Árvore sintética no formato enxuto da extensão: 2 raízes, filhos e netos (60+ categorias)."""
    items = [{"id": "MLB1648", "name": "Informática", "parent_id": None, "total_items": 900, "children": 2},
             {"id": "MLB1276", "name": "Esportes e Fitness", "parent_id": None, "total_items": 500, "children": 1},
             {"id": "MLB430598", "name": "Armazenamento", "parent_id": "MLB1648", "total_items": 300, "children": 1},
             {"id": "MLB1672", "name": "HDs e SSDs", "parent_id": "MLB430598", "total_items": 200, "children": 0},
             {"id": "MLB1712", "name": "Componentes para PC", "parent_id": "MLB1648", "total_items": 100, "children": 0},
             {"id": "MLB1338", "name": "Academia e Fitness", "parent_id": "MLB1276", "total_items": 80, "children": 0}]
    items += [{"id": f"MLB9{i:04d}", "name": f"Outra {i}", "parent_id": "MLB1276", "total_items": 1, "children": 0} for i in range(60 + extra)]
    return [i for i in items if i["id"] not in drop]

def _second_user(Session, client):
    with Session() as db:
        db.add(User(email="outra@pessoa", password_hash=hash_password("senha-forte-456"), is_active=True)); db.commit()
    other = type(client)(client.app)
    other.headers["Authorization"] = f"Bearer {create_access_token('outra@pessoa')}"
    return other

def test_import_tree_paths_search_and_children(env):
    client, Session = env
    r = client.post("/api/ml-categories/import", json={"categories": tree()})
    assert r.status_code == 200 and r.json()["roots"] == 2 and r.json()["total"] == 66
    roots = client.get("/api/ml-categories/children").json()
    assert [c["name"] for c in roots] == ["Esportes e Fitness", "Informática"]
    kids = client.get("/api/ml-categories/children", params={"parent": "MLB1648"}).json()
    assert {c["id"] for c in kids} == {"MLB430598", "MLB1712"}
    ssd = client.get("/api/ml-categories/search", params={"q": "hds e ssds"}).json()[0]
    assert ssd["path"] == "Informática > Armazenamento > HDs e SSDs" and ssd["is_leaf"] and ssd["path_ids"] == ["MLB1648", "MLB430598", "MLB1672"]
    assert client.get("/api/ml-categories/search", params={"q": "informatica"}).json()[0]["id"] == "MLB1648"   # sem acento
    assert client.get("/api/ml-categories/search", params={"q": "mlb1672"}).json()[0]["name"] == "HDs e SSDs"
    assert client.get("/api/ml-categories/status").json()["total"] == 66
    with Session() as db:
        assert catalog.subtree_ids(db, "MLB1648") == {"MLB1648", "MLB430598", "MLB1672", "MLB1712"}

def test_resync_inactivates_removed_and_rejects_incomplete(env):
    client, Session = env
    client.post("/api/ml-categories/import", json={"categories": tree()})
    r = client.post("/api/ml-categories/import", json={"categories": tree(drop=("MLB1712",))})
    assert r.json()["inactivated"] == 1
    with Session() as db:
        assert db.get(MlCategory, "MLB1712").active is False
    assert client.get("/api/ml-categories/search", params={"q": "componentes"}).json() == []
    assert client.post("/api/ml-categories/import", json={"categories": tree()[:10]}).status_code == 422

def test_server_sync_failure_is_logged_and_points_to_browser(env, monkeypatch):
    client, _ = env
    class Blocked:
        status_code, text = 403, '{"blocked_by":"PolicyAgent"}'
    monkeypatch.setattr(catalog.requests, "get", lambda *a, **k: Blocked())
    r = client.post("/api/ml-categories/sync")
    assert r.status_code == 502 and r.json()["detail"]["code"] == "use_browser"
    def down(*a, **k): raise requests.ConnectionError("sem rede")
    monkeypatch.setattr(catalog.requests, "get", down)
    assert client.post("/api/ml-categories/sync").status_code == 502
    logs = client.get("/api/automations/logs").json()
    details = [l["detail"] for l in (logs if isinstance(logs, list) else logs.get("items", []))]
    assert any("403" in d for d in details) and any("Sem conexão" in d for d in details)

def test_server_sync_success(env, monkeypatch):
    client, _ = env
    api = {f"MLB{i}": {"name": f"Cat {i}", "path_from_root": [{"id": "MLB1"}] + ([{"id": f"MLB{i}"}] if i != 1 else []),
                       "children_categories": [] if i != 1 else [{"id": "x"}], "total_items_in_this_category": i} for i in range(1, 70)}
    class Ok:
        status_code = 200
        def json(self): return api
    monkeypatch.setattr(catalog.requests, "get", lambda *a, **k: Ok())
    r = client.post("/api/ml-categories/sync").json()
    assert r["total"] == 69 and r["roots"] == 1

def test_favorites_and_niches_crud_duplicate(env):
    client, _ = env
    client.post("/api/ml-categories/import", json={"categories": tree()})
    assert client.put("/api/ml-categories/favorites/MLB1672").status_code == 204
    assert client.put("/api/ml-categories/favorites/MLB0").status_code == 404
    assert [c["id"] for c in client.get("/api/ml-categories/favorites").json()] == ["MLB1672"]
    assert client.get("/api/ml-categories/search", params={"q": "ssd"}).json()[0]["favorite"] is True
    body = {"name": "Informática", "description": "PC e periféricos", "categories": [{"id": "MLB1648", "include_children": True}],
            "tags": ["tecnologia", "Tecnologia"], "include_keywords": ["ssd", "memória ram"], "exclude_keywords": ["usado", "recondicionado"]}
    n = client.post("/api/niches", json=body).json()
    assert n["tags"] == ["tecnologia"] and n["categories"][0]["path"] == "Informática" and n["include_keywords"] == ["ssd", "memória ram"]
    assert client.post("/api/niches", json=body).status_code == 409                       # nome repetido
    assert client.post("/api/niches", json={**body, "name": "X", "categories": [{"id": "MLB0"}]}).status_code == 422
    copy = client.post(f"/api/niches/{n['id']}/duplicate").json()
    assert copy["name"] == "Informática (cópia)" and copy["categories"][0]["id"] == "MLB1648"
    upd = client.put(f"/api/niches/{copy['id']}", json={**body, "name": "Games", "categories": [{"id": "MLB1672", "include_children": False}]}).json()
    assert upd["name"] == "Games" and upd["categories"][0]["include_children"] is False
    assert client.post(f"/api/niches/{n['id']}/favorite").json()["favorite"] is True
    assert [x["name"] for x in client.get("/api/niches").json()] == ["Informática", "Games"]   # favoritos primeiro
    assert client.delete(f"/api/niches/{copy['id']}").status_code == 204
    client.delete("/api/ml-categories/favorites/MLB1672")
    assert client.get("/api/ml-categories/favorites").json() == []

def test_profiles_cannot_see_each_other(env):
    client, Session = env
    client.post("/api/ml-categories/import", json={"categories": tree()})
    mine = client.post("/api/niches", json={"name": "Meu nicho", "categories": [{"id": "MLB1648"}]}).json()
    client.put("/api/ml-categories/favorites/MLB1648")
    other = _second_user(Session, client)
    assert other.get("/api/niches").json() == []
    assert other.get(f"/api/niches/{mine['id']}").status_code == 404
    assert other.put(f"/api/niches/{mine['id']}", json={"name": "Roubado"}).status_code == 404
    assert other.delete(f"/api/niches/{mine['id']}").status_code == 404
    assert other.get("/api/ml-categories/favorites").json() == []
    # O catálogo é global: os dois enxergam as mesmas categorias oficiais.
    assert len(other.get("/api/ml-categories/children").json()) == 2
    assert other.post("/api/niches", json={"name": "Meu nicho"}).status_code == 201       # mesmo nome, outro perfil
