"""Envio "foto + texto": imagem padronizada 1080x1080 com marca d'água e forma de envio por campanha."""
from io import BytesIO
from PIL import Image
import app.products.social_image as social
from tests.test_publication_flow import env, _set_approval  # noqa: F401  (fixture)
from tests.test_campaigns import _base, _seed

def _photo(w=600, h=300):
    img = Image.new("RGB", (w + 200, h + 200), (255, 255, 255))      # bordas brancas que devem ser cortadas
    img.paste(Image.new("RGB", (w, h), (200, 30, 30)), (100, 100))
    return img

def test_candidates_prefer_largest_mercado_livre_version():
    url = "https://http2.mlstatic.com/D_NQ_NP_655892-MLB117083392777_092026-O.webp"
    got = social.candidates(url)
    assert got[0] == "https://http2.mlstatic.com/D_NQ_NP_2X_655892-MLB117083392777_092026-F.webp" and got[-1] == url
    assert social.candidates("https://loja.example/foto.jpg") == ["https://loja.example/foto.jpg"]

def test_compose_is_square_trimmed_and_has_watermark_band():
    plain = Image.open(BytesIO(social.compose(_photo())))
    assert plain.size == (1080, 1080)
    # Produto (vermelho) ocupa a largura útil inteira depois do corte das bordas brancas.
    row = [plain.getpixel((x, 540)) for x in range(1080)]
    red = [x for x, p in enumerate(row) if p[0] > 150 and p[1] < 90]
    assert red[0] <= social.MARGIN + 20 and red[-1] >= 1080 - social.MARGIN - 21
    marked = Image.open(BytesIO(social.compose(_photo(), "Base 92 | Achados", "@base92")))
    bottom = marked.getpixel((10, 1070))
    assert bottom == social.BAND_COLOR or sum(abs(a - b) for a, b in zip(bottom, social.BAND_COLOR)) < 12

def test_campaign_send_mode_image_endpoint_and_claim(env, monkeypatch, tmp_path):
    client, Session = env
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    monkeypatch.setattr(social, "best_source", lambda url, pid: _photo())
    _seed(Session, 2, "Academia")
    _set_approval(Session, False)
    c = client.post("/api/campaigns", json=_base(groups=[{"group": "G"}], total_limit=1, send_mode="image",
                                                watermark_text="Base 92", watermark_handle="@base92")).json()
    assert c["send_mode"] == "image" and c["watermark_handle"] == "@base92"
    assert client.put(f"/api/campaigns/{c['id']}", json=_base(send_mode="foto")).status_code == 422
    client.post(f"/api/campaigns/{c['id']}/confirm")
    pub = client.get("/api/publications", params={"campaign_id": c["id"]}).json()[0]
    assert pub["send_mode"] == "image"
    r = client.get(f"/api/publications/{pub['id']}/image")
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    assert Image.open(BytesIO(r.content)).size == (1080, 1080)
    assert list(tmp_path.joinpath("social").glob("*.jpg"))                 # fica em cache
    # Publicação avulsa continua no modo prévia do link.
    avulsa = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    assert avulsa["send_mode"] == "preview"

def test_manual_offers_use_settings_default_and_per_publication_choice(env, monkeypatch, tmp_path):
    """Ofertas avulsas: padrão nas Configurações (com marca d'água) e escolha por publicação."""
    client, Session = env
    monkeypatch.setenv("MEDIA_DIR", str(tmp_path))
    calls = []
    real = social.social_image
    monkeypatch.setattr(social, "best_source", lambda url, pid: _photo())
    monkeypatch.setattr(social, "social_image", lambda p, t="", h="", *more: (calls.append((t, h)), real(p, t, h, *more))[1])
    settings = client.get("/api/automations/settings").json()
    settings.update(send_mode="image", watermark_text="Base 92", watermark_handle="@base92")
    saved = client.put("/api/automations/settings", json={k: v for k, v in settings.items()
                                                         if k not in ("id", "name", "default_template", "updated_at")}).json()
    assert saved["send_mode"] == "image" and saved["watermark_handle"] == "@base92"
    pub = client.post("/api/publications", json={"product_id": 1, "message": "Oferta"}).json()
    assert pub["send_mode"] == "image" and pub["send_mode_choice"] is None
    assert client.get(f"/api/publications/{pub['id']}/image").status_code == 200 and calls[-1] == ("Base 92", "@base92")
    # Só esta publicação vai como texto com prévia; "default" volta ao padrão.
    assert client.patch(f"/api/publications/{pub['id']}", json={"send_mode": "preview"}).json()["send_mode"] == "preview"
    assert client.patch(f"/api/publications/{pub['id']}", json={"send_mode": "default"}).json()["send_mode"] == "image"
    texto = client.post("/api/publications", json={"product_id": 2, "message": "Outra", "send_mode": "preview"}).json() \
        if client.get("/api/products/2").status_code == 200 else None
    if texto:
        assert texto["send_mode"] == "preview"
    assert client.get("/api/automations/sample-image", params={"product_id": 1, "title": "X", "handle": ""}).status_code == 200
