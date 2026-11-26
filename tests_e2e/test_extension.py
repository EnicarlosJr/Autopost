"""Testes de ponta a ponta da extensão (leitura de preço e envio pelo WhatsApp) com páginas simuladas.

Rodam sem o Autopost no ar e sem internet:
    pip install playwright pytest
    playwright install chromium
    pytest tests_e2e
"""
import json
import re
import shutil
from pathlib import Path
import pytest
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
ML_PAGE = (ROOT / "backend" / "tests" / "fixtures" / "mercadolivre_pdp_pix.html").read_text(encoding="utf-8")
WA_PAGE = (Path(__file__).parent / "whatsapp_mock.html").read_text(encoding="utf-8")
SEARCH_PAGE = (Path(__file__).parent / "mercadolivre_search_mock.html").read_text(encoding="utf-8")
# Página de produto com a barra de afiliados: "Compartilhar" gera o meli.la num campo de texto.
AFFILIATE_BAR = """<nav class="stripe"><button type="button" class="andes-button generate_link_button">Compartilhar</button></nav>
<div id="share"></div><script>
document.querySelector('.generate_link_button').addEventListener('click', () => setTimeout(() => {
  document.getElementById('share').innerHTML = '<textarea class="andes-form-control__field">https://meli.la/2LBkxVC</textarea>';
}, 600));</script>"""
AFFILIATE_PAGE = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + AFFILIATE_BAR, ML_PAGE, count=1)
HTML = "text/html; charset=utf-8"


@pytest.fixture(scope="module")
def browser(tmp_path_factory):
    profile = tmp_path_factory.mktemp("profile")
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(str(profile), channel="chromium", headless=True,
                                                   args=[f"--disable-extensions-except={EXTENSION}", f"--load-extension={EXTENSION}"])
        ctx.route("https://www.mercadolivre.com.br/**", lambda r: r.fulfill(status=200, content_type=HTML, body=ML_PAGE))
        ctx.route("https://web.whatsapp.com/**", lambda r: r.fulfill(status=200, content_type=HTML, body=WA_PAGE))
        ctx.route("https://lista.mercadolivre.com.br/**", lambda r: r.fulfill(status=200, content_type=HTML, body=SEARCH_PAGE))
        ctx.route("https://produto.mercadolivre.com.br/**", lambda r: r.fulfill(status=200, content_type=HTML, body=AFFILIATE_PAGE))
        worker = ctx.service_workers[0] if ctx.service_workers else ctx.wait_for_event("serviceworker")
        yield ctx, worker
        ctx.close()
    shutil.rmtree(profile, ignore_errors=True)


def _tab_id(worker, pattern):
    return worker.evaluate(f"chrome.tabs.query({{url:'{pattern}'}}).then(t => t[0].id)")


def test_reader_gets_previous_price_and_pix_from_mercado_livre(browser):
    ctx, worker = browser
    page = ctx.new_page(); page.goto("https://www.mercadolivre.com.br/moto/up/MLBU1")
    tab = _tab_id(worker, "https://www.mercadolivre.com.br/*")
    data = worker.evaluate(f"chrome.scripting.executeScript({{target:{{tabId:{tab}}}, files:['reader.js']}}).then(r => r[0].result)")
    page.close()
    assert data["price"] == 4435 and data["original_price"] == 7999.9 and data["price_note"] == "no Pix"
    # "ou R$ 4.580 em 10x sem juros": preço no cartão, usado no total da página dos pais.
    assert data["regular_price"] == 4580 and data["price_conditions"] == "no Pix" and data["available"] is True


@pytest.mark.parametrize("group, open_chat, expect", [
    ("Floripa 2032", False, "ok"),                      # nome com caracteres invisíveis no WhatsApp
    ("Floripa 2033", False, "Não encontrei a conversa"),
    ("Floripa 2032", True, "A conversa aberta é"),      # conversa aberta é outra: não envia
])
def test_whatsapp_send_picks_exact_group_or_refuses(browser, group, open_chat, expect):
    ctx, worker = browser
    page = ctx.new_page(); page.goto("https://web.whatsapp.com/")
    if open_chat:
        page.evaluate("openChat('Trabalho')")
    tab = _tab_id(worker, "https://web.whatsapp.com/*")
    script = ("chrome.scripting.executeScript({target:{tabId:%d}, func: self.__autopostTest.sendInWhatsApp, "
              "args:[%s, 'Oferta\\nlinha 2', %s]}).then(r => r[0].result)") % (tab, json.dumps(group), "true" if open_chat else "false")
    result = worker.evaluate(script)
    sent = page.evaluate("window.SENT")
    page.close()
    if expect == "ok":
        assert result["ok"] and sent[0]["chat"].startswith("Floripa") and "Avisos" not in sent[0]["chat"]
    else:
        assert not result["ok"] and expect in result["error"] and sent == []


