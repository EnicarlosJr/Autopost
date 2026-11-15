import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from app.core.deps import require_user
from app.core.security import hash_password
from app.database.session import SessionLocal
from app.models.automation import AutomationRule
from app.models.user import User
from app.auth.router import router as auth_router
from app.automations.router import router as automations_router
from app.products.images import router as product_images_router
from app.products.router import router as products_router
from app.publications.router import router as publications_router
from app.searches.router import listings_router, router as searches_router, schedules_router
from app.campaigns.router import group_sets_router, router as campaigns_router, searches_router as campaign_searches_router
from app.catalog.router import niches_router, router as catalog_router

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "storage/products"))

def seed_defaults() -> None:
    """Cria a regra principal e o administrador inicial. O schema vem do Alembic."""
    with SessionLocal() as db:
        if db.scalar(select(AutomationRule.id).limit(1)) is None:
            db.add(AutomationRule(name="Regra principal", enabled=True, process_on_create=True, generate_publication=False, require_approval=True))
        email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        password = os.getenv("ADMIN_PASSWORD", "")
        if email and password and db.scalar(select(User.id).where(User.email == email)) is None:
            db.add(User(email=email, password_hash=hash_password(password), is_active=True))
        db.commit()

@asynccontextmanager
async def lifespan(_app: FastAPI):
    seed_defaults()
    yield

app = FastAPI(title="Autopost Affiliate Automation", version="0.7.0",
              description="Gestão de produtos, extração de metadados e fila de ofertas.", lifespan=lifespan)
origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
# A extensão do Autopost (chrome-extension://<id>) também baixa as imagens dos produtos.
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_origin_regex=r"chrome-extension://[a-p]{32}",
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["X-Total-Count"])

protected = [Depends(require_user)]
app.include_router(auth_router)
app.include_router(products_router, dependencies=protected)
app.include_router(product_images_router, dependencies=protected)
app.include_router(publications_router, dependencies=protected)
app.include_router(automations_router, dependencies=protected)
app.include_router(searches_router, dependencies=protected)
app.include_router(listings_router, dependencies=protected)
app.include_router(schedules_router, dependencies=protected)
app.include_router(campaigns_router, dependencies=protected)
app.include_router(campaign_searches_router, dependencies=protected)
app.include_router(group_sets_router, dependencies=protected)
app.include_router(catalog_router, dependencies=protected)
app.include_router(niches_router, dependencies=protected)

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/products", StaticFiles(directory=str(MEDIA_DIR)), name="product-media")

@app.get("/api/health")
def health():
    return {"status": "ok"}
