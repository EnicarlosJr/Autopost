from urllib.parse import urljoin, urlparse
import json
import ipaddress
import re
import socket
import requests
from bs4 import BeautifulSoup

class ProductVerificationRequired(ValueError):
    """The marketplace served a human verification page instead of a product."""

def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must use HTTP or HTTPS")
    if parsed.username or parsed.password:
        raise ValueError("URLs containing credentials are not allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, None)
    except OSError as exc:
        raise ValueError("Could not resolve product host") from exc
    for item in addresses:
        address = ipaddress.ip_address(item[4][0])
        if not address.is_global:
            raise ValueError("Private network URLs are not allowed")

MAX_HTML_BYTES = 3_000_000

def _close(response) -> None:
    close = getattr(response, "close", None)
    if callable(close):
        close()

def _read_html(response) -> str:
    """Lê no máximo MAX_HTML_BYTES da página, sem carregar respostas gigantes na memória."""
    iter_content = getattr(response, "iter_content", None)
    if not callable(iter_content):
        return response.text[:MAX_HTML_BYTES]
    chunks, size = [], 0
    try:
        for chunk in iter_content(64 * 1024):
            if not chunk:
                continue
            chunks.append(chunk)
            size += len(chunk)
            if size >= MAX_HTML_BYTES:
                break
    finally:
        _close(response)
    raw = b"".join(chunks)[:MAX_HTML_BYTES]
    headers = getattr(response, "headers", None) or {}
    declared = "charset" in str(headers.get("Content-Type", "")).lower()
    encoding = (getattr(response, "encoding", None) if declared else None) or "utf-8"
    try:
        return raw.decode(encoding, errors="replace")
    except LookupError:
        return raw.decode("utf-8", errors="replace")

def extract_product(url: str) -> dict:
    """Fetch public product metadata, validating each redirect to reduce SSRF risk."""
    headers = {"User-Agent": "Autopost/1.0 (+product metadata preview)"}
    current_url = url
    for _ in range(6):
        _validate_public_url(current_url)
        response = requests.get(current_url, timeout=12, headers=headers, allow_redirects=False, stream=True)
        if response.is_redirect:
            location = response.headers.get("Location")
            _close(response)
            if not location:
                raise ValueError("Redirect without a destination")
            current_url = urljoin(current_url, location)
            continue
        response.raise_for_status()
        break
    else:
        raise ValueError("Too many product page redirects")
    html = _read_html(response)
    soup = BeautifulSoup(html, "html.parser")
    if _is_verification_page(current_url, html, soup):
        raise ProductVerificationRequired(
            "A loja solicitou verificação de tráfego e não forneceu a página do produto. "
            "Abra o link no navegador e revise os dados manualmente."
        )
    def meta(*keys):
        for key in keys:
            tag = soup.find("meta", attrs={"property": key})
            if tag is None: tag = soup.find("meta", attrs={"name": key})
            if tag is not None and tag.get("content"):
                return tag["content"].strip()
        return ""
    jsonld=_jsonld_product(soup)
    main_heading=soup.find("h1")
    # Algumas lojas acrescentam o preço ao og:title; twitter:title costuma trazer só o nome.
    title = meta("twitter:title", "og:title") or (main_heading.get_text(" ",strip=True) if main_heading else "") or jsonld.get("name","") or (soup.title.get_text(" ", strip=True) if soup.title else "")
    description = meta("og:description", "description", "twitter:description") or jsonld.get("description","")
    image = meta("og:image", "twitter:image") or jsonld.get("image","")
    if not image:
        image_tag=soup.find("img",attrs={"itemprop":"image"})
        if image_tag is None: image_tag=soup.find("link",attrs={"itemprop":"image"})
        if image_tag is None: image_tag=soup.find("link",attrs={"rel":"image_src"})
        if image_tag is not None: image=image_tag.get("src") or image_tag.get("href") or ""
    price, original_price, availability = _product_values(soup, meta)
    html_price, html_original = _html_prices(soup)
    # Ordem de confiança: bloco de preço exibido na página (é o que o cliente vê), depois metadados/JSON-LD.
    price = _first_number(html_price, price)
    original_price = _first_number(html_original, original_price)
    if price is None:
        price_match = re.search(r"(?:[-–]\s*)?R\$\s*([\d.]+(?:,\d{2})?)\s*$", meta("og:title"))
        if price_match:
            price = _number(price_match.group(1))
    # Preço anterior só faz sentido se for maior que o atual.
    if price is not None and original_price is not None and original_price <= price:
        original_price = None
    if image: image=urljoin(current_url,image)
    host = urlparse(current_url).hostname or ""
    store = jsonld.get("seller","") or meta("og:site_name", "twitter:site") or host
    return {"title": title[:500], "description": description[:5000], "image_url": image[:2048], "price": price, "original_price": original_price, "store": store[:160], "availability": availability[:80], "price_note": ""}

def _is_verification_page(url, html, soup):
    host_path = (urlparse(url).hostname or "") + urlparse(url).path
    if "/gz/account-verification" in host_path or "suspicious-traffic-frontend" in html[:100_000]:
        return True
    body_text = soup.get_text(" ", strip=True).lower()[:20_000]
    markers = (
        "tráfego suspeito", "verificação de segurança", "verifique que você é humano",
        "verify you are human", "suspicious traffic", "account verification",
    )
    return any(marker in body_text for marker in markers)

def _number(value):
    if value is None: return None
    try:
        if isinstance(value,(int,float)): return float(value)
        cleaned=str(value).strip().replace("R$","").replace("$","").replace(" ","")
        cleaned=re.sub(r"[^\d.,-]","",cleaned)
        if "," in cleaned and "." in cleaned: cleaned=cleaned.replace(".","").replace(",",".")
        elif "," not in cleaned and re.fullmatch(r"\d{1,3}(\.\d{3})+",cleaned): cleaned=cleaned.replace(".","")
        elif "," in cleaned: cleaned=cleaned.replace(",",".")
        return float(cleaned)
    except (TypeError,ValueError): return None

def _first_number(*values):
    for value in values:
        if value is not None:
            return value
    return None

def _text_price(tag):
    return _number(tag.get_text(" ", strip=True)) if tag is not None else None

def _html_prices(soup):
    """Preço atual e preço anterior (riscado) a partir do bloco principal de preço da página.

    O Mercado Livre não passa por aqui: ele bloqueia o servidor e é lido pela
    extensão (extension/reader.js), a única implementação para essa loja.
    """
    current = original = None
    # Amazon
    if original is None:
        core = soup.select_one("#corePriceDisplay_desktop_feature_div, #corePrice_feature_div, #corePrice_desktop")
        if core is not None:
            original = _text_price(core.select_one(".basisPrice .a-offscreen, .a-price.a-text-price .a-offscreen"))
            if current is None:
                current = _text_price(core.select_one(".priceToPay .a-offscreen, .apexPriceToPay .a-offscreen"))
    # Magazine Luiza e outras lojas com data-testid
    if original is None:
        original = _text_price(soup.select_one('[data-testid="price-original"]'))
        if current is None:
            current = _text_price(soup.select_one('[data-testid="price-value"]'))
    # Atributos semânticos genéricos de preço riscado
    if original is None:
        original = _text_price(soup.select_one('[itemprop="highPrice"], .price-old, .old-price, .preco-antigo, del .price, s .price'))
    return current, original

def _product_values(soup, meta):
    current=_number(meta("product:price:amount","og:price:amount","twitter:data1"))
    original=_number(meta("product:original_price:amount","product:price:regular_amount","og:price:original_amount")); availability=meta("product:availability","og:availability")
    for script in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try: data=json.loads(script.string or script.get_text())
        except (json.JSONDecodeError,TypeError): continue
        queue=data if isinstance(data,list) else [data]
        while queue:
            item=queue.pop()
            if not isinstance(item,dict): continue
            if isinstance(item.get("@graph"),list): queue.extend(item["@graph"])
            if isinstance(item.get("itemListElement"),list): queue.extend(x.get("item",x) if isinstance(x,dict) else x for x in item["itemListElement"])
            if isinstance(item.get("offers"),list): queue.extend(item["offers"])
            elif isinstance(item.get("offers"),dict): queue.append(item["offers"])
            specs=item.get("priceSpecification")
            for spec in (specs if isinstance(specs,list) else [specs] if isinstance(specs,dict) else []):
                kind=str(spec.get("priceType","")) if isinstance(spec,dict) else ""
                if original is None and ("StrikethroughPrice" in kind or "ListPrice" in kind):
                    original=_number(spec.get("price"))
            if current is None and item.get("price") is not None: current=_number(item.get("price"))
            if original is None and item.get("highPrice") is not None: original=_number(item.get("highPrice"))
            availability=availability or str(item.get("availability","")).rsplit("/",1)[-1]
    return current, original, availability

def _jsonld_product(soup):
    queue=[]
    for script in soup.find_all("script",attrs={"type":"application/ld+json"}):
        try:
            parsed=json.loads(script.string or script.get_text())
            queue.extend(parsed if isinstance(parsed,list) else [parsed])
        except (json.JSONDecodeError,TypeError): continue
    while queue:
        item=queue.pop(0)
        if not isinstance(item,dict): continue
        graph=item.get("@graph")
        if isinstance(graph,list): queue.extend(graph)
        item_type=item.get("@type",[])
        types=item_type if isinstance(item_type,list) else [item_type]
        if any(str(t).lower().endswith("product") for t in types):
            image=item.get("image","")
            if isinstance(image,list): image=image[0] if image else ""
            if isinstance(image,dict): image=image.get("url","")
            offers=item.get("offers",{})
            if isinstance(offers,list): offers=offers[0] if offers else {}
            seller=offers.get("seller","") if isinstance(offers,dict) else ""
            if isinstance(seller,dict): seller=seller.get("name","")
            return {"name":str(item.get("name", "")),"description":str(item.get("description", "")),"image":str(image),"seller":str(seller or "")}
    return {}
