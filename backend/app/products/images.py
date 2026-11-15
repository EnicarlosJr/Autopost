from io import BytesIO
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy.orm import Session
from app.database.session import get_db
from app.models.product import Product
from app.products.media import image_path, media_dir, public_image_url

router=APIRouter(prefix="/api/products",tags=["products"])
MAX_BYTES=12_000_000

@router.post("/{product_id}/image")
async def upload_product_image(product_id:int,file:UploadFile=File(...),db:Session=Depends(get_db)):
    product=db.get(Product,product_id)
    if not product: raise HTTPException(404,"Produto não encontrado")
    raw=await file.read(MAX_BYTES+1)
    if len(raw)>MAX_BYTES: raise HTTPException(413,"Imagem excede 12 MB")
    try:
        with Image.open(BytesIO(raw)) as source:
            if source.format not in {"JPEG","PNG","WEBP"}: raise HTTPException(415,"Formatos aceitos: JPEG, PNG e WEBP")
            if source.width*source.height>30_000_000: raise HTTPException(413,"Imagem com resolução excessiva")
            image=ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((1600,1600),Image.Resampling.LANCZOS)
            media_dir().mkdir(parents=True,exist_ok=True)
            image.save(image_path(product_id),format="JPEG",quality=86,optimize=True)
    except UnidentifiedImageError as exc: raise HTTPException(415,"Arquivo não é uma imagem válida") from exc
    product.image_url=public_image_url(product_id)
    db.commit(); db.refresh(product)
    return {"product_id":product.id,"image_url":product.image_url,"width":image.width,"height":image.height}
