"""Páginas públicas das listas escolares (sem login): /escolas/<escola> e /escolas/<escola>/<série>.

O responsável informa o nome do aluno e a turma (com consentimento) e vai direto para a lista da série.
O navegador guarda só um token em cookie; os dados ficam em school_visitors para o seu controle.
"""
import secrets
from datetime import timedelta
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.ratelimit import LoginLimiter
from app.database.session import get_db
from app.models.school import SchoolList, SchoolVisitor
from app.publications.service import main_rule
from app.school_lists import service

router = APIRouter(prefix="/escolas", tags=["school-public"])
COOKIE = "autopost_resp"
# Até 20 identificações por IP a cada 15 min (evita cadastro em massa por robô).
signup_limiter = LoginLimiter(max_failures=20, window_seconds=900)
NOT_FOUND = ("<!doctype html><html lang='pt-BR'><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
             "<title>Página não encontrada</title><body style='font-family:system-ui;padding:40px;color:#1B1D1C'>"
             "<h1>Página não encontrada</h1><p>Confira o link recebido. A lista pode ainda não estar publicada.</p></body></html>")


def _published(db: Session, school: str) -> list[SchoolList]:
    rows = db.scalars(select(SchoolList).where(SchoolList.public.is_(True)).order_by(SchoolList.grade, SchoolList.id))
    return [r for r in rows if service.school_slug(r) == school]


def _options(lists: list[SchoolList]) -> list[tuple[str, str]]:
    out = []
    for row in lists:
        turmas = service.turmas_of(row)
        if turmas:
            out += [(f"{row.id}:{t}", f"{row.grade} – Turma {t}") for t in turmas]
        else:
            out.append((f"{row.id}:", row.grade))
    return out


def _visitor(db: Session, request: Request, lists: list[SchoolList]) -> SchoolVisitor | None:
    token = request.cookies.get(COOKIE, "")
    if not token or len(token) > 64:
        return None
    visitor = db.scalar(select(SchoolVisitor).where(SchoolVisitor.token == token))
    owners = {r.owner_id for r in lists}
    return visitor if visitor and visitor.owner_id in owners else None


def _disclosure(db: Session) -> str:
    rule = main_rule(db)
    return (getattr(rule, "disclosure_text", "") or "#publi") if rule else "#publi"


def _page_path(row: SchoolList) -> str:
    return f"/escolas/{service.school_slug(row)}/{service.grade_slug(row)}"


@router.get("/{school}", response_class=HTMLResponse)
def landing(school: str, request: Request, trocar: int = 0, db: Session = Depends(get_db)):
    lists = _published(db, school)
    if not lists:
        return HTMLResponse(NOT_FOUND, status_code=404)
    visitor = None if trocar else _visitor(db, request, lists)
    target = next((r for r in lists if visitor and r.id == visitor.list_id), None)
    if target:
        return RedirectResponse(_page_path(target), status_code=303)
    contact = next((r.contact for r in lists if r.contact), "")
    return HTMLResponse(service.render_landing(lists[0].school, _options(lists), f"/escolas/{school}", contact,
                                               disclosure=_disclosure(db)))


@router.post("/{school}", response_class=HTMLResponse)
def identify(school: str, request: Request, student_name: str = Form(default="", max_length=200),
             turma: str = Form(default="", max_length=200), consent: str = Form(default=""), db: Session = Depends(get_db)):
    lists = _published(db, school)
    if not lists:
        return HTMLResponse(NOT_FOUND, status_code=404)
    contact = next((r.contact for r in lists if r.contact), "")
    name = " ".join(student_name.split())[:120]
    def again(error: str, status: int = 422):
        return HTMLResponse(service.render_landing(lists[0].school, _options(lists), f"/escolas/{school}", contact, error,
                                                   name, _disclosure(db)), status_code=status)
    key = f"school-signup:{request.client.host if request.client else '?'}"
    if signup_limiter.retry_after(key):
        return again("Muitas tentativas seguidas. Tente de novo em alguns minutos.", 429)
    list_id, _, turma_name = turma.partition(":")
    target = next((r for r in lists if str(r.id) == list_id), None)
    if len(name) < 2:
        return again("Informe o nome do aluno.")
    if target is None or (turma_name and turma_name not in service.turmas_of(target)) or (not turma_name and service.turmas_of(target)):
        return again("Escolha a turma na lista.")
    if consent != "1":
        return again("Para continuar, marque a autorização.")
    signup_limiter.fail(key)
    now = service.now()
    visitor = SchoolVisitor(owner_id=target.owner_id, list_id=target.id, school=target.school, student_name=name,
                            turma=f"{target.grade} {turma_name}".strip(), token=secrets.token_urlsafe(32),
                            consent_at=now, created_at=now, last_seen_at=now, visits=0)
    db.add(visitor); db.commit()
    response = RedirectResponse(_page_path(target), status_code=303)
    response.set_cookie(COOKIE, visitor.token, max_age=365 * 24 * 3600, httponly=True, samesite="lax",
                        secure=service.public_base().startswith("https://"), path="/escolas")
    return response


@router.get("/{school}/{grade}", response_class=HTMLResponse)
def list_page(school: str, grade: str, request: Request, db: Session = Depends(get_db)):
    lists = _published(db, school)
    row = next((r for r in lists if service.grade_slug(r) == grade), None)
    if row is None:
        return HTMLResponse(NOT_FOUND, status_code=404)
    visitor = _visitor(db, request, lists)
    if visitor is None:
        return RedirectResponse(f"/escolas/{school}", status_code=303)
    now = service.now()
    # Conta uma visita por meia hora (recarregar a página não infla o número).
    last = service.aware(visitor.last_seen_at)
    if visitor.visits == 0 or last is None or now - last > timedelta(minutes=30):
        visitor.visits = (visitor.visits or 0) + 1
    visitor.last_seen_at = now
    db.commit()
    detail = service.list_detail(db, row)
    captured = [o["captured_at"] for i in detail["items"] for o in i["options"] if o["captured_at"]]
    from datetime import datetime
    oldest = datetime.fromisoformat(min(captured)) if captured else None
    body = service.render_page(detail, _disclosure(db), oldest, greeting=f"Lista de {visitor.student_name} · {visitor.turma}",
                               switch_url=f"/escolas/{school}?trocar=1")
    return HTMLResponse(body, headers={"Cache-Control": "no-store"})
