"""Regras das listas escolares: dados das opções, totais e a página de orçamento para os pais.

As funções de cima são puras (sem banco) para serem testadas sozinhas.
"""
import html
import json
import os
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from app.models.product import Product
from app.models.school import SchoolList, SchoolListItem, SchoolListOption, SchoolVisitor

SECTIONS = ("coletivo", "individual")
DEFAULT_LABELS = ("Econômica", "Equilibrada", "Premium")
CLAIM_MINUTES = 10
_CATALOG = re.compile(r"/p/(MLB\d+)", re.I)
_LISTING = re.compile(r"MLB-?U?(\d{6,})", re.I)
_AFFILIATE = re.compile(r"^https://(meli\.la|(www\.)?mercadolivre\.com(\.br)?/sec)/", re.I)


def slugify(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", plain).strip("-")


def school_slug(school_list) -> str:
    return slugify(school_list.school) or "escola"


def grade_slug(school_list) -> str:
    return slugify(f"{school_list.grade} {school_list.year}") or str(school_list.id)


def turmas_of(school_list) -> list[str]:
    try:
        value = json.loads(school_list.turmas or "[]")
    except ValueError:
        value = []
    return [str(t).strip()[:60] for t in value if str(t).strip()]


def clean_turmas(values: list[str]) -> str:
    seen, out = set(), []
    for value in values:
        name = " ".join(str(value).split())[:60]
        if name and name.lower() not in seen:
            seen.add(name.lower()); out.append(name)
    return json.dumps(out[:30], ensure_ascii=False)


def public_base() -> str:
    return os.getenv("APP_PUBLIC_URL", "http://localhost:8000").rstrip("/")


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
            "public": bool(school_list.public), "turmas": turmas_of(school_list), "contact": school_list.contact or "",
            "public_url": f"{public_base()}/escolas/{school_slug(school_list)}",
            "page_url": f"{public_base()}/escolas/{school_slug(school_list)}/{grade_slug(school_list)}",
            "totals": totals(out_items), "oldest_capture": min(captured) if captured else None,
            "missing_links": sum(1 for i in out_items for o in i["options"] if not o["has_affiliate_link"]),
            "empty_items": sum(1 for i in out_items if not i["options"]),
            "visitors": db.scalar(select(func.count()).select_from(SchoolVisitor).where(SchoolVisitor.list_id == school_list.id)) or 0}


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
        # Item sem opção com preço também aparece (fora do total), para a lista não ficar incompleta.
        items.append({"section": item["section"], "name": item["name"], "requested": item["requested"],
                      "color": item["color"], "options": options, "default": max(0, min(1, len(options) - 1))})
    return {"school": detail["school"], "grade": detail["grade"], "year": detail["year"], "items": items}


def buy_link_from(option: dict) -> str:
    return option["affiliate_url"] if option["has_affiliate_link"] else option["original_url"]


def render_page(detail: dict, disclosure: str = "#publi", checked_at: datetime | None = None,
                greeting: str = "", switch_url: str = "") -> str:
    """Página única (HTML + CSS + JS, sem dependências) para publicar no seu site ou landing."""
    data = page_data(detail)
    stamp = (checked_at or now()).astimezone(timezone(timedelta(hours=-3))).strftime("%d/%m/%Y às %H:%M")
    # JSON dentro de <script>: "</" quebrado para não fechar a tag antes da hora.
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(f"Material escolar {data['year']} – {data['grade']}".strip(" –"))
    school = html.escape(data["school"])
    return (PAGE_TEMPLATE.replace("{{TITLE}}", title).replace("{{SCHOOL}}", school)
            .replace("{{DISCLOSURE}}", html.escape(disclosure or "#publi")).replace("{{STAMP}}", html.escape(stamp))
            .replace("{{GREETING}}", _greeting(greeting, switch_url)).replace("{{DATA}}", payload))


def _greeting(greeting: str, switch_url: str) -> str:
    if not greeting:
        return ""
    link = f' · <a href="{html.escape(switch_url)}">trocar aluno</a>' if switch_url else ""
    return f'<p class="hello">{html.escape(greeting)}{link}</p>'


