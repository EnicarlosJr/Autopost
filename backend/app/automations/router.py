import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.automation import AutomationLog, AutomationRule
from app.models.product import Product
from app.publications.messages import (DEFAULT_TEMPLATE, INLINE_VARIABLES, LINE_VARIABLES, clean_disclosure, discount_percent,
                                       standard_offer_text, unknown_variables, with_disclosure)
from app.publications.service import main_rule

router = APIRouter(prefix="/api/automations", tags=["automations"])

class SettingsUpdate(BaseModel):
    enabled: bool = True
    process_on_create: bool = True
    generate_publication: bool = False
    require_approval: bool = True
    categories: list[str] = Field(default_factory=list)
    marketplaces: list[str] = Field(default_factory=list)
    whatsapp_group_name: str = Field(default="", max_length=160)
    message_template: str = Field(default="", max_length=4000)
    send_mode: str = Field(default="preview", pattern="^(preview|image)$")
    watermark_text: str = Field(default="", max_length=80)
    watermark_handle: str = Field(default="", max_length=60)
    disclosure_text: str = Field(default="#publi", max_length=40)
    show_discount: bool = True

class SettingsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    enabled: bool
    process_on_create: bool
    generate_publication: bool
    require_approval: bool
    categories: list[str]
    marketplaces: list[str]
    whatsapp_group_name: str
    message_template: str
    send_mode: str = "preview"
    watermark_text: str = ""
    watermark_handle: str = ""
    disclosure_text: str = "#publi"
    show_discount: bool = True
    default_template: str
    updated_at: datetime

class TemplatePreview(BaseModel):
    template: str = Field(default="", max_length=4000)
    product_id: int | None = None
    disclosure: str | None = Field(default=None, max_length=40)   # vazio = a do perfil

def as_settings(row: AutomationRule) -> dict:
    return {"id": row.id, "name": row.name, "enabled": row.enabled, "process_on_create": row.process_on_create,
            "generate_publication": row.generate_publication, "require_approval": row.require_approval,
            "categories": json.loads(row.categories or "[]"), "marketplaces": json.loads(row.marketplaces or "[]"),
            "whatsapp_group_name": row.whatsapp_group_name, "message_template": row.message_template or "",
            "send_mode": row.send_mode or "preview", "watermark_text": row.watermark_text or "", "watermark_handle": row.watermark_handle or "",
            "disclosure_text": clean_disclosure(row.disclosure_text), "show_discount": True if row.show_discount is None else bool(row.show_discount),
            "default_template": DEFAULT_TEMPLATE, "updated_at": row.updated_at}

def _settings_row(db: Session) -> AutomationRule:
    row = main_rule(db)
    if row is None:
        row = AutomationRule(name="Regra principal"); db.add(row); db.flush()
    return row

def _save(row: AutomationRule, data: SettingsUpdate) -> None:
    template = data.message_template.strip()
    unknown = unknown_variables(template)
    if unknown:
        raise HTTPException(422, f"Variáveis desconhecidas no modelo: {', '.join('{' + u + '}' for u in unknown)}")
    if template == DEFAULT_TEMPLATE.strip():
        template = ""  # igual ao padrão: continua acompanhando o padrão
    values = data.model_dump()
    values["whatsapp_group_name"] = values["whatsapp_group_name"].strip()
    values["categories"] = json.dumps([c.strip() for c in values["categories"] if c.strip()], ensure_ascii=False)
    values["marketplaces"] = json.dumps([m.strip() for m in values["marketplaces"] if m.strip()], ensure_ascii=False)
    values["message_template"] = template
    disclosure = clean_disclosure(values["disclosure_text"])
    if "publi" not in disclosure.casefold():
        raise HTTPException(422, 'A identificação de publicidade precisa ter "#publi" (por exemplo, "#publi | link de afiliado"). '
                                 "O programa de afiliados pede que o afiliado se identifique.")
    values["disclosure_text"] = disclosure
    for key, value in values.items():
        setattr(row, key, value)

