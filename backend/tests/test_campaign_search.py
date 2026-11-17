"""Busca de produtos dentro da campanha: fila da extensão, filtro por categoria oficial, seleção, histórico e isolamento."""
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest
import app.searches.service as search_service
from tests.test_publication_flow import env  # noqa: F401  (fixture)
from tests.test_catalog import tree, _second_user

@pytest.fixture(autouse=True)
def _no_downloads(monkeypatch):
    monkeypatch.setattr(search_service, "download_product_image", lambda url, pid: "")

def _setup(client):
    client.post("/api/ml-categories/import", json={"categories": tree()})
    niche = client.post("/api/niches", json={"name": "Informática", "categories": [{"id": "MLB1648", "include_children": True}],
                                              "include_keywords": ["ssd", "memória ram"], "exclude_keywords": ["usado"]}).json()
    tomorrow = (datetime.now(ZoneInfo("America/Sao_Paulo")) + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    camp = client.post("/api/campaigns", json={"name": "Floripa Teste", "groups": [{"group": "Floripa 2032"}], "total_limit": 10,
                                               "interval_minutes": 20, "start_at": tomorrow.isoformat()}).json()
    return niche, camp

def _item(n, cat, **extra):
    return {"external_id": f"MLB{n}", "url": f"https://produto.mercadolivre.com.br/MLB-{n}", "term": "ssd", "title": f"SSD Kingston {n}",
            "price": 199.9, "original_price": 299.9, "rating": 4.7, "sold": 5000, "free_shipping": True, "ml_category_id": cat, **extra}

def test_full_flow_niche_search_select_and_plan(env):
    client, _ = env
    niche, camp = _setup(client)
    cid = camp["id"]
    defaults = client.get(f"/api/campaigns/{cid}/niche-defaults", params={"niche_ids": str(niche["id"])}).json()
    assert defaults["categories"][0]["id"] == "MLB1648" and defaults["include_keywords"] == ["ssd", "memória ram"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"niche_id": niche["id"], "categories": defaults["categories"],
                    "keywords": defaults["include_keywords"], "exclude_keywords": defaults["exclude_keywords"], "filters": {"min_discount": 20}}).json()
    assert s["status"] == "queued" and s["niche_name"] == "Informática" and s["terms"] == ["ssd", "memória ram"]
    due = client.get("/api/campaign-searches/due").json()
    assert due["id"] == s["id"] and due["terms"][1]["url"] == "https://lista.mercadolivre.com.br/mem%C3%B3ria-ram"
    assert client.get("/api/campaign-searches/due").json() is None                       # reservada
    items = [_item(1, "MLB1672"), _item(2, "MLB1338"), _item(3, None), _item(4, "MLB1712", title="SSD usado"),
             _item(5, "MLB1712", original_price=210), _item(1, "MLB1672", term="memória ram"), {"external_id": "", "url": ""}]
    done = client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": items}).json()
    assert done["status"] == "done" and done["result_count"] == 5 and done["matched_count"] == 1
    results = client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results", params={"matched": "all"}).json()
    reasons = {r["external_id"]: r["reason"] for r in results}
    assert reasons == {"MLB1": "", "MLB2": "fora das categorias (Academia e Fitness)", "MLB3": "categoria não identificada",
                       "MLB4": 'contém "usado"', "MLB5": "desconto menor que 20%"}
    good = [r for r in results if r["matched"]][0]
    assert good["category_path"] == "Informática > Armazenamento > HDs e SSDs" and not good["in_campaign"]
    # Achados da busca da campanha não aparecem na tela Achados (que é das buscas automáticas).
    assert client.get("/api/listings").json() == []
    added = client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [good["listing_id"]], "search_id": s["id"]}).json()
    assert added == {"added": 1, "skipped": 0}
    assert client.post(f"/api/campaigns/{cid}/products", json={"listing_ids": [good["listing_id"]]}).json() == {"added": 0, "skipped": 1}
    prods = client.get(f"/api/campaigns/{cid}/products").json()
    assert prods[0]["ml_category_id"] == "MLB1672" and prods[0]["tags"] == ["ssd"] and prods[0]["category_name"] == "HDs e SSDs"
    assert client.get(f"/api/campaigns/{cid}/searches/{s['id']}/results").json()[0]["in_campaign"] is True
    history = client.get(f"/api/campaigns/{cid}/searches").json()
    assert history[0]["added_count"] == 1 and history[0]["filters"]["min_discount"] == 20
    # O planejamento usa só os produtos escolhidos.
    detail = client.get(f"/api/campaigns/{cid}").json()
    assert detail["products_count"] == 1 and detail["searches_count"] == 1
    cfg = {k: detail[k] for k in ("name", "groups", "total_limit", "interval_minutes", "start_at", "strategy")}
    plan = client.post("/api/campaigns/preview", params={"campaign_id": cid}, json=cfg).json()
    assert plan["matching"] == 1 and plan["messages"] == 1
    confirmed = client.post(f"/api/campaigns/{cid}/confirm").json()
    assert confirmed["display_status"] == "scheduled" and confirmed["pending"] == 1
    client.post(f"/api/campaigns/{cid}/products/remove", json={"product_ids": [prods[0]["product_id"]]})
    assert client.get(f"/api/campaigns/{cid}/products").json() == []

