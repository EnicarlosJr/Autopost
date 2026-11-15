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
