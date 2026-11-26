"""Regras das listas escolares: dados das opções, totais e a página de orçamento para os pais.

As funções de cima são puras (sem banco) para serem testadas sozinhas.
"""
import html
import json
import re
from datetime import datetime, timedelta, timezone
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.school import SchoolList, SchoolListItem, SchoolListOption

SECTIONS = ("coletivo", "individual")
DEFAULT_LABELS = ("Econômica", "Equilibrada", "Premium")
CLAIM_MINUTES = 10
_CATALOG = re.compile(r"/p/(MLB\d+)", re.I)
_LISTING = re.compile(r"MLB-?U?(\d{6,})", re.I)
_AFFILIATE = re.compile(r"^https://(meli\.la|(www\.)?mercadolivre\.com(\.br)?/sec)/", re.I)


def now() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def catalog_id(url: str) -> str:
    """Código do produto de catálogo do Mercado Livre (/p/MLB…): é o mesmo para todos os vendedores."""
    match = _CATALOG.search(url or "")
    return match.group(1).upper() if match else ""


def is_affiliate_link(url: str) -> bool:
    return bool(_AFFILIATE.match((url or "").strip()))


def buy_link(product: Product) -> str:
    """Link que vai para os pais: o de afiliado quando existe, senão o link comum do produto."""
    return product.affiliate_url if is_affiliate_link(product.affiliate_url) else product.original_url


def parse_lines(text: str) -> list[dict]:
    """Itens colados como texto, um por linha. "2 - Cola branca 90 g" ou "Cola branca 90 g | 2 unidades".

    O que vem depois de "|" (ou o número do começo) vira o "como a escola pede".
    """
    items = []
    for raw in (text or "").splitlines():
        line = raw.strip().strip("•*-–·").strip()
        if not line:
            continue
        requested = ""
        if "|" in line:
            line, requested = (part.strip() for part in line.split("|", 1))
        else:
            match = re.match(r"^(\d{1,4})\s*(?:[-–x)]|un\.?|unid\.?)?\s+(.+)$", line, re.I)
            if match:
                requested, line = match.group(1), match.group(2).strip()
        if line:
            items.append({"name": line[:300], "requested": requested[:120]})
    return items


def option_price(option: dict) -> float | None:
    price = option.get("price")
    return None if price is None else round(price * max(1, option.get("buy_qty") or 1), 2)


def totals(items: list[dict]) -> dict:
    """Total da lista em cada faixa (opção mais barata, a do meio/padrão e a mais cara) por seção."""
    out = {s: {"min": 0.0, "max": 0.0, "items": 0, "priced": 0} for s in SECTIONS}
    for item in items:
        bucket = out.setdefault(item["section"], {"min": 0.0, "max": 0.0, "items": 0, "priced": 0})
        bucket["items"] += 1
        prices = [p for p in (option_price(o) for o in item["options"]) if p is not None]
        if prices:
            bucket["priced"] += 1
            bucket["min"] = round(bucket["min"] + min(prices), 2)
            bucket["max"] = round(bucket["max"] + max(prices), 2)
    return out


# ---------------------------------------------------------------- banco

def option_read(option: SchoolListOption, product: Product) -> dict:
    return {
        "slot": option.slot, "label": option.label or DEFAULT_LABELS[option.slot], "buy_qty": option.buy_qty,
        "watch": option.watch, "last_error": option.last_error or "",
        "product_id": product.id, "title": product.title, "status": product.status,
        "price": product.price, "original_price": product.original_price, "price_note": product.price_note or "",
        "store": product.store, "image_url": product.image_url, "image_source_url": product.image_source_url or "",
        "original_url": product.original_url, "affiliate_url": product.affiliate_url,
        "has_affiliate_link": is_affiliate_link(product.affiliate_url), "catalog_id": catalog_id(product.original_url),
        "captured_at": aware(product.captured_at).isoformat() if product.captured_at else None,
    }