def render_landing(school: str, options: list[tuple[str, str]], action: str, contact: str = "", error: str = "",
                   student: str = "", disclosure: str = "#publi") -> str:
    """Entrada da escola: o responsável informa o nome do aluno e a turma e vai direto para a lista da série."""
    opts = "".join(f'<option value="{html.escape(v)}">{html.escape(label)}</option>' for v, label in options)
    contact_line = (f" Para pedir a exclusão dos dados, fale com {html.escape(contact)}." if contact
                    else " Você pode pedir a exclusão dos dados a qualquer momento a quem enviou este link.")
    return (LANDING_TEMPLATE.replace("{{SCHOOL}}", html.escape(school or "Material escolar"))
            .replace("{{ACTION}}", html.escape(action)).replace("{{OPTIONS}}", opts)
            .replace("{{ERROR}}", f'<p class="err" role="alert">{html.escape(error)}</p>' if error else "")
            .replace("{{STUDENT}}", html.escape(student)).replace("{{CONTACT}}", contact_line)
            .replace("{{DISCLOSURE}}", html.escape(disclosure or "#publi")))

LANDING_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<title>Material escolar · {{SCHOOL}}</title>
<style>
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:#F6F6F3;color:#1B1D1C;font:15px/1.5 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:460px;margin:0 auto;padding:20px 16px 40px}
.top{display:flex;justify-content:flex-end;margin-bottom:28px}
.publi{font-size:12px;font-weight:600;color:#5A5D5B;border:1px solid #E4E4DE;border-radius:6px;padding:3px 8px;background:#fff}
h1{font-size:26px;line-height:1.2;margin:0 0 8px;letter-spacing:-.01em}p{margin:0 0 20px;color:#4A4D4B}
.card{background:#fff;border:1px solid #E4E4DE;border-radius:18px;padding:20px;display:flex;flex-direction:column;gap:16px}
label{display:flex;flex-direction:column;gap:6px;font-size:14px;font-weight:600}
input[type=text],select{font:inherit;font-size:16px;min-height:48px;padding:10px 12px;border:1px solid #CFCFC7;border-radius:12px;background:#fff;color:#1B1D1C;width:100%}
input[type=text]:focus,select:focus{outline:2px solid #0F6E5C;outline-offset:1px;border-color:#0F6E5C}
.consent{flex-direction:row;align-items:flex-start;gap:10px;font-weight:400;font-size:13px;color:#4A4D4B;line-height:1.45}
.consent input{width:22px;height:22px;margin:0;accent-color:#0F6E5C;flex:none}
button{font:inherit;font-size:16px;font-weight:700;min-height:50px;border-radius:12px;border:0;background:#0F6E5C;color:#fff;cursor:pointer}
.err{color:#B3261E;background:#FCEEEE;border-radius:10px;padding:10px 12px;margin:0;font-size:14px}
@media (min-width:700px){main{padding-top:48px}h1{font-size:32px}}
</style></head>
<body><main>
<div class="top"><span class="publi">{{DISCLOSURE}}</span></div>
<h1>{{SCHOOL}}</h1>
<p>Informe o nome do aluno e a turma para ver a lista de material da série, com os preços de hoje.</p>
<form class="card" method="post" action="{{ACTION}}">
{{ERROR}}
<label>Nome do aluno<input type="text" name="student_name" required maxlength="120" autocomplete="off" value="{{STUDENT}}"></label>
<label>Turma<select name="turma" required><option value="">Escolha a turma</option>{{OPTIONS}}</select></label>
<label class="consent"><input type="checkbox" name="consent" value="1" required>
<span>Sou responsável por este aluno e autorizo guardar o nome e a turma informados para montar a lista e controlar os acessos desta página. Nada mais é coletado.{{CONTACT}}</span></label>
<button type="submit">Ver a lista</button>
</form>
</main></body></html>
"""


PAGE_TEMPLATE = """<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>{{TITLE}}</title>
<style>
:root{--bg:#F6F6F3;--ink:#1B1D1C;--muted:#5A5D5B;--line:#E4E4DE;--line2:#CFCFC7;--acc:#0F6E5C;--acc2:#E3F2EE;--acc3:#0A5446}
*{box-sizing:border-box}html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;padding-bottom:88px}
a{color:var(--acc)}button{font:inherit;color:inherit}
header{background:#fff;border-bottom:1px solid var(--line)}
.wrap{max-width:1120px;margin:0 auto;padding:0 16px}
.top{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:52px}
.school{font-weight:700;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.publi{flex:none;font-size:12px;font-weight:600;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:3px 8px}
.hero{padding:20px 0 4px}.hello{font-size:13px;color:var(--muted);margin:0 0 6px}
h1{font-size:24px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}.lead{margin:0;color:#4A4D4B;max-width:620px}
.tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;position:sticky;top:0;z-index:5;background:var(--bg);padding:12px 0}
.tabs:empty{display:none}
.tab{text-align:left;padding:11px 12px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer;display:flex;justify-content:space-between;align-items:baseline;gap:6px;min-width:0}
.tab span{font-weight:700;font-size:15px}.tab small{font-size:13px;color:var(--muted);white-space:nowrap}.tab em{display:none;font-style:normal}
.tab[aria-selected=true]{background:var(--ink);border-color:var(--ink);color:#fff}.tab[aria-selected=true] small{color:#CFD2CF}
.layout{display:grid;gap:16px;padding:4px 0 24px}
.list{display:flex;flex-direction:column;gap:12px;min-width:0}
.card{background:#fff;border:1px solid var(--line);border-radius:16px;padding:14px;display:grid;gap:12px;align-items:start;
  grid-template-columns:72px minmax(0,1fr);grid-template-areas:"img info" "opts opts" "foot foot" "acts acts"}
.card.done{border-color:#9FCFC3;background:#FBFDFC}
.img{grid-area:img;width:72px;height:72px;border-radius:12px;border:1px solid var(--line);background:#fff;object-fit:contain}
.ph{display:flex;align-items:center;justify-content:center;color:#A3A6A3;background:#FAFAF8}
.info{grid-area:info;min-width:0}
.name{font-size:16px;font-weight:700;margin:0;line-height:1.3}
.meta{margin:3px 0 0;font-size:13px;color:var(--muted)}
.prod{margin:4px 0 0;font-size:13px;color:#3A3D3B;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.opts{grid-area:opts;display:flex;gap:8px;overflow-x:auto;scrollbar-width:none;margin:0 -14px;padding:2px 14px}
.opts::-webkit-scrollbar{display:none}
.opt{flex:0 0 auto;min-width:108px;display:flex;flex-direction:column;align-items:flex-start;gap:1px;padding:8px 12px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer}
.opt span{font-size:12px;color:var(--muted)}.opt b{font-size:15px}
.opt[aria-pressed=true]{border-color:var(--acc);background:var(--acc2);box-shadow:inset 0 0 0 1px var(--acc)}.opt[aria-pressed=true] span{color:var(--acc3)}
.foot{grid-area:foot;display:flex;align-items:center;justify-content:space-between;gap:12px}
.qty{display:flex;align-items:center;border:1px solid var(--line2);border-radius:12px;background:#fff}
.qty button{width:44px;height:44px;border:0;background:none;font-size:20px;cursor:pointer}
.qty span{min-width:24px;text-align:center;font-weight:700}
.price{display:flex;flex-direction:column;align-items:flex-end;text-align:right}
.price b{font-size:20px;line-height:1.15}.was{font-size:12px;color:var(--muted)}.was s{margin-left:4px}
.each{font-size:12px;color:var(--muted)}.pct{color:var(--acc3);font-weight:700}
.acts{grid-area:acts;display:grid;grid-template-columns:1fr auto;gap:8px;align-items:center}
.buy{grid-column:1/-1;display:flex;align-items:center;justify-content:center;min-height:46px;border-radius:12px;background:var(--acc);color:#fff;font-weight:700;text-decoration:none}
.tog{font-weight:600;font-size:14px;min-height:42px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer;padding:0 14px}
.tog[aria-pressed=true]{background:var(--acc2);border-color:var(--acc);color:var(--acc3)}
.link{font-size:14px;font-weight:600;background:none;border:0;color:var(--muted);text-decoration:underline;cursor:pointer;padding:0 6px;min-height:42px}
.card.off{grid-template-areas:"img info" "undo undo"}.card.off .img,.card.off .info{opacity:.55}
.undo{grid-area:undo;display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:13px;color:var(--muted);border-top:1px dashed var(--line);padding-top:4px}
.card.nop{grid-template-areas:"img info"}
.empty{background:#fff;border:1px dashed var(--line2);border-radius:16px;padding:28px 20px;text-align:center;display:flex;flex-direction:column;gap:4px}
.sum{background:#fff;border:1px solid var(--line);border-radius:16px;padding:18px;display:flex;flex-direction:column;gap:14px}
.label{font-size:13px;color:var(--muted)}.total{font-size:34px;font-weight:800;line-height:1.05;letter-spacing:-.02em}
.row{display:flex;justify-content:space-between;align-items:baseline;gap:8px;font-size:14px}
.bar{height:8px;background:#ECECE6;border-radius:999px;overflow:hidden;margin-top:6px}.bar i{display:block;height:100%;width:0;background:var(--acc);border-radius:999px;transition:width .2s}
.split{display:flex;flex-direction:column;gap:6px;border-top:1px solid var(--line);padding-top:12px}.split:empty{display:none}.split .all{font-weight:700}
.btn2{font-size:14px;font-weight:600;min-height:44px;border-radius:12px;border:1px solid var(--line2);background:#fff;cursor:pointer}
.small{font-size:12px;line-height:1.5;color:var(--muted);margin:0}
.mbar{transition:transform .2s}.mbar.hide{transform:translateY(110%)}
.mbar{position:fixed;left:0;right:0;bottom:0;z-index:10;background:#fff;border-top:1px solid var(--line);box-shadow:0 -6px 18px rgba(0,0,0,.06);padding:10px 16px calc(10px + env(safe-area-inset-bottom))}
.mbar .in{max-width:1120px;margin:0 auto;display:flex;align-items:center;justify-content:space-between;gap:16px}
.mbar small{display:block;font-size:12px;color:var(--muted)}.mbar b{font-size:22px;letter-spacing:-.01em}
.mbar .cart{text-align:right;font-size:13px;width:128px}
@media (min-width:900px){
  body{padding-bottom:0}.mbar{display:none}
  .hero{padding:32px 0 4px}h1{font-size:32px}
  .tabs{position:static;display:flex;padding:20px 0 12px}.tab{min-width:230px;flex-direction:column;align-items:flex-start;gap:1px}.tab em{display:inline}.tab small{font-size:12px}
  .layout{grid-template-columns:minmax(0,1fr) 320px;align-items:start}aside{position:sticky;top:16px}
  .card{grid-template-columns:96px minmax(0,1fr) 250px;grid-template-areas:"img info foot" "img opts acts";padding:16px 18px;gap:12px 20px}
  .img{width:96px;height:96px}.opts{margin:0;padding:0;flex-wrap:wrap;overflow:visible}.opt{min-width:0;padding:7px 11px}
  .card.off{grid-template-areas:"img info undo"}.undo{border:0;padding:0;flex-direction:column;align-items:flex-end}
  .card.nop{grid-template-areas:"img info info"}
}
@media print{
  body{padding:0;background:#fff}header,.tabs,.buy,.tog,.link,.qty button,.btn2,.mbar{display:none}
  .layout{grid-template-columns:1fr}.card{break-inside:avoid}aside{position:static}
}
</style>
</head>
<body>
<header><div class="wrap top"><span class="school">{{SCHOOL}}</span><span class="publi">{{DISCLOSURE}}</span></div></header>
<main class="wrap">
<div class="hero">{{GREETING}}<h1>{{TITLE}}</h1>
<p class="lead">Marque o que você já tem em casa, escolha uma opção de cada item e compre no Mercado Livre.</p></div>
<nav class="tabs" role="tablist" id="tabs"></nav>
<div class="layout"><section class="list" id="list" aria-live="polite"></section>
<aside><div class="sum" id="sum">
<div><div class="label" id="sumTitle"></div><div class="total" id="total"></div><div class="label" id="count" style="margin-top:6px"></div></div>
<div><div class="row"><span class="label">No carrinho</span><b id="cartLabel"></b></div><div class="bar"><i id="cartBar"></i></div></div>
<div class="split" id="split"></div>
<button class="btn2" onclick="window.print()">Imprimir ou salvar em PDF</button>
<p class="small">Preços conferidos em {{STAMP}}. O preço e o estoque finais são os do Mercado Livre na hora da compra. O Mercado Livre não deixa colocar vários produtos no carrinho de uma vez: abra cada item e marque "Pus no carrinho".</p>
</div></aside></div>
</main>
<div class="mbar"><div class="in"><div><small id="mbLabel"></small><b id="mbTotal"></b></div>
<div class="cart"><span id="mbCart"></span><div class="bar"><i id="mbBar"></i></div></div></div></div>
<script>
const D = {{DATA}};
const KEY = 'orcamento:' + D.school + ':' + D.grade + ':' + D.year;
const brl = v => v.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
const esc = s => String(s == null ? '' : s).replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c]));
let S = {};
try { S = JSON.parse(localStorage.getItem(KEY) || '{}'); } catch (e) { S = {}; }
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(S)); } catch (e) {} };
const st = i => {
  const it = D.items[i], s = S[i] || (S[i] = {inc: true, opt: it.default, qty: (it.options[it.default] || {qty: 1}).qty, cart: false});
  if (!it.options[s.opt]) s.opt = 0;
  return s;
};
const sections = [...new Set(D.items.map(i => i.section))];
let tab = sections.includes('coletivo') ? 'coletivo' : (sections[0] || '');
const LABEL = {coletivo: ['Coletivo', 'vai para a escola'], individual: ['Individual', 'fica com a criança']};
const nameOf = s => (LABEL[s] || [s || ''])[0];
const PH = '<svg viewBox="0 0 24 24" width="28" height="28" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h16M6 16l10-10 3 3-10 10H6z"/></svg>';
function sum(section) {
  const r = {total: 0, n: 0, c: 0, priced: 0, all: 0};
  D.items.forEach((it, i) => {
    if (it.section !== section) return;
    r.all++;
    if (!it.options.length) return;
    r.priced++;
    const s = st(i);
    if (s.inc) { r.total += it.options[s.opt].price * s.qty; r.n++; if (s.cart) r.c++; }
  });
  return r;
}
function card(it, i) {
  const meta = [it.requested ? 'Pedido: ' + esc(it.requested) : '', it.color ? 'Cor: ' + esc(it.color) : ''].filter(Boolean).join(' · ');
  const head = title => `<div class="info"><h3 class="name">${esc(it.name)}</h3>${meta ? `<p class="meta">${meta}</p>` : ''}${title}</div>`;
  if (!it.options.length) return `<article class="card nop"><span class="img ph">${PH}</span>${head('<p class="meta">Ainda sem preço conferido; fica fora do total.</p>')}</article>`;
  const s = st(i), o = it.options[s.opt];
  const img = o.image ? `<img class="img" src="${esc(o.image)}" alt="" referrerpolicy="no-referrer" loading="lazy">` : `<span class="img ph">${PH}</span>`;
  const info = head(`<p class="prod">${esc(o.title)}</p>`);
  if (!s.inc) return `<article class="card off">${img}${info}<div class="undo"><span>Você já tem este item.</span><button class="link" data-i="${i}" data-act="have">Desfazer</button></div></article>`;
  const pct = o.original_price && o.original_price > o.price ? Math.round((1 - o.price / o.original_price) * 100) : 0;
  const opts = it.options.length > 1 ? `<div class="opts" role="group" aria-label="Opções">${it.options.map((x, j) =>
    `<button class="opt" aria-pressed="${j === s.opt}" data-i="${i}" data-opt="${j}"><span>${esc(x.label || 'Opção ' + (j + 1))}</span><b>${brl(x.price)}</b></button>`).join('')}</div>` : '';
  const each = s.qty > 1 ? brl(o.price) + ' cada' : '';
  return `<article class="card${s.cart ? ' done' : ''}">${img}${info}${opts}
    <div class="foot"><div class="qty"><button data-i="${i}" data-act="minus" aria-label="Diminuir quantidade">−</button><span>${s.qty}</span><button data-i="${i}" data-act="plus" aria-label="Aumentar quantidade">+</button></div>
    <div class="price">${pct >= 5 ? `<span class="was"><span class="pct">-${pct}%</span><s>${brl(o.original_price * s.qty)}</s></span>` : ''}<b>${brl(o.price * s.qty)}</b>${each ? `<span class="each">${each}</span>` : ''}</div></div>
    <div class="acts"><a class="buy" href="${esc(o.url)}" target="_blank" rel="noopener sponsored">Comprar no Mercado Livre</a>
    <button class="tog" data-i="${i}" data-act="cart" aria-pressed="${s.cart}">${s.cart ? '✓ No carrinho' : 'Pus no carrinho'}</button>
    <button class="link" data-i="${i}" data-act="have">Já tenho</button></div></article>`;
}
function render() {
  const sums = Object.fromEntries(sections.map(s => [s, sum(s)]));
  document.getElementById('tabs').innerHTML = sections.length < 2 ? '' : sections.map(s =>
    `<button class="tab" role="tab" aria-selected="${s === tab}" data-tab="${s}"><span>${esc(nameOf(s))}</span><small><em>${esc((LABEL[s] || ['', ''])[1])} · </em>${brl(sums[s].total)}</small></button>`).join('');
  document.getElementById('list').innerHTML = D.items.map((it, i) => it.section === tab ? card(it, i) : '').join('')
    || '<div class="empty"><b>A lista ainda está sendo preparada.</b><span class="label">Os preços estão sendo conferidos. Volte daqui a pouco.</span></div>';
  const t = sums[tab] || {total: 0, n: 0, c: 0, priced: 0, all: 0};
  const label = ['Seu orçamento', nameOf(tab)].filter(Boolean).join(' · ');
  const width = (t.n ? Math.round(t.c / t.n * 100) : 0) + '%';
  document.getElementById('sumTitle').textContent = label;
  document.getElementById('total').textContent = brl(t.total);
  document.getElementById('count').textContent = t.n + ' de ' + t.all + ' itens no orçamento';
  document.getElementById('cartLabel').textContent = t.c + ' de ' + t.n;
  document.getElementById('cartBar').style.width = width;
  document.getElementById('mbLabel').textContent = label;
  document.getElementById('mbTotal').textContent = brl(t.total);
  document.getElementById('mbCart').textContent = t.c + ' de ' + t.n + ' no carrinho';
  document.getElementById('mbBar').style.width = width;
  const all = sections.reduce((a, s) => a + sums[s].total, 0);
  document.getElementById('split').innerHTML = sections.length < 2 ? '' : sections.map(s =>
    `<div class="row"><span>${esc(nameOf(s))}</span><span>${brl(sums[s].total)}</span></div>`).join('')
    + `<div class="row all"><span>Total da série</span><span>${brl(all)}</span></div>`;
}
document.addEventListener('click', e => {
  const t = e.target.closest('[data-tab],[data-opt],[data-act]');
  if (!t) return;
  if (t.dataset.tab) { tab = t.dataset.tab; render(); window.scrollTo({top: document.getElementById('tabs').offsetTop - 4}); return; }
  const i = Number(t.dataset.i), s = st(i), act = t.dataset.act;
  if (t.dataset.opt) { s.opt = Number(t.dataset.opt); s.qty = D.items[i].options[s.opt].qty; }
  if (act === 'minus') s.qty = Math.max(1, s.qty - 1);
  if (act === 'plus') s.qty = s.qty + 1;
  if (act === 'cart') s.cart = !s.cart;
  if (act === 'have') { s.inc = !s.inc; if (!s.inc) s.cart = false; }
  save(); render();
});
render();
// No celular, a barra de baixo some quando o resumo completo já está na tela.
if ('IntersectionObserver' in window) new IntersectionObserver(es => es.forEach(e =>
  document.querySelector('.mbar').classList.toggle('hide', e.isIntersecting))).observe(document.getElementById('sum'));
</script>
</body>
</html>
"""
