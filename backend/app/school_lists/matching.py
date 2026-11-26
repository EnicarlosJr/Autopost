"""Busca de equivalentes das listas escolares: o mesmo produto (mesma medida, quantidade e cor) em outras
ofertas e marcas, para preencher as opções vazias (Econômica, Equilibrada, Premium) e achar um mais barato.

Tudo aqui é puro (sem banco). A regra é "na dúvida, fora": qualquer medida diferente (96 x 200 folhas,
90 g x 110 g, 12 x 24 cores), outra cor, kit no lugar de unidade, acessório ("capa para caderno") ou termo
de baixa confiabilidade descarta o anúncio. Nada entra na lista sem o clique em "Usar".
"""
import math
import re
import unicodedata
from collections import Counter
from statistics import median
from urllib.parse import quote

PER_SLOT = 3
CHEAPER_MIN_GAIN = 0.03          # "mais barato" precisa ser ao menos 3% mais barato
MIN_RATING = 4.0                 # nota mínima (quando o anúncio mostra nota)
MIN_SOLD = 10                    # vendas mínimas (quando o anúncio mostra vendas)
MIN_SCORE = 25

STOPWORDS = {"de", "da", "do", "das", "dos", "com", "c", "para", "p", "e", "a", "o", "as", "os", "em", "no", "na",
             "sem", "tipo", "cada", "un", "und", "unid", "unidade", "unidades", "un.", "kit", "cx", "caixa", "pacote",
             "pct", "escolar", "escolares", "infantil", "material", "cor", "cores", "tamanho", "modelo", "marca"}

COLORS = {
    "azul": {"azul", "azuis"}, "vermelho": {"vermelho", "vermelha", "vermelhos", "vermelhas"},
    "verde": {"verde", "verdes"}, "amarelo": {"amarelo", "amarela", "amarelos", "amarelas"},
    "preto": {"preto", "preta", "pretos", "pretas"}, "branco": {"branco", "branca", "brancos", "brancas"},
    "rosa": {"rosa", "pink"}, "roxo": {"roxo", "roxa", "lilas", "violeta"}, "laranja": {"laranja"},
    "marrom": {"marrom"}, "cinza": {"cinza"}, "dourado": {"dourado", "dourada"}, "prateado": {"prateado", "prateada", "prata"},
    "transparente": {"transparente", "incolor", "cristal"},
}
_COLOR_OF = {word: name for name, words in COLORS.items() for word in words}
MULTI_COLOR = {"sortido", "sortidos", "sortida", "sortidas", "colorido", "colorida", "coloridos", "coloridas",
               "variado", "variados", "variadas", "neon", "pastel"}
ANY_COLOR = {"qualquer", "livre", "indiferente", "sortida", "sortidas", "sortido", "sortidos"}

# Variações que mudam o produto: se a referência diz uma, o anúncio não pode dizer a outra.
EXCLUSIVE = [
    [("espiral",), ("brochura",)],
    [("capa dura",), ("capa flexivel", "capa mole")],
    [("liquida", "liquido"), ("bastao",)],
    [("sextavado",), ("triangular",), ("redondo",)],
    [("permanente",), ("lavavel",)],
]

# Características que fazem outro produto: se o anúncio tem e a referência não, fica de fora.
MARKED = ["bastao", "quente", "glitter", "neon", "metalizada", "metalizado", "aquarelavel", "spray", "refil",
          "mini", "infantil", "de cor", "decorado", "decorada", "personalizado", "personalizada", "usado", "usada"]

MARK_LABEL = {"bastao": "bastão", "aquarelavel": "aquarelável"}