def list_detail(db: Session, school_list: SchoolList) -> dict:
    items = list(db.scalars(select(SchoolListItem).where(SchoolListItem.list_id == school_list.id)
                            .order_by(SchoolListItem.section, SchoolListItem.position, SchoolListItem.id)))
    ids = [i.id for i in items]
    rows = db.execute(select(SchoolListOption, Product).join(Product, Product.id == SchoolListOption.product_id)
                      .where(SchoolListOption.item_id.in_(ids)).order_by(SchoolListOption.slot)).all() if ids else []
    by_item: dict[int, list[dict]] = {}
    for option, product in rows:
        by_item.setdefault(option.item_id, []).append(option_read(option, product))
    out_items = [{"id": i.id, "section": i.section, "name": i.name, "requested": i.requested, "color": i.color,
                  "position": i.position, "options": by_item.get(i.id, [])} for i in items]
    captured = [o["captured_at"] for i in out_items for o in i["options"] if o["captured_at"]]
    return {"id": school_list.id, "school": school_list.school, "grade": school_list.grade, "year": school_list.year,
            "notes": school_list.notes, "refresh_hours": school_list.refresh_hours, "items": out_items,
            "totals": totals(out_items), "oldest_capture": min(captured) if captured else None,
            "missing_links": sum(1 for i in out_items for o in i["options"] if not o["has_affiliate_link"]),
            "empty_items": sum(1 for i in out_items if not i["options"])}


def next_refresh(db: Session, owner_id: int) -> Product | None:
    """O próximo produto das listas deste perfil com preço vencido, reservado por alguns minutos."""
    moment = now()
    candidates = db.execute(
        select(SchoolListOption, Product, SchoolList.refresh_hours)
        .join(SchoolListItem, SchoolListItem.id == SchoolListOption.item_id)
        .join(SchoolList, SchoolList.id == SchoolListItem.list_id)
        .join(Product, Product.id == SchoolListOption.product_id)
        .where(SchoolList.owner_id == owner_id, SchoolListOption.watch.is_(True),
               or_(SchoolListOption.refresh_claimed_at.is_(None),
                   SchoolListOption.refresh_claimed_at < moment - timedelta(minutes=CLAIM_MINUTES)))
        .order_by(Product.captured_at.asc().nullsfirst(), Product.id)).all()
    for option, product, hours in candidates:
        captured = aware(product.captured_at)
        if captured is None or captured < moment - timedelta(hours=max(1, hours or 12)):
            for other in db.scalars(select(SchoolListOption).where(SchoolListOption.product_id == product.id)):
                other.refresh_claimed_at = moment
            db.commit()
            return product
    return None


def finish_refresh(db: Session, product_id: int, error: str = "") -> None:
    for option in db.scalars(select(SchoolListOption).where(SchoolListOption.product_id == product_id)):
        option.refresh_claimed_at = None if not error else option.refresh_claimed_at
        option.last_error = error[:500]
    db.commit()


# ---------------------------------------------------------------- página dos pais

def page_data(detail: dict) -> dict:
    """Só o que a página pública precisa (sem ids internos nem endereços locais)."""
    items = []
    for item in detail["items"]:
        options = [{"label": o["label"], "title": o["title"], "price": o["price"], "original_price": o["original_price"],
                    "qty": o["buy_qty"], "image": o["image_source_url"], "url": buy_link_from(o)}
                   for o in item["options"] if o["price"] is not None]
        if options:
            items.append({"section": item["section"], "name": item["name"], "requested": item["requested"],
                          "color": item["color"], "options": options, "default": min(1, len(options) - 1)})
    return {"school": detail["school"], "grade": detail["grade"], "year": detail["year"], "items": items}


def buy_link_from(option: dict) -> str:
    return option["affiliate_url"] if option["has_affiliate_link"] else option["original_url"]


def render_page(detail: dict, disclosure: str = "#publi", checked_at: datetime | None = None) -> str:
    """Página única (HTML + CSS + JS, sem dependências) para publicar no seu site ou landing."""
    data = page_data(detail)
    stamp = (checked_at or now()).astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    # JSON dentro de <script>: "</" quebrado para não fechar a tag antes da hora.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"Material escolar {data['year']} – {data['grade']}".strip(" –"))
    school = html.escape(data["school"])
    return (PAGE_TEMPLATE.replace("{{TITLE}}", title).replace("{{SCHOOL}}", school)
            .replace("{{DISCLOSURE}}", html.escape(disclosure or "#publi")).replace("{{STAMP}}", html.escape(stamp))
            .replace("{{DATA}}", payload))


