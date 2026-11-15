"""Catálogo oficial de categorias do Mercado Livre.

A árvore vem de GET https://api.mercadolibre.com/sites/MLB/categories/all (pública; cerca de 29 MB).
O servidor tenta baixar direto; se o Mercado Livre bloquear, a extensão baixa pelo navegador e envia
uma versão enxuta para /api/ml-categories/import. As categorias que saem da API ficam inativas (nada é apagado).
"""
import unicodedata
from datetime import datetime, timezone
import requests
from sqlalchemy import select, update
from sqlalchemy.orm import Session
from app.models.catalog import MlCategory
from app.publications.service import record_event

ALL_URL = "https://api.mercadolibre.com/sites/MLB/categories/all"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36",
           "Accept": "application/json", "Accept-Encoding": "gzip"}


class CatalogError(Exception):
    pass


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text or "")
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).casefold().split())


def slim_from_api(data: dict) -> list[dict]:
    """Converte a resposta de /categories/all no formato enxuto usado na importação."""
    items = []
    for cid, node in (data or {}).items():
        path = node.get("path_from_root") or []
        items.append({
            "id": cid, "name": node.get("name") or cid,
            "parent_id": path[-2]["id"] if len(path) >= 2 else None,
            "total_items": node.get("total_items_in_this_category") or 0,
            "children": len(node.get("children_categories") or []),
        })
    return items


def import_tree(db: Session, items: list[dict], source: str) -> dict:
    """Grava a árvore inteira: cria e atualiza categorias, calcula caminhos e inativa as que sumiram."""
    if len(items) < 50:
        raise CatalogError("A lista de categorias veio incompleta. Nada foi alterado.")
    started = datetime.now(timezone.utc)
    by_id = {str(i["id"]).strip(): i for i in items if str(i.get("id", "")).startswith("MLB")}
    existing = {c.id: c for c in db.scalars(select(MlCategory))}

    def path_of(cid: str) -> list[str]:
        out, seen = [], set()
        while cid and cid in by_id and cid not in seen:
            seen.add(cid); out.append(cid); cid = by_id[cid].get("parent_id")
        return list(reversed(out))

    created = 0
    for cid, item in by_id.items():
        ids = path_of(cid)
        row = existing.get(cid)
        if row is None:
            row = MlCategory(id=cid); db.add(row); created += 1
        row.name = str(item.get("name") or cid)[:200]
        row.search_name = plain(row.name)[:200]
        row.parent_id = item.get("parent_id") or None
        row.path_ids = "/".join(ids)
        row.path_names = " > ".join(str(by_id[i].get("name") or i) for i in ids)
        row.depth = max(0, len(ids) - 1)
        row.children_count = int(item.get("children") or 0)
        row.is_leaf = row.children_count == 0
        row.total_items = int(item.get("total_items") or 0)
        row.active = True
        row.synced_at = started
    gone = [cid for cid in existing if cid not in by_id]
    if gone:
        db.execute(update(MlCategory).where(MlCategory.id.in_(gone)).values(active=False))
    roots = sum(1 for i in by_id.values() if not i.get("parent_id"))
    record_event(db, source, "catalog.sync", None, "completed",
                 f"Categorias do Mercado Livre sincronizadas: {len(by_id)} ({roots} principais), {created} novas, {len(gone)} inativadas.")
    return {"total": len(by_id), "roots": roots, "created": created, "inactivated": len(gone), "synced_at": started.isoformat()}


def sync_from_api(db: Session, source: str = "servidor") -> dict:
    """Tenta baixar a árvore direto do Mercado Livre (o servidor pode ser bloqueado; a extensão é a alternativa)."""
    try:
        response = requests.get(ALL_URL, headers=HEADERS, timeout=90)
    except requests.RequestException as exc:
        record_event(db, source, "catalog.sync", None, "failed", f"Sem conexão com a API do Mercado Livre: {exc}")
        raise CatalogError("O servidor não conseguiu falar com a API do Mercado Livre.") from exc
    if response.status_code != 200:
        record_event(db, source, "catalog.sync", None, "failed", f"API do Mercado Livre respondeu {response.status_code}: {response.text[:200]}")
        raise CatalogError(f"A API do Mercado Livre recusou o servidor ({response.status_code}). Use a atualização pelo navegador.")
    return import_tree(db, slim_from_api(response.json()), source)


def subtree_ids(db: Session, category_id: str) -> set[str]:
    """A categoria e todas as descendentes (pelo caminho gravado)."""
    root = db.get(MlCategory, category_id)
    if root is None:
        return {category_id}
    prefix = root.path_ids
    rows = db.scalars(select(MlCategory.id).where((MlCategory.path_ids == prefix) | MlCategory.path_ids.like(prefix + "/%")))
    return set(rows) | {category_id}
