"""Padrão do perfil (modelo da mensagem, marca d'água, #publi, selo de desconto) e personalização por campanha."""
from io import BytesIO
from PIL import Image
import app.products.social_image as social
from app.publications.messages import with_disclosure
from tests.test_publication_flow import env, _set_approval  # noqa: F401  (fixture)
from tests.test_campaigns import _base, _seed
from tests.test_image_mode import _photo


def _settings(client, **changes):
    s = client.get("/api/automations/settings").json()
    s.update(changes)
    return client.put("/api/automations/settings", json={k: v for k, v in s.items() if k not in ("id", "name", "default_template", "updated_at")})


def test_with_disclosure_always_on_top_once():
    assert with_disclosure("Oferta", "#publi") == "#publi\n\nOferta"
    assert with_disclosure("#publi\n\nOferta", "#publi") == "#publi\n\nOferta"
    assert with_disclosure("Oferta", "") == "#publi\n\nOferta"


def test_disclosure_goes_out_even_when_text_is_edited(env):
    client, _ = env
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta boa"}).json()
    assert pub["message"] == "Oferta boa" and pub["outgoing_message"] == "#publi\n\nOferta boa"
    edited = client.patch(f"/api/publications/{pub['id']}", json={"message": "Texto sem nada"}).json()
    assert edited["outgoing_message"].startswith("#publi\n\n")
    assert _settings(client, disclosure_text="#publi | link de afiliado").status_code == 200
    assert client.get(f"/api/publications/{pub['id']}").json()["outgoing_message"].startswith("#publi | link de afiliado\n\n")
    bad = _settings(client, disclosure_text="Patrocinado")
    assert bad.status_code == 422 and "#publi" in bad.json()["detail"]
    assert _settings(client, disclosure_text="").json()["disclosure_text"] == "#publi"


def test_campaign_uses_profile_style_unless_customized(env, monkeypatch, tmp_path):
    client, Session = env
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(social, "best_source", lambda url, pid: _photo())
    calls = []
    real = social.social_image
    monkeypatch.setattr(social, "social_image", lambda p, *a: (calls.append(a), real(p, *a))[1])
    _seed(Session, 2, "Academia")
    _set_approval(Session, False)
    _settings(client, message_template="PERFIL {titulo}\n{link}", watermark_text="Base 92", watermark_handle="@base92")
    perfil = client.post("/api/campaigns", json=_base(groups=[{"group": "A"}], total_limit=1, send_mode="image",
                                                      watermark_text="Ignorado", custom_style=False)).json()
    propria = client.post("/api/campaigns", json=_base(groups=[{"group": "B"}], total_limit=1, send_mode="image", custom_style=True,
                                                       message_template="CAMPANHA {titulo} {preco_por}\n{link}",
                                                       watermark_text="Grupo B", watermark_handle="@b")).json()
    assert propria["custom_style"] is True and propria["message_template"].startswith("CAMPANHA")
    assert client.post("/api/campaigns", json=_base(message_template="{inexistente}")).status_code == 422
    for c in (perfil, propria):
        client.post(f"/api/campaigns/{c['id']}/confirm")
    p1 = client.get("/api/publications", params={"campaign_id": perfil["id"]}).json()[0]
    p2 = client.get("/api/publications", params={"campaign_id": propria["id"]}).json()[0]
    assert p1["message"].startswith("PERFIL") and p2["message"].startswith("CAMPANHA")
    assert client.get(f"/api/publications/{p1['id']}/image").status_code == 200
    assert calls[-1] == ("Base 92", "@base92", "#publi", 50)          # preço 50, antes 100: 50% OFF
    assert client.get(f"/api/publications/{p2['id']}/image").status_code == 200
    assert calls[-1][:2] == ("Grupo B", "@b")
    _settings(client, show_discount=False)
    client.get(f"/api/publications/{p1['id']}/image")
    assert calls[-1][3] is None
    # Preço novo: o texto padrão de cada campanha é refeito com o próprio modelo (não vira "editado à mão").
    client.patch(f"/api/products/{p2['product_id']}", json={"price": 40})
    again = client.get(f"/api/publications/{p2['id']}").json()
    assert again["message"].startswith("CAMPANHA") and "40,00" in again["message"] and again["status"] != "failed"


def test_photo_has_publi_badge_and_discount_sticker():
    img = Image.open(BytesIO(social.compose(_photo(), "Base 92", "@base92", "#publi", 40)))
    assert img.size == (1080, 1080)
    dark = img.getpixel((40, 50))                                        # selo #publi no canto superior esquerdo
    yellow = img.getpixel((1080 - 30 - 88, 48))                          # topo do selo de desconto
    assert sum(dark) < 150 and yellow[0] > 200 and yellow[1] > 150 and yellow[2] < 120
