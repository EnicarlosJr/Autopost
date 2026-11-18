"""Imagem padronizada para o envio "foto + texto": sempre 1080 x 1080, fundo branco, produto centralizado
e, se configurado, uma faixa com o nome do grupo e o Instagram (marca d'água).

A foto é buscada na maior qualidade que a loja oferece (no Mercado Livre, a versão 2X/"F" do mesmo arquivo)
e, se nada der certo, usa a cópia local do produto.
"""
import hashlib
import re
from io import BytesIO
from urllib.parse import urljoin
import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageOps
from app.products.extractor import _validate_public_url
from app.products.media import image_path, media_dir

SIZE = 1080
MARGIN = 48
BAND = 128
MAX_BYTES = 12_000_000
BAND_COLOR = (17, 18, 32)
ML_FILE = re.compile(r"mlstatic\.com/(?:D_)?(?:NQ_NP_)?(?:2X_)?(?:Q_NP_)?(\d+-ML[A-Z]{1,2}\d+_\d+)-[A-Z]\.(?:webp|jpe?g|png)", re.I)


def candidates(url: str) -> list[str]:
    """Versões da mesma foto, da maior para a menor."""
    m = ML_FILE.search(url or "")
    if not m:
        return [url] if url else []
    key, base = m.group(1), "https://http2.mlstatic.com/"
    return [f"{base}D_NQ_NP_2X_{key}-F.webp", f"{base}D_NQ_NP_{key}-F.webp", f"{base}D_{key}-F.jpg",
            f"{base}D_NQ_NP_{key}-O.webp", url]


def _download(url: str) -> Image.Image:
    current = url
    for _ in range(5):
        _validate_public_url(current)
        r = requests.get(current, headers={"User-Agent": "Mozilla/5.0 (Autopost)"}, timeout=15, stream=True, allow_redirects=False)
        if r.is_redirect:
            current = urljoin(current, r.headers.get("Location", "")); r.close(); continue
        r.raise_for_status()
        raw = b""
        for chunk in r.iter_content(64 * 1024):
            raw += chunk
            if len(raw) > MAX_BYTES:
                raise ValueError("imagem grande demais")
        img = Image.open(BytesIO(raw))
        if img.width * img.height > 40_000_000:
            raise ValueError("resolução grande demais")
        img.load()
        return img
    raise ValueError("redirecionamentos demais")


def best_source(source_url: str, product_id: int) -> Image.Image:
    """A maior versão disponível da foto (ou a cópia local)."""
    best = None
    for url in candidates(source_url):
        try:
            img = _download(url)
        except Exception:
            continue
        if best is None or img.width * img.height > best.width * best.height:
            best = img
        if min(best.size) >= 1000:
            break
    if best is None and image_path(product_id).exists():
        best = Image.open(image_path(product_id)); best.load()
    if best is None:
        raise ValueError("O produto não tem foto disponível.")
    return best


def _flatten(img: Image.Image) -> Image.Image:
    img = ImageOps.exif_transpose(img)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    return img.convert("RGB")


def _trim(img: Image.Image) -> Image.Image:
    """Corta as bordas brancas para o produto ocupar o mesmo espaço em todas as fotos."""
    diff = ImageChops.difference(img, Image.new("RGB", img.size, (255, 255, 255))).convert("L")
    box = diff.point(lambda p: 255 if p > 14 else 0).getbbox()
    if not box:
        return img
    pad = int(max(img.size) * 0.01)
    box = (max(0, box[0] - pad), max(0, box[1] - pad), min(img.width, box[2] + pad), min(img.height, box[3] + pad))
    return img.crop(box)


def _font(size: int):
    for name in ("DejaVuSans-Bold.ttf", "DejaVuSans.ttf", "arialbd.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def compose(img: Image.Image, title: str = "", handle: str = "") -> bytes:
    img = _trim(_flatten(img))
    band = BAND if (title or handle) else 0
    canvas = Image.new("RGB", (SIZE, SIZE), (255, 255, 255))
    area_w, area_h = SIZE - 2 * MARGIN, SIZE - band - 2 * MARGIN
    scale = min(area_w / img.width, area_h / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(size, Image.Resampling.LANCZOS)
    canvas.paste(img, ((SIZE - size[0]) // 2, MARGIN + (area_h - size[1]) // 2))
    if band:
        draw = ImageDraw.Draw(canvas)
        draw.rectangle((0, SIZE - band, SIZE, SIZE), fill=BAND_COLOR)
        lines = [(title, _font(44), (255, 255, 255)), (handle, _font(34), (255, 200, 61))]
        lines = [l for l in lines if l[0]]
        heights = [draw.textbbox((0, 0), t, font=f)[3] - draw.textbbox((0, 0), t, font=f)[1] for t, f, _ in lines]
        gap = 10
        y = SIZE - band + (band - sum(heights) - gap * (len(lines) - 1)) // 2
        for (text, font, color), h in zip(lines, heights):
            box = draw.textbbox((0, 0), text, font=font)
            draw.text(((SIZE - (box[2] - box[0])) // 2 - box[0], y - box[1]), text, font=font, fill=color)
            y += h + gap
    out = BytesIO()
    canvas.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()


def social_image(product, title: str = "", handle: str = "") -> bytes:
    """Imagem pronta (com cache em disco) para o produto e a marca d'água pedida."""
    title, handle = " ".join((title or "").split())[:60], " ".join((handle or "").split())[:40]
    key = hashlib.sha1(f"v1|{product.image_source_url}|{product.image_url}|{title}|{handle}".encode()).hexdigest()[:12]
    folder = media_dir() / "social"
    path = folder / f"{product.id}-{key}.jpg"
    if path.exists():
        return path.read_bytes()
    data = compose(best_source(product.image_source_url or "", product.id), title, handle)
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