def test_no_results_failure_and_repeat(env):
    client, _ = env
    _, camp = _setup(client)
    cid = camp["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"keywords": ["monitor"]}).json()
    client.get("/api/campaign-searches/due")
    r = client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": []}).json()
    assert r["status"] == "no_results"
    s2 = client.post(f"/api/campaigns/{cid}/searches/{s['id']}/repeat").json()
    assert s2["status"] == "queued" and s2["keywords"] == ["monitor"] and s2["id"] != s["id"]
    client.get("/api/campaign-searches/due")
    failed = client.post(f"/api/campaign-searches/{s2['id']}/results", json={"items": [], "error": "O Mercado Livre pediu verificação."}).json()
    assert failed["status"] == "failed" and "verificação" in failed["error"]
    # Só categorias: as palavras de busca são os nomes das categorias.
    s3 = client.post(f"/api/campaigns/{cid}/searches", json={"categories": [{"id": "MLB1672"}]}).json()
    assert s3["terms"] == ["HDs e SSDs"]

def test_validation_and_uncategorized_option(env):
    client, _ = env
    _, camp = _setup(client)
    cid = camp["id"]
    assert client.post(f"/api/campaigns/{cid}/searches", json={}).status_code == 422
    assert client.post(f"/api/campaigns/{cid}/searches", json={"categories": [{"id": "MLB0"}]}).status_code == 422
    s = client.post(f"/api/campaigns/{cid}/searches", json={"categories": [{"id": "MLB1648"}], "keywords": ["ssd"],
                                                            "filters": {"allow_uncategorized": True}}).json()
    client.get("/api/campaign-searches/due")
    r = client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": [_item(7, None)]}).json()
    assert r["matched_count"] == 1

def test_other_profile_cannot_touch_campaign(env):
    client, Session = env
    niche, camp = _setup(client)
    cid = camp["id"]
    s = client.post(f"/api/campaigns/{cid}/searches", json={"keywords": ["ssd"]}).json()
    other = _second_user(Session, client)
    assert other.get("/api/campaigns").json() == []
    for call in (lambda: other.get(f"/api/campaigns/{cid}"), lambda: other.get(f"/api/campaigns/{cid}/searches"),
                 lambda: other.post(f"/api/campaigns/{cid}/searches", json={"keywords": ["x"]}),
                 lambda: other.get(f"/api/campaigns/{cid}/searches/{s['id']}/results"),
                 lambda: other.post(f"/api/campaigns/{cid}/products", json={"product_ids": [1]}),
                 lambda: other.post(f"/api/campaign-searches/{s['id']}/results", json={"items": []}),
                 lambda: other.post(f"/api/campaigns/{cid}/pause")):
        assert call().status_code == 404
    assert other.get("/api/campaign-searches/due").json() is None                        # não pega a fila do outro
    # Nicho de outro perfil não pode ser usado.
    other_camp = other.post("/api/campaigns", json={"name": "Minha", "groups": [{"group": "G"}]}).json()
    assert other.post(f"/api/campaigns/{other_camp['id']}/searches", json={"niche_id": niche["id"], "keywords": ["x"]}).status_code == 404
    assert other.get(f"/api/campaigns/{other_camp['id']}/niche-defaults", params={"niche_ids": str(niche["id"])}).json()["niche_ids"] == []

def test_gender_filter_adds_term_and_rejects_other_audience(env):
    """Público masculino: "masculino" entra na busca e anúncios femininos ficam de fora (unissex passa)."""
    client, Session = env
    _setup(client)
    camp = client.post("/api/campaigns", json={"name": "Gênero", "groups": [{"group": "G"}]}).json()
    niche = client.post("/api/niches", json={"name": "Homens", "gender": "male", "include_keywords": ["tênis"]}).json()
    assert niche["gender"] == "male"
    defaults = client.get(f"/api/campaigns/{camp['id']}/niche-defaults", params={"niche_ids": str(niche["id"])}).json()
    assert defaults["gender"] == "male"
    s = client.post(f"/api/campaigns/{camp['id']}/searches", json={"keywords": ["tênis", "Perfume Masculino", "relógio feminino"],
                                                                   "filters": {"gender": "male"}}).json()
    assert s["terms"] == ["tênis masculino", "Perfume Masculino", "relógio feminino"]   # quem já cita o público fica como está
    assert client.get("/api/campaign-searches/due").json()["id"] == s["id"]
    items = [_item(11, None, title="Tênis Masculino Corrida"), _item(12, None, title="Tênis Feminino Casual"),
             _item(13, None, title="Tênis Unissex Branco"), _item(14, None, title="Tênis Esportivo Preto"),
             _item(15, None, title="Sandália Mulher Verão")]
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": items})
    reasons = {r["external_id"]: r["reason"] for r in client.get(f"/api/campaigns/{camp['id']}/searches/{s['id']}/results",
                                                                params={"matched": "all"}).json()}
    assert reasons == {"MLB11": "", "MLB12": "para o público feminino", "MLB13": "", "MLB14": "", "MLB15": "para o público feminino"}
    # Modo estrito: só passa quem diz o público ou unissex.
    strict = client.post(f"/api/campaigns/{camp['id']}/searches", json={"keywords": ["tênis"], "filters": {"gender": "male", "gender_strict": True}}).json()
    client.get("/api/campaign-searches/due")
    client.post(f"/api/campaign-searches/{strict['id']}/results", json={"items": items})
    got = {r["external_id"]: r["reason"] for r in client.get(f"/api/campaigns/{camp['id']}/searches/{strict['id']}/results",
                                                            params={"matched": "all"}).json()}
    assert got["MLB14"] == "não diz que é masculino ou unissex" and got["MLB11"] == "" and got["MLB13"] == ""

def test_trust_filters_reject_low_quality_listings(env):
    """Confiabilidade: termos de baixa qualidade, poucas vendas e exigência de loja oficial ou Full."""
    client, _ = env
    _setup(client)
    camp = client.post("/api/campaigns", json={"name": "Confiável", "groups": [{"group": "G"}]}).json()
    s = client.post(f"/api/campaigns/{camp['id']}/searches", json={"keywords": ["pulseira"], "filters": {
        "trust": "high", "min_sold": 500, "official_or_full": True, "exclude_suspicious": True}}).json()
    client.get("/api/campaign-searches/due")
    items = [_item(21, None, title="Pulseira Grumet Banhada A Ouro 18k", sold=5000, fulfillment=True),
             _item(22, None, title="Pulseira Prata 925 Legítima", sold=100, official_store=True),
             _item(23, None, title="Pulseira Couro Masculina", sold=2000),
             _item(24, None, title="Relógio Casio Original", sold=3000, official_store=True),
             _item(25, None, title="Tênis 1ª Linha Premium", sold=9000, fulfillment=True)]
    client.post(f"/api/campaign-searches/{s['id']}/results", json={"items": items})
    rows = client.get(f"/api/campaigns/{camp['id']}/searches/{s['id']}/results", params={"matched": "all"}).json()
    reasons = {r["external_id"]: r["reason"] for r in rows}
    assert reasons == {"MLB21": 'baixa confiabilidade ("banhada")', "MLB22": "menos de 500 vendidos",
                       "MLB23": "não é loja oficial nem Full", "MLB24": "", "MLB25": 'baixa confiabilidade ("1a linha")'}
    assert next(r for r in rows if r["external_id"] == "MLB24")["official_store"] is True
