from bs4 import BeautifulSoup
from app.products import extractor
from app.products.extractor import _jsonld_product, _number, _product_values

def test_price_parser_uses_confirmed_json_ld_values():
    soup=BeautifulSoup('<script type="application/ld+json">{"@type":"Product","offers":{"price":"129,90","highPrice":"199.90","availability":"https://schema.org/InStock"}}</script>','html.parser')
    current,original,availability=_product_values(soup,lambda *keys: "")
    assert current == 129.9
    assert original == 199.9
    assert availability == "InStock"

def test_number_rejects_unparseable_prices():
    assert _number("consulte a loja") is None

def test_open_graph_meta_is_read_even_without_children():
    soup=BeautifulSoup('<meta property="og:title" content="Produto"><meta property="og:price:amount" content="49,90">','html.parser')
    def meta(*keys):
        for key in keys:
            tag=soup.find("meta",attrs={"property":key})
            if tag is None: tag=soup.find("meta",attrs={"name":key})
            if tag is not None and tag.get("content"): return tag["content"].strip()
        return ""
    assert meta("og:title")=="Produto"
    assert _product_values(soup,meta)[0]==49.9

def test_json_ld_product_name_description_image_and_seller():
    soup=BeautifulSoup('<script type="application/ld+json">{"@type":"Product","name":"Cafeteira","description":"Prepara café","image":"/cafeteira.jpg","offers":{"seller":{"name":"Loja Centro"}}}</script>','html.parser')
    values=_jsonld_product(soup)
    assert values=={"name":"Cafeteira","description":"Prepara café","image":"/cafeteira.jpg","seller":"Loja Centro"}

def test_extract_product_reads_title_price_and_resolves_image(monkeypatch):
    class Response:
        is_redirect=False
        text='<title>Produto da Loja</title><meta property="og:image" content="/images/p.jpg"><meta property="product:price:amount" content="79,90"><meta property="og:description" content="Descrição real">'
        def raise_for_status(self): pass
    monkeypatch.setattr(extractor,"_validate_public_url",lambda url:None)
    monkeypatch.setattr(extractor.requests,"get",lambda *args,**kwargs:Response())
    result=extractor.extract_product("https://loja.example/item")
    assert result["title"]=="Produto da Loja"
    assert result["image_url"]=="https://loja.example/images/p.jpg"
    assert result["price"]==79.9
    assert result["description"]=="Descrição real"



def _fake_page(monkeypatch, html):
    class Response:
        is_redirect=False
        text=html
        def raise_for_status(self): pass
    monkeypatch.setattr(extractor,"_validate_public_url",lambda url:None)
    monkeypatch.setattr(extractor.requests,"get",lambda *args,**kwargs:Response())

def test_json_ld_strikethrough_price_is_the_previous_price():
    soup=BeautifulSoup('<script type="application/ld+json">{"@type":"Product","offers":{"price":"80.00","priceSpecification":[{"priceType":"https://schema.org/StrikethroughPrice","price":"120.00"}]}}</script>','html.parser')
    current,original,_=_product_values(soup,lambda *keys:"")
    assert (current,original)==(80.0,120.0)

def test_amazon_list_price(monkeypatch):
    html='<span id="productTitle">Fone</span><div id="corePriceDisplay_desktop_feature_div"><span class="priceToPay"><span class="a-offscreen">R$ 149,90</span></span><span class="a-price a-text-price"><span class="a-offscreen">R$ 299,00</span></span></div>'
    _fake_page(monkeypatch, html)
    result=extractor.extract_product("https://www.amazon.com.br/dp/X")
    assert (result["price"],result["original_price"])==(149.9,299.0)

def test_previous_price_lower_than_current_is_discarded(monkeypatch):
    html='<div data-testid="price-original">R$ 50,00</div><div data-testid="price-value">R$ 80,00</div>'
    _fake_page(monkeypatch, html)
    result=extractor.extract_product("https://loja.example/p")
    assert result["price"]==80.0 and result["original_price"] is None

def test_number_handles_brazilian_thousands():
    assert _number("R$ 1.299") == 1299.0
    assert _number("1.299,90") == 1299.9
    assert _number("193.9") == 193.9

