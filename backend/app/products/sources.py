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

BROWSER_NOTICE = "Aguardando leitura no navegador: esta loja bloqueia o servidor. A extensão lê o produto ao abrir a tela Produtos."
