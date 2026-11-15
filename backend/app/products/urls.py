from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Parâmetros de rastreio que não mudam o produto e geravam cadastros duplicados.
_TRACKING_PREFIXES = ("utm_", "matt_", "pdp_filters", "tracking_id", "searchvariation")
_TRACKING_KEYS = {"fbclid", "gclid", "gbraid", "wbraid", "ref", "ref_", "source", "c_id", "c_uid", "position", "type", "sid", "wid"}

def normalize_product_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k.lower() not in _TRACKING_KEYS and not k.lower().startswith(_TRACKING_PREFIXES)]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), ""))