def test_search_reader_skips_ads_and_reads_cards(browser):
    ctx, worker = browser
    page = ctx.new_page(); page.goto("https://lista.mercadolivre.com.br/parafusadeira")
    tab = _tab_id(worker, "https://lista.mercadolivre.com.br/*")
    data = worker.evaluate(f"chrome.scripting.executeScript({{target:{{tabId:{tab}}}, files:['search_reader.js']}}).then(r => r[0].result)")
    page.close()
    first, second = data["items"]
    assert len(data["items"]) == 2 and not data["blocked"]
    assert first.pop("catalog_product_id") == "MLB30144703"        # link com página de catálogo (/p/)
    assert first == {"external_id": "MLB4268042659", "url": "https://produto.mercadolivre.com.br/MLB-4268042659",
                     "title": "Parafusadeira 48v", "image_url": "https://http2.mlstatic.com/D_1.webp", "seller": "THE BLACK TOOLS",
                     "price": 132.9, "original_price": 259.9, "price_note": "no Pix", "rating": 4.8, "sold": 250000,
                     "free_shipping": True}
    assert second["external_id"] == "MLBU3947202950" and second["url"] == "https://www.mercadolivre.com.br/lanterna-tatica/up/MLBU3947202950"
    assert second["price"] == 1097 and second["rating"] is None and second["sold"] == 1500 and not second["free_shipping"]


def _affiliate(browser, url):
    ctx, worker = browser
    page = ctx.new_page(); page.goto(url)
    tab = _tab_id(worker, url.split("/")[0] + "//" + url.split("/")[2] + "/*")
    result = worker.evaluate(f"chrome.scripting.executeScript({{target:{{tabId:{tab}}}, func: self.__autopostTest.generateAffiliateLink}})"
                             ".then(r => r[0].result)")
    page.close()
    return result


def test_share_button_gives_affiliate_link(browser):
    assert _affiliate(browser, "https://produto.mercadolivre.com.br/MLB-4268042659") == {"link": "https://meli.la/2LBkxVC"}


def test_missing_affiliate_bar_is_reported(browser):
    assert _affiliate(browser, "https://www.mercadolivre.com.br/moto/up/MLBU2") == {"error": "no_affiliate_bar"}


@pytest.mark.parametrize("link, expect", [("https://meli.la/ok1", "com imagem"), ("https://meli.la/fail1", "no_preview")])
def test_whatsapp_waits_for_real_link_preview(browser, link, expect):
    """Cartão provisório (título = o próprio link) não conta como prévia: sem prévia de verdade, não envia."""
    ctx, worker = browser
    page = ctx.new_page(); page.goto("https://web.whatsapp.com/")
    tab = _tab_id(worker, "https://web.whatsapp.com/*")
    script = ("chrome.scripting.executeScript({target:{tabId:%d}, func: self.__autopostTest.sendInWhatsApp, "
              "args:['Floripa 2032', %s, false]}).then(r => r[0].result)") % (tab, json.dumps("Oferta\n" + link))
    result = worker.evaluate(script)
    sent = page.evaluate("window.SENT")
    page.close()
    if expect == "no_preview":
        assert not result["ok"] and result["code"] == "no_preview" and sent == []
    else:
        assert result["ok"] and result["preview"] == expect and len(sent) == 1


def _payload_page():
    """Página no formato atual do Mercado Livre: sem cartões no HTML, só os dados embutidos (com @refs e u)."""
    def card(item_id, title, price, previous=None, ads=False, category="MLB999193"):
        prices = [{"values": [{"type": "price", "key": "previous_price", "price": {"value": previous, "previous": True}}]}] if previous else []
        return {"polycard": {"unique_id": "x", "metadata": {"id": item_id, "url": "www.mercadolivre.com.br/x/p/MLB1", "category_id": category,
                                                            "signal": {"ads": ads, "sales": 777, "official_store": not ads and title.endswith("12kg"), "ship_logistics": "full"}},
                             "pictures": {"pictures": [{"id": "655892-MLB1_092026"}]},
                             "components": [{"type": "title", "title": {"text": title}},
                                            {"type": "seller", "seller": {"values": [{"label": {"text": "CROMMO"}}]}},
                                            {"type": "review_compacted", "review_compacted": {"values": [{"label": {"text": "4.9"}}, {"label": {"text": "| +500 vendidos"}}]}},
                                            {"type": "price", "price": {"price_labels": prices, "current_price": {"value": price}, "pix": "no Pix" if previous else ""}},
                                            {"type": "shipping_v2", "shipping_v2": [{"values": [{"key": "free_shipping_single"}]}]}]}}
    data = {"optimizedResponse": {"results": [card("MLB7579993462", "Kettlebell 12kg", 158.98, 199.9), card("MLB5", "Patrocinado", 10, ads=True),
                                              card("MLB7912900396", "Kettlebell 16kg", 167.22)]}}
    text = "0:" + json.dumps(data, ensure_ascii=False).replace('"pix": ""', '"ref": @12, "empty": u') + "\n"
    return f'<html><body><div id="root"></div><script>_n.ctx.s["nr"].q({json.dumps(text)});</script></body></html>'