@router.get("/sample-image")
def sample_image(product_id: int | None = None, title: str | None = None, handle: str | None = None,
                 disclosure: str | None = None, show_discount: bool | None = None, db: Session = Depends(get_db)):
    """Prévia da foto das ofertas avulsas (aceita a marca d'água ainda não salva)."""
    from fastapi import Response
    from sqlalchemy import select
    from app.models.product import Product
    from app.products.social_image import social_image
    row = _settings_row(db)
    product = db.get(Product, product_id) if product_id else db.scalar(
        select(Product).where(Product.status == "processed", Product.image_url != "").order_by(Product.id.desc()).limit(1))
    if not product:
        raise HTTPException(404, "Cadastre um produto com foto para ver a prévia.")
    try:
        show = (row.show_discount if row.show_discount is not None else True) if show_discount is None else show_discount
        data = social_image(product, row.watermark_text if title is None else title, row.watermark_handle if handle is None else handle,
                            clean_disclosure(row.disclosure_text if disclosure is None else disclosure),
                            discount_percent(product.price, product.original_price) if show else None)
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "no-store"})

@router.get("/settings", response_model=SettingsRead)
def get_settings(db: Session = Depends(get_db)):
    row = _settings_row(db); db.commit(); db.refresh(row)
    return as_settings(row)

@router.put("/settings", response_model=SettingsRead)
def update_settings(data: SettingsUpdate, db: Session = Depends(get_db)):
    row = _settings_row(db)
    _save(row, data)
    db.commit(); db.refresh(row)
    return as_settings(row)

@router.get("/template-variables")
def template_variables():
    return {"line": LINE_VARIABLES, "inline": INLINE_VARIABLES, "default_template": DEFAULT_TEMPLATE}

@router.post("/template-preview")
def template_preview(data: TemplatePreview, db: Session = Depends(get_db)):
    unknown = unknown_variables(data.template)
    if unknown:
        raise HTTPException(422, f"Variáveis desconhecidas no modelo: {', '.join('{' + u + '}' for u in unknown)}")
    product = db.get(Product, data.product_id) if data.product_id else None
    if product is None:
        product = db.scalar(select(Product).where(Product.title != "", Product.price.is_not(None))
                            .order_by(Product.original_price.is_(None), Product.created_at.desc()).limit(1))
    if product is None:
        product = Product(title="Fone de ouvido sem fio", price=129.9, original_price=199.9, price_note="no Pix",
                          affiliate_url="https://meli.la/exemplo", store="Loja exemplo", category="Eletrônicos")
    message = standard_offer_text(product, data.template)
    rule = main_rule(db)
    tag = data.disclosure if data.disclosure is not None else (rule.disclosure_text if rule else "")
    return {"product_title": product.title, "message": message, "outgoing": with_disclosure(message, tag)}

# Compatibilidade: a configuração é uma só; estas rotas leem e gravam a mesma linha.
@router.get("/rules", response_model=list[SettingsRead])
def get_rules(db: Session = Depends(get_db)):
    return [get_settings(db)]

@router.put("/rules/{rule_id}", response_model=SettingsRead)
def update_rule(rule_id: int, data: SettingsUpdate, db: Session = Depends(get_db)):
    row = db.get(AutomationRule, rule_id)
    if row is None: raise HTTPException(404, "Regra não encontrada")
    _save(row, data)
    db.commit(); db.refresh(row)
    return as_settings(row)

@router.delete("/logs")
def clear_logs(db: Session = Depends(get_db)):
    result = db.execute(delete(AutomationLog))
    db.commit()
    return {"deleted": result.rowcount or 0}

@router.get("/logs")
def get_logs(limit: int = 100, db: Session = Depends(get_db)):
    limit = max(1, min(limit, 500))
    rows = db.scalars(select(AutomationLog).order_by(AutomationLog.created_at.desc()).limit(limit))
    return [{"id": r.id, "task_id": r.task_id, "task_type": r.task_type, "product_id": r.product_id, "status": r.status,
             "attempt": r.attempt, "detail": r.detail, "created_at": r.created_at} for r in rows]
