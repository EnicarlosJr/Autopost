"""Imagem padronizada para o envio "foto + texto": sempre 1080 x 1080, fundo branco, produto centralizado,
selo de publicidade (#publi, pedido pelo programa de afiliados), selo de desconto e, se configurado,
uma faixa com o nome do grupo e o Instagram (marca d'água).

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


def _font(size: int, bold: bool = True):
    names = ("DejaVuSans-Bold.ttf", "arialbd.ttf") if bold else ("DejaVuSans.ttf", "arial.ttf")
    for name in names + ("DejaVuSans.ttf",):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _fit(draw: ImageDraw.ImageDraw, text: str, size: int, max_width: int, bold: bool = True):
    """Fonte do maior tamanho (até `size`) em que o texto cabe na largura."""
    while size > 12:
        font = _font(size, bold)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font, box
        size -= 2
    font = _font(size, bold)
    return font, draw.textbbox((0, 0), text, font=font)


def _text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, font, fill, anchor_box) -> None:
    """Escreve com o canto superior esquerdo do texto (não da fonte) em xy."""
    draw.text((xy[0] - anchor_box[0], xy[1] - anchor_box[1]), text, font=font, fill=fill)


# Desenho em 2x e redução no fim: bordas e letras saem suaves (o Pillow não suaviza formas).
SS = 2
TOP_WITH_BADGE = 110
INK = BAND_COLOR
ACCENT = (255, 200, 61)


def compose(img: Image.Image, title: str = "", handle: str = "", disclosure: str = "", discount: int | None = None) -> bytes:
    """Foto 1080 x 1080: produto centralizado no branco, selo de publicidade no canto superior esquerdo,
    selo de desconto no canto superior direito e faixa com o nome do grupo e o Instagram no rodapé."""
    img = _trim(_flatten(img))
    W, m = SIZE * SS, MARGIN * SS
    band = (BAND if (title or handle) else 0) * SS
    canvas = Image.new("RGB", (W, W), (255, 255, 255))
    # Com selo, o topo ganha um respiro para o produto não ficar embaixo dele.
    top_m = (TOP_WITH_BADGE * SS) if (disclosure or (discount and discount >= 5)) else m
    area_w, area_h = W - 2 * m, W - band - top_m - m
    scale = min(area_w / img.width, area_h / img.height)
    size = (max(1, round(img.width * scale)), max(1, round(img.height * scale)))
    img = img.resize(size, Image.Resampling.LANCZOS)
    canvas.paste(img, ((W - size[0]) // 2, top_m + (area_h - size[1]) // 2))
    draw = ImageDraw.Draw(canvas)

    if band:
        top = W - band
        draw.rectangle((0, top, W, W), fill=INK)
        draw.rectangle((0, top, W, top + 6 * SS), fill=ACCENT)          # filete de cor no topo da faixa
        pad, gap = 44 * SS, 28 * SS
        mid = top + 6 * SS + (band - 6 * SS) / 2
        if title and handle:
            hfont, hbox = _fit(draw, handle, 38 * SS, int(W * 0.42), bold=True)
            hw, hh = hbox[2] - hbox[0], hbox[3] - hbox[1]
            tfont, tbox = _fit(draw, title, 44 * SS, W - 2 * pad - hw - gap)
            th = tbox[3] - tbox[1]
            _text(draw, (pad, mid - th / 2), title, tfont, (255, 255, 255), tbox)
            _text(draw, (W - pad - hw, mid - hh / 2), handle, hfont, ACCENT, hbox)
        else:
            text, color = (title, (255, 255, 255)) if title else (handle, ACCENT)
            font, box = _fit(draw, text, 46 * SS, W - 2 * pad)
            _text(draw, ((W - (box[2] - box[0])) / 2, mid - (box[3] - box[1]) / 2), text, font, color, box)

    corner = 30 * SS
    if disclosure:
        font, box = _fit(draw, disclosure, 30 * SS, int(W * 0.5))
        tw, th = box[2] - box[0], box[3] - box[1]
        px, py = 20 * SS, 13 * SS
        draw.rounded_rectangle((corner, corner, corner + tw + 2 * px, corner + th + 2 * py), radius=(th + 2 * py) // 2, fill=INK)
        _text(draw, (corner + px, corner + py), disclosure, font, (255, 255, 255), box)

    if discount and discount >= 5:
        d = 176 * SS
        x0, y0 = W - corner - d, corner
        draw.ellipse((x0, y0, x0 + d, y0 + d), fill=ACCENT)
        big, bbox = _fit(draw, f"-{discount}%", 58 * SS, int(d * 0.8))
        small, sbox = _fit(draw, "OFF", 26 * SS, d)
        bw, bh, sw, sh = bbox[2] - bbox[0], bbox[3] - bbox[1], sbox[2] - sbox[0], sbox[3] - sbox[1]
        space = 8 * SS
        y = y0 + (d - bh - space - sh) / 2
        _text(draw, (x0 + (d - bw) / 2, y), f"-{discount}%", big, INK, bbox)
        _text(draw, (x0 + (d - sw) / 2, y + bh + space), "OFF", small, INK, sbox)

    canvas = canvas.resize((SIZE, SIZE), Image.Resampling.LANCZOS)
    out = BytesIO()
    canvas.save(out, format="JPEG", quality=92, optimize=True, progressive=True)
    return out.getvalue()


def social_image(product, title: str = "", handle: str = "", disclosure: str = "", discount: int | None = None) -> bytes:
    """Imagem pronta (com cache em disco) para o produto, a marca d'água, o selo de publicidade e o desconto."""
    title, handle = " ".join((title or "").split())[:60], " ".join((handle or "").split())[:40]
    disclosure = " ".join((disclosure or "").split())[:40]
    discount = discount if discount and discount >= 5 else None
    key = hashlib.sha1(f"v2|{product.image_source_url}|{product.image_url}|{title}|{handle}|{disclosure}|{discount}".encode()).hexdigest()[:12]
    folder = media_dir() / "social"
    path = folder / f"{product.id}-{key}.jpg"
    if path.exists():
        return path.read_bytes()
    data = compose(best_source(product.image_source_url or "", product.id), title, handle, disclosure, discount)
    folder.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data
