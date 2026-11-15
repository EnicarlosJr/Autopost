import os
from datetime import datetime, timedelta, timezone
import requests
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, select
from app.database.session import SessionLocal
from app.models.automation import AutomationLog, AutomationRule
from app.models.product import Product
from app.models.publication import Publication
from app.products.extractor import ProductVerificationRequired, extract_product
from app.products.image_fetch import download_product_image
from app.products.service import VERIFICATION_NOTICE, add_note, apply_server_fields, remove_notes
from app.products.sources import BROWSER_NOTICE, needs_browser
from app.publications.service import maybe_generate_publication, release_due
from app.workers.celery_app import celery_app

PROCESSING_TIMEOUT = 15 * 60   # produto em "processing" há mais tempo que isso é considerado travado
SENDING_TIMEOUT = 10 * 60      # publicação em "sending" sem confirmação vira "failed"

def _now():
    return datetime.now(timezone.utc)

def _record(db, task_id, task_type, product_id, status, attempt, detail):
    db.add(AutomationLog(task_id=task_id or "", task_type=task_type, product_id=product_id, status=status,
                         attempt=attempt, detail=str(detail)[:2000]))

@celery_app.task(bind=True, name="products.process", max_retries=3, autoretry_for=(requests.RequestException,),
                 retry_backoff=True, retry_jitter=True)
def process_product(self, product_id: int):
    attempt = self.request.retries + 1
    db = SessionLocal()
    try:
        product = db.get(Product, product_id)
        if product is None:
            _record(db, self.request.id, "products.process", product_id, "skipped", attempt, "Produto não existe")
            db.commit(); return {"status": "skipped"}
        if needs_browser(product.original_url):
            # Lojas que bloqueiam o servidor: não adianta tentar; a extensão lê pelo navegador.
            product.status = "awaiting_browser"
            product.processing_started_at = None
            add_note(product, BROWSER_NOTICE)
            _record(db, self.request.id, "products.process", product.id, "awaiting_browser", attempt, BROWSER_NOTICE)
            db.commit()
            return {"status": product.status, "product_id": product.id}
        product.status = "processing"
        product.processing_started_at = _now()
        db.commit()
        try:
            try:
                fields = extract_product(product.original_url)
            except ProductVerificationRequired:
                # Alguns links curtos de afiliado mostram a prévia pública do produto
                # mesmo quando a URL canônica pede verificação.
                if not product.affiliate_url or product.affiliate_url == product.original_url:
                    raise
                fields = extract_product(product.affiliate_url)
                if not fields.get("title"):
                    raise
            remove_notes(product, VERIFICATION_NOTICE, "Falha na extração:")
            image_url = fields.pop("image_url", "")
            apply_server_fields(product, fields)
            if image_url and not product.image_url.startswith(os.getenv("APP_PUBLIC_URL", "http://localhost:8000")):
                try:
                    product.image_url = download_product_image(image_url, product.id)
                except Exception as image_error:
                    _record(db, self.request.id, "products.image", product.id, "warning", attempt, image_error)
            product.status = "processed" if product.title else "needs_review"
            detail = "Metadados extraídos" if product.title else "Página acessível, mas sem título; revise manualmente"
        except ProductVerificationRequired as exc:
            product.status = "needs_review"
            product.processing_started_at = None
            add_note(product, str(exc))
            _record(db, self.request.id, "products.process", product.id, "needs_review", attempt, exc)
            db.commit()
            return {"status": product.status, "product_id": product.id, "detail": str(exc)}
        except SoftTimeLimitExceeded:
            product.status = "error"
            product.processing_started_at = None
            add_note(product, "Falha na extração: tempo limite excedido")
            _record(db, self.request.id, "products.process", product.id, "failed", attempt, "Tempo limite excedido")
            db.commit()
            return {"status": "error", "product_id": product.id}
        except Exception as exc:
            final = not isinstance(exc, requests.RequestException) or self.request.retries >= self.max_retries
            # Entre tentativas o produto continua "processing"; só vira "error" na última.
            product.status = "error" if final else "processing"
            if final:
                product.processing_started_at = None
                add_note(product, f"Falha na extração: {str(exc)[:300]}")
            _record(db, self.request.id, "products.process", product.id, "failed" if final else "retrying", attempt, exc)
            db.commit()
            raise
        product.processing_started_at = None
        _record(db, self.request.id, "products.process", product.id, "completed", attempt, detail)
        maybe_generate_publication(db, product)
        db.commit()
        return {"status": product.status, "product_id": product.id}
    finally:
        db.close()

@celery_app.task(name="publications.release_due")
def release_due_publications():
    db = SessionLocal()
    try:
        released = release_due(db, "celery-beat")
        db.commit()
        return {"released": len(released)}
    finally:
        db.close()

@celery_app.task(name="maintenance.recover_stuck")
def recover_stuck_items():
    """Destrava produtos e envios que ficaram presos (worker reiniciado, navegador fechado...)."""
    db = SessionLocal()
    try:
        now = _now()
        products = list(db.scalars(select(Product).where(
            Product.status == "processing",
            (Product.processing_started_at.is_(None)) | (Product.processing_started_at < now - timedelta(seconds=PROCESSING_TIMEOUT)))))
        for product in products:
            product.status = "error"
            product.processing_started_at = None
            add_note(product, "Falha na extração: processamento interrompido; use Reprocessar")
            _record(db, "celery-beat", "maintenance.recover_stuck", product.id, "failed", 1, "Processamento travado")
        sending = list(db.scalars(select(Publication).where(
            Publication.status == "sending", Publication.updated_at < now - timedelta(seconds=SENDING_TIMEOUT))))
        for publication in sending:
            publication.status = "failed"
            publication.last_error = "Envio sem confirmação. Confira no WhatsApp se a mensagem saiu antes de reenviar."
            _record(db, "celery-beat", "maintenance.recover_stuck", publication.product_id, "failed", 1,
                    f"Publicação #{publication.id} ficou em envio sem confirmação")
        db.commit()
        return {"products": len(products), "publications": len(sending)}
    finally:
        db.close()

@celery_app.task(name="maintenance.cleanup_logs")
def cleanup_logs():
    try:
        days = max(1, int(os.getenv("LOG_RETENTION_DAYS", "30")))
    except ValueError:
        days = 30
    db = SessionLocal()
    try:
        result = db.execute(delete(AutomationLog).where(AutomationLog.created_at < _now() - timedelta(days=days)))
        db.commit()
        return {"deleted": result.rowcount}
    finally:
        db.close()


@celery_app.task(name="catalog.refresh")
def refresh_ml_categories():
    """Tenta atualizar o catálogo de categorias direto da API. Falhas ficam no histórico (a extensão é a alternativa)."""
    from app.catalog.service import CatalogError, sync_from_api
    db = SessionLocal()
    try:
        try:
            result = sync_from_api(db, "celery-beat")
        except CatalogError as exc:
            db.commit()
            return {"error": str(exc)}
        db.commit()
        return result
    finally:
        db.close()
