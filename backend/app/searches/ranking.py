"""Qualidade das ofertas: nota, agrupamento de anúncios parecidos e escolha dos melhores.

Sem dependências do banco: recebe objetos simples (ou modelos) e devolve números e listas,
para poder ser testado e reaproveitado pelas buscas automáticas e pelas buscas das campanhas.

Por que existe: o mesmo produto costuma aparecer várias vezes numa busca (lojas diferentes,
cores, títulos quase iguais). Sem agrupar, todos ficam no topo juntos e a campanha repete produto.
"""
from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------- nota da oferta (0 a 100)

PRIOR_RATING = 4.3      # nota "média" assumida quando há poucas vendas
PRIOR_WEIGHT = 30       # quantas vendas a nota precisa para pesar mais que a média
FLAT_DAYS = 3           # dias de histórico para concluir que o preço nunca mudou
FLAT_VARIATION = 0.05   # variação abaixo de 5% conta como preço parado


def weighted_rating(rating: float | None, sold: int | None) -> float:
    """Nota ponderada pelo volume: 5,0 com 3 vendas vale menos que 4,8 com 10 mil."""
    volume = max(0, sold or 0)
    if rating is None:
        return PRIOR_RATING
    return (min(rating, 5) * volume + PRIOR_RATING * PRIOR_WEIGHT) / (volume + PRIOR_WEIGHT)


def effective_discount(discount_pct: int | None, history_points: int = 0, min_30d: float | None = None,
                       max_30d: float | None = None, history_days: float = 0) -> float:
    """Desconto anunciado, pela metade quando o preço ficou parado por dias (o "de" nunca foi praticado)."""
    announced = float(discount_pct or 0)
    if announced and history_points >= 3 and history_days >= FLAT_DAYS and min_30d and max_30d \
            and (max_30d - min_30d) / max_30d < FLAT_VARIATION:
        return announced / 2
    return announced


def offer_score(*, discount_pct: int | None, rating: float | None, sold: int | None, free_shipping: bool = False,
                official_store: bool = False, fulfillment: bool = False, price: float | None = None,
                history_points: int = 0, min_30d: float | None = None, max_30d: float | None = None,
                history_days: float = 0) -> int:
    """Nota de 0 a 100.

    Desconto conferido no histórico (até 40), nota ponderada pelas vendas (até 20), vendas (até 15),
    menor preço dos últimos 30 dias (10) e confiança: loja oficial (7), Full (5) e frete grátis (3).
    """
    discount = effective_discount(discount_pct, history_points, min_30d, max_30d, history_days)
    score = min(discount, 60) / 60 * 40
    score += max(0.0, min(weighted_rating(rating, sold), 5) - 3.5) / 1.5 * 20
    if sold:
        score += min(math.log10(sold + 1) / 4, 1) * 15
    if history_points >= 3 and min_30d is not None and price is not None and price <= min_30d:
        score += 10
    score += 7 * bool(official_store) + 5 * bool(fulfillment) + 3 * bool(free_shipping)
    return max(0, min(100, round(score)))


# ---------------------------------------------------------------- anúncios parecidos

# Palavras que não ajudam a distinguir produtos (comparadas sem acento e em minúsculas).
STOPWORDS = {
    "a", "o", "as", "os", "um", "uma", "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas", "com",
    "para", "pra", "por", "ao", "aos", "sem", "the", "and", "for", "with",
    "kit", "novo", "nova", "novos", "novas", "original", "originais", "oficial", "lancamento", "promocao", "oferta",
    "frete", "gratis", "envio", "imediato", "pronta", "entrega", "premium", "qualidade", "melhor", "super", "top",
    "unidade", "unidades", "peca", "pecas", "pc", "pcs", "cor", "cores", "tamanho", "modelo", "produto", "x",
}
UNITS = r"gb|tb|mb|ml|l|lt|litros?|g|kg|mg|mm|cm|m|w|v|mah|hz|pol|polegadas|pcs|un|cv|btus?"