PAGE_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITLE}}</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#F6F6F3;color:#1B1D1C;font-family:Inter,system-ui,-apple-system,"Segoe UI",sans-serif}
a{color:#0F6E5C}header{background:#fff;border-bottom:1px solid #E4E4DE}
.wrap{max-width:1160px;margin:0 auto;padding:16px}
.top{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;font-size:13px;color:#5A5D5B}
.pill{border:1px solid #E4E4DE;border-radius:999px;padding:5px 10px;color:#1B1D1C}
h1{font-size:30px;line-height:1.15;margin:10px 0 6px}.lead{margin:0 0 18px;color:#4A4D4B;max-width:640px;line-height:1.5}
.tabs{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px}
.tab{font:inherit;font-size:14px;font-weight:600;padding:10px 16px;border-radius:10px;border:1px solid #CFCFC7;background:#fff;cursor:pointer;color:#1B1D1C}
.tab[aria-selected=true]{background:#1B1D1C;color:#fff;border-color:#1B1D1C}
.cols{display:flex;flex-wrap:wrap;gap:20px;align-items:flex-start}.list{flex:999 1 560px;min-width:0;display:flex;flex-direction:column;gap:10px}
.card{background:#fff;border:1px solid #E4E4DE;border-radius:14px;padding:14px;display:flex;flex-direction:column;gap:10px}
.card.off{opacity:.5}.row{display:flex;flex-wrap:wrap;gap:12px;align-items:flex-start}
.main{display:flex;gap:12px;flex:1 1 260px;min-width:0;cursor:pointer}
.img{flex:0 0 84px;width:84px;height:84px;border-radius:10px;border:1px solid #E4E4DE;background:#fff;object-fit:contain}
.name{font-size:16px;font-weight:600}.muted{font-size:13px;color:#5A5D5B}.prod{font-size:13px;margin-top:2px}
.qty{display:flex;align-items:center;border:1px solid #CFCFC7;border-radius:10px}
.qty button{width:40px;height:40px;border:0;background:none;font-size:18px;cursor:pointer}.qty span{min-width:28px;text-align:center;font-weight:600}
.sub{text-align:right;min-width:96px}.sub b{font-size:18px}
.opts{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.opt{font:inherit;font-size:13px;font-weight:600;padding:8px 12px;border-radius:999px;border:1px solid #CFCFC7;background:#fff;cursor:pointer;color:#1B1D1C}
.opt[aria-pressed=true]{background:#E3F2EE;border-color:#0F6E5C;color:#0A5446}
.grow{flex:1 1 auto}.chk{display:flex;align-items:center;gap:8px;font-size:13px;color:#4A4D4B;cursor:pointer}
input[type=checkbox]{width:20px;height:20px;accent-color:#0F6E5C;margin:0}
.buy{font-size:14px;font-weight:600;text-decoration:none;padding:10px 14px;border-radius:10px;background:#0F6E5C;color:#fff}
aside{flex:1 1 280px;background:#fff;border:1px solid #E4E4DE;border-radius:16px;padding:20px;display:flex;flex-direction:column;gap:14px;position:sticky;top:12px}
.total{font-size:38px;font-weight:700;line-height:1}.bar{height:8px;background:#ECECE6;border-radius:999px;overflow:hidden}.bar div{height:8px;background:#0F6E5C}
.small{font-size:12px;line-height:1.5;color:#5A5D5B;margin:0}.btn2{font:inherit;font-size:14px;font-weight:600;padding:12px;border-radius:12px;border:1px solid #CFCFC7;background:#fff;cursor:pointer}
@media (max-width:640px){aside{position:static}h1{font-size:24px}}
@media print{header,.tabs,.buy,.chk,.qty button,.btn2{display:none}aside{position:static}}
</style>
</head>
<body>
<header><div class="wrap top"><span class="pill">{{SCHOOL}}</span><span class="grow"></span><span>{{DISCLOSURE}} · os links são de afiliado; comprar por eles é opcional</span></div></header>
<main class="wrap">
<h1>{{TITLE}}</h1>
<p class="lead">A lista da série já vem pronta. Desmarque o que você já tem, escolha a opção de cada item e compre no Mercado Livre item por item.</p>
<div class="tabs" role="tablist" id="tabs"></div>
<div class="cols"><section class="list" id="list"></section>
<aside aria-live="polite"><div class="muted" id="sumTitle"></div><div><div class="total" id="total"></div><div class="muted" id="count" style="margin-top:6px"></div></div>
<div><div class="muted" style="display:flex;justify-content:space-between"><span>No carrinho</span><b id="cartLabel"></b></div><div class="bar"><div id="cartBar"></div></div></div>
<button class="btn2" onclick="window.print()">Imprimir ou salvar em PDF</button>
<p class="small">Preços conferidos em {{STAMP}}. O preço e o estoque finais são os do Mercado Livre na hora da compra. O Mercado Livre não deixa colocar vários produtos no carrinho de uma vez: abra cada item e marque "Já pus no carrinho".</p></aside></div>
</main>
<script>
const D = {{DATA}};
const KEY = 'orcamento:' + D.school + ':' + D.grade + ':' + D.year;
const brl = v => v.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
let S = {};
try { S = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { S = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} };
const st = i => S[i] || (S[i] = {inc: true, opt: D.items[i].default, qty: D.items[i].options[D.items[i].default].qty, cart: false});
const sections = [...new Set(D.items.map(i => i.section))];
let tab = sections.includes('coletivo') ? 'coletivo' : sections[0];
const LABEL = {coletivo: 'Coletivo (vai para a escola)', individual: 'Individual (fica com a criança)'};
function render() {
  document.getElementById('tabs').innerHTML = sections.map(s => `<button class="tab" role="tab" aria-selected="${s === tab}" data-tab="${s}">${esc(LABEL[s] || s)}</button>`).join('');
  let total = 0, n = 0, c = 0, shown = 0;
  document.getElementById('list').innerHTML = D.items.map((it, i) => {
    if (it.section !== tab) return '';
    shown++;
    const s = st(i), o = it.options[s.opt] || it.options[0], sub = o.price * s.qty;
    if (s.inc) { total += sub; n++; if (s.cart) c++; }
    const opts = it.options.map((x, j) => `<button class="opt" aria-pressed="${j === s.opt}" data-i="${i}" data-opt="${j}">${esc(x.label)} · ${brl(x.price)}</button>`).join('');
    const img = o.image ? `<img class="img" src="${esc(o.image)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : '<span class="img"></span>';
    return `<article class="card${s.inc ? '' : ' off'}"><div class="row">
      <label class="main"><input type="checkbox" data-i="${i}" data-act="inc" ${s.inc ? 'checked' : ''} aria-label="Incluir ${esc(it.name)} no orçamento">${img}
      <span><span class="name">${esc(it.name)}</span>${it.requested ? `<div class="muted">Pedido pela escola: ${esc(it.requested)}</div>` : ''}${it.color ? `<div class="muted">Cor: ${esc(it.color)}</div>` : ''}<div class="prod">${esc(o.title)}</div></span></label>
      <div class="row" style="align-items:center"><div class="qty"><button data-i="${i}" data-act="minus" aria-label="Diminuir quantidade">−</button><span>${s.qty}</span><button data-i="${i}" data-act="plus" aria-label="Aumentar quantidade">+</button></div>
      <div class="sub"><b>${brl(sub)}</b><div class="muted">${brl(o.price)} cada</div></div></div></div>
      <div class="opts">${opts}<span class="grow"></span><label class="chk"><input type="checkbox" data-i="${i}" data-act="cart" ${s.cart ? 'checked' : ''}> Já pus no carrinho</label>
      <a class="buy" href="${esc(o.url)}" target="_blank" rel="noopener sponsored">Abrir no Mercado Livre</a></div></article>`;
  }).join('');
  document.getElementById('sumTitle').textContent = 'Seu orçamento · ' + D.grade + ' · ' + (LABEL[tab] || tab).split(' (')[0];
  document.getElementById('total').textContent = brl(total);
  document.getElementById('count').textContent = n + ' de ' + shown + ' itens incluídos';
  document.getElementById('cartLabel').textContent = c + ' de ' + n;
  document.getElementById('cartBar').style.width = (n ? Math.round(c / n * 100) : 0) + '%';
}
document.addEventListener('click', e => {
  const t = e.target.closest('[data-tab],[data-opt],[data-act=minus],[data-act=plus]');
  if (!t) return;
  if (t.dataset.tab) { tab = t.dataset.tab; render(); return; }
  const i = Number(t.dataset.i), s = st(i);
  if (t.dataset.opt) { s.opt = Number(t.dataset.opt); s.qty = D.items[i].options[s.opt].qty; }
  if (t.dataset.act === 'minus') s.qty = Math.max(1, s.qty - 1);
  if (t.dataset.act === 'plus') s.qty = s.qty + 1;
  save(); render();
});
document.addEventListener('change', e => {
  const t = e.target; if (!t.dataset || !t.dataset.act) return;
  const s = st(Number(t.dataset.i));
  if (t.dataset.act === 'inc') s.inc = t.checked;
  if (t.dataset.act === 'cart') s.cart = t.checked;
  save(); render();
});
render();
</script>
</body>
</html>
"""