NUM = r"(\d+(?:[.,]\d+)?)"
UNITS = [  # (medida, padrão, fator)
    ("folhas", r"(\d{1,4})\s*(?:fls?|folhas?)\b", 1),
    ("g", NUM + r"\s*(?:g|gr|grs|grama|gramas)\b", 1),
    ("g", NUM + r"\s*(?:kg|quilos?)\b", 1000),
    ("ml", NUM + r"\s*ml\b", 1),
    ("ml", NUM + r"\s*(?:l|lt|litros?)\b", 1000),
    ("cores", r"(\d{1,3})\s*cores\b", 1),
    ("cm", NUM + r"\s*cm\b", 1),
    ("cm", NUM + r"\s*mm\b", 0.1),
    ("pack", r"\b(?:kit|caixa|cx|pacote|pct|pack|jogo|conjunto|estojo)\s*(?:c/|com|de)?\s*(\d{1,3})\b(?!\s*(?:cores|folhas|fls|g|ml|cm|mm))", 1),
    ("pack", r"\bc/\s*(\d{1,3})\b(?!\s*(?:cores|folhas|fls|g|ml|cm|mm))", 1),
    ("pack", r"\b(\d{1,3})\s*(?:un|und|unid|unidades|pcs|pecas|pc)\b", 1),
    ("numero", r"\b(?:n|no|nr|num|numero)\.?\s*(\d{1,2})\b(?!\s*(?:cores|folhas|fls|g|ml|cm|mm))", 1),
]
FORMATS = {"a3", "a4", "a5", "oficio", "carta"}
UNIT_LABEL = {"folhas": "{} folhas", "g": "{} g", "ml": "{} ml", "cores": "{} cores", "cm": "{} cm", "pack": "{} un.",
              "numero": "nº {}", "formato": "{}"}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c)).casefold()
    return " ".join(text.split())


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+(?:/[0-9]+)?", plain(text))


def stem(word: str) -> str:
    if word.endswith("oes") and len(word) > 5:
        return word[:-3] + "ao"
    if word.endswith("es") and len(word) > 5 and word[-3] in "rsz":
        return word[:-2]
    return word[:-1] if word.endswith("s") and len(word) > 3 else word


def _num(text: str) -> float:
    return float(text.replace(",", "."))


def spec(text: str) -> dict[str, set]:
    """Medidas citadas no texto: {"folhas": {96.0}, "g": {90.0}, "formato": {"a4"}, ...}."""
    t = plain(text)
    out: dict[str, set] = {}
    for unit, pattern, factor in UNITS:
        for match in re.finditer(pattern, t):
            value = round(_num(match.group(1)) * factor, 2)
            if unit == "pack" and value <= 1:
                continue
            out.setdefault(unit, set()).add(value)
    formats = {w for w in words(t) if w in FORMATS}
    if formats:
        out["formato"] = formats
    return out


def colors(text: str) -> tuple[set[str], bool]:
    """Cores citadas e se o texto fala em várias cores (sortidas, coloridas)."""
    ws = words(text)
    return {_COLOR_OF[w] for w in ws if w in _COLOR_OF}, any(w in MULTI_COLOR for w in ws)


def core_words(name: str) -> list[str]:
    """Palavras que definem o item ("cola", "branca"), sem números, medidas, cores e palavras vazias."""
    out = []
    for w in words(name):
        if w in STOPWORDS or w in _COLOR_OF or w in MULTI_COLOR or any(ch.isdigit() for ch in w) or len(w) < 2:
            continue
        if w in {"g", "gr", "ml", "cm", "mm", "fls", "folha", "folhas", "nº", "n"}:
            continue
        s = stem(w)
        if s not in out:
            out.append(s)
    return out


def _variant(text: str, group) -> int | None:
    t = f" {plain(text)} "
    for index, phrases in enumerate(group):
        if any(f" {p} " in t for p in phrases):
            return index
    return None


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= max(0.01, 0.01 * max(a, b))


def compare(reference: dict, title: str) -> tuple[str, list[str], int]:
    """Confere um anúncio contra a referência. Devolve (motivo da recusa ou "", sinais bons, pontos de medida)."""
    t = plain(title)
    tokens = {stem(w) for w in words(t)}
    core = reference["core"]
    if core:
        if core[0] not in tokens:
            return f'não é "{core[0]}"', [], 0
        need = max(1, math.floor(len(core) * 0.6))
        if sum(1 for w in core if w in tokens) < need:
            return "nome diferente do item", [], 0
        accessory = rf"\b(?:para|p/|pra)\s+(?:\w+\s+)?{re.escape(core[0])}"
        if re.search(accessory, t) and not re.search(accessory, plain(reference["text"])):
            return "acessório, não o próprio item", [], 0
    ref_text = f" {plain(reference['text'])} "
    for mark in MARKED:
        if f" {mark} " in f" {t} " and f" {mark} " not in ref_text:
            return f'é "{MARK_LABEL.get(mark, mark)}"', [], 0
    good, points = [], 0
    found = spec(t)
    for unit, values in reference["spec"].items():
        mine = found.get(unit)
        if not mine:
            if unit != "pack":
                points -= 6
            continue
        same = bool(values & mine) if unit == "formato" else any(_close(a, b) for a in values for b in mine)
        if not same:
            want = UNIT_LABEL[unit].format(_fmt(sorted(values)[0]))
            got = UNIT_LABEL[unit].format(_fmt(sorted(mine)[0]))
            return f"{got} (a lista pede {want})", [], 0
        points += 5
        good.append(UNIT_LABEL[unit].format(_fmt(sorted(values)[0])))
    if "cores" in found and "cores" not in reference["spec"]:
        return f'é de {_fmt(sorted(found["cores"])[0])} cores', [], 0
    if "pack" in found and "pack" not in reference["spec"]:
        return f'vem em kit de {_fmt(sorted(found["pack"])[0])}', [], 0
    for group in EXCLUSIVE:
        mine, theirs = _variant(reference["text"], group), _variant(t, group)
        if mine is not None and theirs is not None and mine != theirs:
            return f'é "{group[theirs][0]}", não "{group[mine][0]}"', [], 0
    want = reference["colors"]
    have, multi = colors(t)
    if want:
        if have and not have & want:
            return f"outra cor ({', '.join(sorted(have))})", [], 0
        if multi and not have & want:
            return "cores sortidas", [], 0
        if have & want:
            good.append("cor " + "/".join(sorted(have & want)))
            points += 5
        else:
            points -= 5
    return "", good, points


