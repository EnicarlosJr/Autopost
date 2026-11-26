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
from app.school_lists.public import router as school_public_router
from app.school_lists.router import router as school_lists_router, searches_router as school_searches_router, visitors_router as school_visitors_router

MEDIA_DIR = Path(os.getenv("MEDIA_DIR", "storage/products"))
PRODUCTION = os.getenv("APP_ENV", "").strip().lower() == "production"
_EXAMPLE_WORDS = ("replace", "troque", "change-this", "changeme", "autopost")


def check_production_secrets() -> None:
    """Em produção, não sobe com segredo de exemplo ou fraco (servidor aberto na internet)."""
    if not PRODUCTION:
        return
    problems = []
    secret = os.getenv("JWT_SECRET", "")
    if len(secret) < 32 or any(w in secret.lower() for w in _EXAMPLE_WORDS):
        problems.append("JWT_SECRET precisa ter 32+ caracteres aleatórios (openssl rand -base64 48)")
    password = os.getenv("ADMIN_PASSWORD", "")
    if password and (len(password) < 12 or any(w in password.lower() for w in _EXAMPLE_WORDS)):
        problems.append("ADMIN_PASSWORD precisa ter 12+ caracteres e não pode ser a do exemplo")
    if not os.getenv("APP_PUBLIC_URL", "").startswith("https://"):
        problems.append("APP_PUBLIC_URL precisa começar com https://")
    if problems:
        raise RuntimeError("Configuração de produção insegura: " + "; ".join(problems) + ". Ajuste o .env.production.")

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
    check_production_secrets()
    seed_defaults()
    yield

_docs = os.getenv("DOCS_ENABLED", "true").strip().lower() not in ("0", "false", "no")
app = FastAPI(title="Autopost Affiliate Automation", version="0.7.0",
              description="Gestão de produtos, extração de metadados e fila de ofertas.", lifespan=lifespan,
              docs_url="/docs" if _docs else None, redoc_url="/redoc" if _docs else None,
              openapi_url="/openapi.json" if _docs else None)
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
app.include_router(school_lists_router, dependencies=protected)
app.include_router(school_visitors_router, dependencies=protected)
app.include_router(school_searches_router, dependencies=protected)
# Páginas públicas para os pais (sem login): /escolas/<escola> e /escolas/<escola>/<série>.
app.include_router(school_public_router)

MEDIA_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/media/products", StaticFiles(directory=str(MEDIA_DIR)), name="product-media")

@app.get("/api/health")
def health():
    return {"status": "ok"}
