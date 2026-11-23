"""Lojas que bloqueiam o acesso automático do servidor e só podem ser lidas pelo navegador."""
import re
from urllib.parse import urlparse

_BROWSER_ONLY = re.compile(r"(^|\.)(mercadolivre\.com\.br|mercadolivre\.com|mercadolibre\.com|meli\.la)$", re.I)


def needs_browser(url: str) -> bool:
    try:
        host = urlparse(url).hostname or ""
    except ValueError:
        return False
    return bool(_BROWSER_ONLY.search(host))

# Nome da loja a partir do endereço do link (usado quando o usuário não informa).
_MARKETPLACES = [
    (re.compile(r"(^|\.)(mercadolivre\.com(\.br)?|mercadolibre\.com|meli\.la)$", re.I), "Mercado Livre"),
    (re.compile(r"(^|\.)(amazon\.com(\.br)?|amzn\.to)$", re.I), "Amazon"),
    (re.compile(r"(^|\.)(magazineluiza\.com\.br|magalu\.com)$", re.I), "Magalu"),
    (re.compile(r"(^|\.)shopee\.com\.br$", re.I), "Shopee"),
]


def marketplace_of(url: str) -> str:
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return ""
    for pattern, name in _MARKETPLACES:
        if pattern.search(host):
            return name
    return host.removeprefix("www.")


BROWSER_NOTICE = "Aguardando leitura no navegador: esta loja bloqueia o servidor. A extensão lê o produto ao abrir a tela Produtos."