def _fmt(value) -> str:
    if isinstance(value, str):
        return value.upper() if value.startswith("a") and len(value) == 2 else value
    return f"{value:g}".replace(".", ",")


def make_reference(item_name: str, item_color: str, reference_title: str) -> dict:
    """O que o anúncio precisa ter: medidas do item e do produto de referência, cor e palavras do item."""
    text = f"{item_name} {reference_title}"
    color_text = item_color if item_color.strip() and not set(words(item_color)) & ANY_COLOR else ""
    want, _ = colors(color_text or item_name)
    if not want and not color_text:
        want, multi = colors(reference_title)
        if multi:
            want = set()
    item_spec = spec(item_name)
    ref_spec = spec(reference_title)
    merged = {u: item_spec.get(u, set()) | ref_spec.get(u, set()) for u in set(item_spec) | set(ref_spec)}
    # A quantidade de unidades do item ("2 cadernos") é quanto comprar, não o tamanho do pacote.
    if "pack" in item_spec and "pack" not in ref_spec:
        merged.pop("pack", None)
    core = core_words(item_name) or core_words(reference_title)[:2]
    return {"core": core, "title_core": core_words(reference_title), "spec": merged, "colors": want,
            "text": text, "tokens": {stem(w) for w in words(text)}}


def quality(c: dict, spec_points: int) -> int:
    """Nota de 0 a 100: avaliação, vendas, loja oficial, Full, frete grátis e quanto bate com a referência."""
    rating, sold = c.get("rating"), c.get("sold")
    score = 8 if rating is None else max(0.0, min(1.0, (rating - 3.5) / 1.5)) * 30
    score += 5 if sold is None else min(25.0, math.log10(sold + 1) / 4 * 25)
    score += 12 if c.get("official_store") else 0
    score += 8 if c.get("fulfillment") else 0
    score += 5 if c.get("free_shipping") else 0
    score += 20 + spec_points
    return int(max(0, min(100, round(score))))


def floor_reason(c: dict, score: int) -> str:
    if c.get("price") is None:
        return "sem preço"
    if c.get("rating") is not None and c["rating"] < MIN_RATING:
        return f"nota {c['rating']:g}"
    if c.get("sold") is not None and c["sold"] < MIN_SOLD:
        return "poucas vendas"
    if score < MIN_SCORE:
        return "pouca confiança"
    return ""


def _signals(c: dict, good: list[str], same_catalog: bool) -> list[str]:
    out = (["mesmo produto (catálogo)"] if same_catalog else []) + good
    if c.get("official_store"):
        out.append("loja oficial")
    if c.get("fulfillment"):
        out.append("Full")
    if c.get("rating") is not None:
        out.append(f"nota {c['rating']:g}".replace(".", ","))
    if c.get("sold"):
        out.append(f"{c['sold']} vendidos" if c["sold"] < 1000 else f"+{c['sold'] // 1000} mil vendidos")
    return out


