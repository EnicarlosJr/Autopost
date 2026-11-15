from io import BytesIO
from PIL import Image
from app.products import image_fetch

def test_image_download_normalizes_and_saves_local_copy(monkeypatch,tmp_path):
    source=BytesIO(); Image.new("RGB",(2000,1000),(255,0,0)).save(source,format="PNG"); raw=source.getvalue()
    class Response:
        is_redirect=False
        headers={"Content-Type":"image/png","Content-Length":str(len(raw))}
        def raise_for_status(self): pass
        def iter_content(self,size): yield raw
    monkeypatch.setattr(image_fetch,"_validate_public_url",lambda url:None)
    monkeypatch.setattr(image_fetch.requests,"get",lambda *args,**kwargs:Response())
    monkeypatch.setenv("MEDIA_DIR",str(tmp_path))
    monkeypatch.setenv("APP_PUBLIC_URL","http://localhost:8000")
    result=image_fetch.download_product_image("https://cdn.example/item.png",42)
    assert result.startswith("http://localhost:8000/media/products/42.jpg?v=")
    with Image.open(tmp_path/"42.jpg") as saved:
        assert saved.format=="JPEG"
        assert saved.size==(1600,800)
