import os
import time
from pathlib import Path

def media_dir() -> Path:
    return Path(os.getenv("MEDIA_DIR", "storage/products"))

def image_path(product_id: int) -> Path:
    return media_dir() / f"{product_id}.jpg"

def public_image_url(product_id: int) -> str:
    """URL pública da cópia local; o parâmetro v evita o cache do navegador após troca."""
    base = os.getenv("APP_PUBLIC_URL", "http://localhost:8000").rstrip("/")
    return f"{base}/media/products/{product_id}.jpg?v={int(time.time())}"

def remove_image(product_id: int) -> None:
    try:
        image_path(product_id).unlink(missing_ok=True)
    except OSError:
        pass