def pick(reference: dict, candidates: list[dict], existing: list[dict], empty_slots: list[int],
         reference_catalog: str = "", suspicious=None) -> dict:
    """Escolhe as sugestões.

    candidates: anúncios lidos (listing_id, url, title, price, rating, sold, official_store, fulfillment,
    free_shipping, catalog_product_id, ...). existing: opções já escolhidas ({slot, price, url, catalog_id}).
    Devolve {"slots": {"0": [...]}, "cheaper": [...], "accepted": n, "rejected": n, "reasons": {...}}.
    """
    taken_urls = {e.get("url") for e in existing if e.get("url")}
    taken_catalogs = {e.get("catalog_id") for e in existing if e.get("catalog_id")}
    reasons: Counter = Counter()
    accepted, seen_catalog = [], {}
    for c in candidates:
        if c.get("url") in taken_urls or (c.get("catalog_product_id") and c["catalog_product_id"] in taken_catalogs):
            reasons["já está na lista"] += 1
            continue
        bad = suspicious(c.get("title", "")) if suspicious else ""
        if bad:
            reasons[f'baixa confiabilidade ("{bad}")'] += 1
            continue
        reason, good, points = compare(reference, c.get("title", ""))
        same_catalog = bool(reference_catalog and c.get("catalog_product_id") == reference_catalog)
        if same_catalog:
            reason, points = "", points + 10
        if reason:
            reasons[reason] += 1
            continue
        score = quality(c, points)
        reason = floor_reason(c, score)
        if reason:
            reasons[reason] += 1
            continue
        entry = {**c, "score": score, "signals": _signals(c, good, same_catalog)}
        key = c.get("catalog_product_id")
        if key:                                   # mesmo produto de catálogo: fica a oferta mais barata
            prev = seen_catalog.get(key)
            if prev is not None:
                if entry["price"] < prev["price"]:
                    accepted[accepted.index(prev)] = entry
                    seen_catalog[key] = entry
                continue
            seen_catalog[key] = entry
        accepted.append(entry)

    prices = [e["price"] for e in existing if e.get("price") is not None]
    mid = median([a["price"] for a in accepted]) if accepted else 0
    used: set = set()
    slots: dict[str, list] = {}

    def take(rows):
        out = []
        for row in rows:
            if row["url"] not in used and len(out) < PER_SLOT:
                out.append(row); used.add(row["url"])
        return out

    if 0 in empty_slots:
        cheap = sorted(accepted, key=lambda a: (a["price"], -a["score"]))
        if prices:
            cheap = [a for a in cheap if a["price"] <= min(prices)] or cheap
        slots["0"] = take(cheap)
    if 2 in empty_slots:
        strong = [a for a in accepted if a.get("official_store") or (a.get("rating") or 0) >= 4.6 or (a.get("sold") or 0) >= 1000]
        strong = [a for a in strong if a["price"] >= mid] or strong
        slots["2"] = take(sorted(strong, key=lambda a: (-a["score"], -a["price"])))
    if 1 in empty_slots:
        base = mid or 1
        slots["1"] = take(sorted(accepted, key=lambda a: -(a["score"] - 25 * a["price"] / base)))
    cheaper = []
    if prices and 0 not in empty_slots:
        limit = min(prices) * (1 - CHEAPER_MIN_GAIN)
        cheaper = sorted((a for a in accepted if a["price"] <= limit), key=lambda a: (a["price"], -a["score"]))[:PER_SLOT]
    return {"slots": slots, "cheaper": cheaper, "accepted": len(accepted), "rejected": sum(reasons.values()),
            "reasons": dict(reasons.most_common(6))}


def search_url(term: str, cheapest_first: bool = False) -> str:
    slug = re.sub(r"\s+", "-", term.strip().lower())
    url = f"https://lista.mercadolivre.com.br/{quote(slug, safe='-')}"
    return url + "_OrderId_PRICE_ASC_NoIndex_True" if cheapest_first else url


def build_terms(item_name: str, item_color: str, reference_title: str) -> list[dict]:
    """Até 3 buscas: o item pela relevância, o item do mais barato para o mais caro e o produto de referência."""
    name = " ".join(item_name.split())
    color = " ".join(item_color.split())
    if color and not set(words(color)) & ANY_COLOR and plain(color) not in plain(name):
        name = f"{name} {color}"
    name = re.sub(r"^\d{1,3}\s+", "", name)          # "2 colas" -> "colas"
    terms = []
    if name:
        terms += [{"term": name, "url": search_url(name)}, {"term": f"{name} (mais baratos)", "url": search_url(name, True)}]
    ref = re.sub(r"\(.*?\)|\[.*?\]", " ", reference_title or "")
    ref = " ".join(ref.split()[:8])
    if ref and plain(ref) != plain(name):
        terms.append({"term": ref, "url": search_url(ref)})
    return terms[:3]
