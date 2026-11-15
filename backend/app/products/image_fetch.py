from io import BytesIO
import requests
from PIL import Image, ImageOps, UnidentifiedImageError
from urllib.parse import urljoin
from app.products.extractor import _validate_public_url
from app.products.media import image_path, media_dir, public_image_url

MAX_IMAGE_BYTES=10_000_000

def download_product_image(url:str,product_id:int)->str:
    """Download only public image URLs, bound response size and normalize via Pillow."""
    current=url
    headers={"User-Agent":"Autopost/1.0 (+product image preview)"}
    for _ in range(6):
        _validate_public_url(current)
        response=requests.get(current,headers=headers,timeout=15,stream=True,allow_redirects=False)
        if response.is_redirect:
            location=response.headers.get("Location")
            response.close()
            if not location: raise ValueError("Image redirect has no destination")
            current=urljoin(current,location)
            continue
        try:
            response.raise_for_status()
        except Exception:
            response.close(); raise
        content_type=response.headers.get("Content-Type","").split(";",1)[0].lower()
        if not content_type.startswith("image/"): raise ValueError("Product image URL did not return an image")
        if int(response.headers.get("Content-Length","0") or 0)>MAX_IMAGE_BYTES: raise ValueError("Product image exceeds 10 MB")
        chunks=[]; size=0
        for chunk in response.iter_content(64*1024):
            if not chunk: continue
            size+=len(chunk)
            if size>MAX_IMAGE_BYTES: raise ValueError("Product image exceeds 10 MB")
            chunks.append(chunk)
        raw=b"".join(chunks)
        break
    else: raise ValueError("Too many image redirects")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG","PNG","WEBP","GIF"}: raise ValueError("Unsupported image format")
            if source.width*source.height>30_000_000: raise ValueError("Product image resolution is too large")
            image=ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            media_dir().mkdir(parents=True,exist_ok=True)
            image.save(image_path(product_id),format="JPEG",quality=86,optimize=True)
    except UnidentifiedImageError as exc: raise ValueError("Invalid product image") from exc
    return public_image_url(product_id)