def test_search_reader_reads_embedded_payload_when_cards_are_not_rendered(browser):
    ctx, worker = browser
    ctx.route("https://lista.mercadolivre.com.br/kettlebell", lambda r: r.fulfill(status=200, content_type=HTML, body=_payload_page()))
    page = ctx.new_page(); page.goto("https://lista.mercadolivre.com.br/kettlebell")
    tab = _tab_id(worker, "https://lista.mercadolivre.com.br/*")
    data = worker.evaluate(f"chrome.scripting.executeScript({{target:{{tabId:{tab}}}, files:['search_reader.js']}}).then(r => r[0].result)")
    page.close(); ctx.unroute("https://lista.mercadolivre.com.br/kettlebell")
    assert data["source"] == "dados" and [i["external_id"] for i in data["items"]] == ["MLB7579993462", "MLB7912900396"]
    first = data["items"][0]
    assert first == {"external_id": "MLB7579993462", "url": "https://produto.mercadolivre.com.br/MLB-7579993462", "title": "Kettlebell 12kg",
                     "image_url": "https://http2.mlstatic.com/D_NQ_NP_655892-MLB1_092026-O.webp", "seller": "CROMMO",
                     "price": 158.98, "original_price": 199.9, "price_note": "no Pix", "rating": 4.9, "sold": 777,
                     "free_shipping": True, "ml_category_id": "MLB999193", "official_store": True, "fulfillment": True,
                     "catalog_product_id": "MLB1"}


OFFERS = "https://www.mercadolivre.com.br/ofertas?container_id=MLB1599405-1"


def _read_offers(browser, body):
    ctx, worker = browser
    ctx.route("https://www.mercadolivre.com.br/ofertas**", lambda r: r.fulfill(status=200, content_type=HTML, body=body))
    page = ctx.new_page(); page.goto(OFFERS)
    tab = _tab_id(worker, "https://www.mercadolivre.com.br/*")
    data = worker.evaluate(f"chrome.scripting.executeScript({{target:{{tabId:{tab}}}, files:['search_reader.js']}}).then(r => r[0].result)")
    page.close(); ctx.unroute("https://www.mercadolivre.com.br/ofertas**")
    return data


def test_offers_page_reads_cards_from_plain_json(browser):
    # Ofertas do dia: os mesmos cartões "polycard", num JSON comum (sem o formato _n.ctx da busca).
    raw = _payload_page().split('q(', 1)[1].rsplit(');', 1)[0]
    state = json.loads(raw)[2:]
    body = f'<html><body><div id="root"></div><script>window.__PRELOADED_STATE__ = {state};</script></body></html>'
    data = _read_offers(browser, body)
    assert data["source"] == "dados" and [i["external_id"] for i in data["items"]] == ["MLB7579993462", "MLB7912900396"]


def test_offers_page_reads_promotion_item_cards(browser):
    card = ('<li class="promotion-item"><a class="promotion-item__link-container" href="https://produto.mercadolivre.com.br/MLB-123456789-mochila-_JM">'
            '<img src="https://http2.mlstatic.com/a.webp"><p class="promotion-item__title">Mochila Escolar</p>'
            '<span class="andes-money-amount andes-money-amount--previous"><span class="andes-money-amount__fraction">200</span></span>'
            '<span class="andes-money-amount"><span class="andes-money-amount__fraction">149</span><span class="andes-money-amount__cents">90</span></span>'
            '<span class="promotion-item__shipping">Frete grátis</span></a></li>')
    data = _read_offers(browser, f'<html><body><ol>{card}</ol></body></html>')
    assert data["source"] == "ofertas"
    assert data["items"][0] | {"image_url": ""} == {"external_id": "MLB123456789", "url": "https://produto.mercadolivre.com.br/MLB-123456789",
        "title": "Mochila Escolar", "image_url": "", "seller": "", "price": 149.9, "original_price": 200, "price_note": "",
        "rating": None, "sold": None, "free_shipping": True, "catalog_product_id": None}