# Palavras que separam públicos: "camiseta masculina" e "camiseta feminina" não são o mesmo produto.
AUDIENCES = [
    {"masculino", "masculina", "masc", "homem", "men", "mens"},
    {"feminino", "feminina", "fem", "mulher", "women", "womens"},
    {"infantil", "kids", "menino", "menina", "bebe", "juvenil"},
]

PRICE_RATIO = 1.8        # parecidos com preço muito diferente não são o mesmo produto
SAME_JACCARD = 0.55      # palavras em comum / palavras no total
SAME_CONTAINED = 0.8     # palavras do título menor que aparecem no maior
CHEAP_BONUS = 8          # pontos para o mais barato do grupo na escolha do representante
SIMILAR_PENALTY = 25     # pontos tirados de quem lembra demais algo já escolhido


def _plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return "".join(c for c in text if not unicodedata.combining(c)).casefold()


def title_tokens(title: str) -> frozenset[str]:
    """Palavras que identificam o produto: sem acento, sem palavras vazias, "128 gb" vira "128gb"."""
    text = _plain(title).replace(",", ".")
    text = re.sub(rf"(\d+(?:\.\d+)?)\s*({UNITS})\b", r"\1\2", text)
    out = set()
    for word in re.findall(r"[a-z0-9.]+", text):
        word = word.strip(".")
        if not word or word in STOPWORDS or (len(word) < 2 and not word.isdigit()):
            continue
        if len(word) > 4 and word.endswith("s") and not any(ch.isdigit() for ch in word):
            word = word[:-1]                                  # plural simples: "fones" ~ "fone"
        out.add(word)
    return frozenset(out)


def _numbers(tokens: frozenset[str]) -> frozenset[str]:
    return frozenset(t for t in tokens if any(ch.isdigit() for ch in t))


def _measures(tokens: frozenset[str]) -> frozenset[str]:
    """Medidas como "480gb", "500ml", "25w": se diferem, são produtos diferentes."""
    return frozenset(t for t in tokens if re.fullmatch(rf"\d+(?:\.\d+)?(?:{UNITS})", t))


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


@dataclass
class Offer:
    """Um anúncio (ou produto já na campanha) para comparar.

    id: identificador único na lista (use negativos para produtos já na campanha).
    taken: já está na campanha; o grupo inteiro passa a contar como "já tem".
    eligible: passou nos filtros (só os elegíveis podem representar um grupo ou ser escolhidos).
    """
    id: int
    title: str
    price: float | None = None
    category: str | None = None
    catalog: str | None = None
    seller: str = ""
    score: float = 0
    eligible: bool = True
    taken: bool = False
    tokens: frozenset[str] = field(default=frozenset(), init=False, repr=False)

    def __post_init__(self):
        self.tokens = title_tokens(self.title)


def same_product(a: Offer, b: Offer) -> bool:
    """Os dois anúncios parecem ser o mesmo produto (outra loja, outra cor ou título quase igual)?"""
    if a.catalog and a.catalog == b.catalog:
        return True
    if a.category and b.category and a.category != b.category:
        return False
    if a.price and b.price and max(a.price, b.price) / min(a.price, b.price) > PRICE_RATIO:
        return False
    aud_a = {i for i, words in enumerate(AUDIENCES) if a.tokens & words}
    aud_b = {i for i, words in enumerate(AUDIENCES) if b.tokens & words}
    if aud_a and aud_b and not aud_a & aud_b:
        return False
    ma, mb = _measures(a.tokens), _measures(b.tokens)
    if ma and mb and ma != mb:
        return False                                          # "128gb" x "256gb": produtos diferentes
    na, nb = _numbers(a.tokens), _numbers(b.tokens)
    if na and nb and not na & nb:
        return False                                          # modelos diferentes ("520bt" x "720bt")
    if not a.tokens or not b.tokens:
        return False
    common = len(a.tokens & b.tokens)
    jac = common / len(a.tokens | b.tokens)
    smaller = min(len(a.tokens), len(b.tokens))
    return jac >= SAME_JACCARD or (smaller >= 3 and common / smaller >= SAME_CONTAINED and jac >= 0.4)


@dataclass
class GroupInfo:
    key: int            # identificador do grupo (o menor id do grupo)
    size: int           # anúncios elegíveis no grupo
    best: bool          # é o representante do grupo
    cheapest: bool      # é o mais barato entre os elegíveis do grupo (com mais de um)
    rank: float         # nota usada para ordenar e escolher (nota + bônus de preço)
    taken: bool         # o grupo já tem algo na campanha
    order: int = 0      # posição na lista agrupada


def group_offers(offers: list[Offer]) -> dict[int, GroupInfo]:
    """Junta os parecidos e escolhe um representante por grupo (melhor nota, mais barato desempata)."""
    parent = {o.id: o.id for o in offers}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(offers):
        for b in offers[i + 1:]:
            if find(a.id) != find(b.id) and same_product(a, b):
                parent[find(b.id)] = find(a.id)

    groups: dict[int, list[Offer]] = {}
    for o in offers:
        groups.setdefault(find(o.id), []).append(o)

    info: dict[int, GroupInfo] = {}
    ranked_groups = []
    for members in groups.values():
        key = min(m.id for m in members if m.id > 0) if any(m.id > 0 for m in members) else min(m.id for m in members)
        taken = any(m.taken for m in members)
        eligible = [m for m in members if m.eligible and m.id > 0]
        prices = [m.price for m in eligible if m.price]
        low = min(prices) if prices else None

        def rank_of(m: Offer) -> float:
            bonus = 0.0
            if low and m.price and len(prices) > 1:
                bonus = CHEAP_BONUS * max(0.0, 1 - (m.price - low) / (low * 0.3))
            return m.score + bonus

        ordered = sorted(eligible, key=lambda m: (-rank_of(m), m.price or 0, m.id))
        best = ordered[0].id if ordered else None
        for m in members:
            info[m.id] = GroupInfo(key=key, size=len(eligible), best=m.id == best,
                                   cheapest=bool(low and len(prices) > 1 and m.eligible and m.price == low),
                                   rank=round(rank_of(m), 1), taken=taken)
        rest = sorted((m for m in members if m not in ordered), key=lambda m: (-rank_of(m), m.id))
        ranked_groups.append((-(rank_of(ordered[0]) if ordered else -1), key, [m.id for m in ordered + rest]))

    position = 0
    for _, _, ids in sorted(ranked_groups):
        for mid in ids:
            info[mid].order = position
            position += 1
    return info


def pick_best(offers: list[Offer], info: dict[int, GroupInfo], n: int, *,
              per_category: int = 0, per_seller: int = 2) -> list[int]:
    """Os n melhores: um por grupo, sem grupos que já estão na campanha, variando categoria e loja.

    per_category: no máximo isso por categoria (0 = automático, cerca de 40% de n quando há várias categorias).
    per_seller: no máximo isso por loja (0 = sem limite).
    Se os limites não deixarem chegar a n, completa sem eles.
    """
    pool = [o for o in offers if o.id > 0 and o.eligible and o.id in info and info[o.id].best and not info[o.id].taken]
    if n <= 0 or not pool:
        return []
    categories = {o.category for o in pool if o.category}
    if per_category <= 0:
        per_category = max(2, math.ceil(n * 0.4)) if len(categories) > 1 else 0

    chosen: list[Offer] = []
    for limited in (True, False):
        while len(chosen) < n:
            best, best_value = None, None
            for o in pool:
                if o in chosen:
                    continue
                if limited:
                    if per_category and o.category and sum(c.category == o.category for c in chosen) >= per_category:
                        continue
                    if per_seller and o.seller and sum(c.seller == o.seller for c in chosen) >= per_seller:
                        continue
                closeness = max((jaccard(o.tokens, c.tokens) for c in chosen), default=0.0)
                value = info[o.id].rank - SIMILAR_PENALTY * closeness
                if best_value is None or value > best_value or (value == best_value and o.id < best.id):
                    best, best_value = o, value
            if best is None:
                break
            chosen.append(best)
    return [o.id for o in chosen]
