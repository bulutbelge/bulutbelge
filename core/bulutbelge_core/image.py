"""Fotoğraf ve görsel dosyaları (PNG, JPG, TIFF, BMP, WEBP).

Görsel, bellekte tek sayfalık bir PDF'e çevrilir; böylece tarama, önizleme,
"Alan seç" ve maskeleme yöntemleri PDF ile aynı yoldan çalışır. Sayfada
1 pt = 1 piksel olduğundan koordinatlar görselin pikselleridir.

Maskeleme sonunda sayfa görselin kendi boyutunda yeniden çizilir ve kaynakla
aynı biçimde kaydedilir. Yeni dosya orijinalden hiçbir meta veri taşımaz:
EXIF'teki konum (GPS), kamera, çekim tarihi ve küçük önizleme resmi gider.
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
# Sıkıştırma bombasına karşı üst sınır (yaklaşık 12000 x 8000).
MAX_PIXELS = 100_000_000

_SAVE_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".webp": "WEBP"}


class ImageError(Exception):
    """Kullanıcıya gösterilecek görsel hatası."""


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def _load(path: str | Path) -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        img = Image.open(path)
        img.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        raise ImageError("Dosya görsel olarak açılamadı") from None
    if getattr(img, "n_frames", 1) > 1:
        raise ImageError("Çok sayfalı görseller (TIFF, animasyon) henüz desteklenmiyor")
    return img


def image_to_doc(path: str | Path) -> pymupdf.Document:
    """Görseli tek sayfalık bellek içi PDF olarak açar (EXIF'e göre döndürülmüş)."""
    img = _load(path)
    # Telefon fotoğrafları çoğunlukla yan kaydedilir; yön EXIF'te yazar.
    img = ImageOps.exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page(width=img.width, height=img.height)
    page.insert_image(page.rect, stream=buf.getvalue())
    return doc


def metadata_warnings(path: str | Path) -> list[str]:
    """Görselin meta verisinde kişisel olabilecek bilgiler (kaydedilen dosyada silinir)."""
    try:
        exif = _load(path).getexif()
    except ImageError:
        return []
    found = []
    if exif.get_ifd(ExifTags.IFD.GPSInfo):
        found.append("konum (GPS)")
    if exif.get(ExifTags.Base.Model) or exif.get(ExifTags.Base.Make):
        found.append("cihaz bilgisi")
    if exif.get(ExifTags.Base.DateTime) or exif.get_ifd(ExifTags.IFD.Exif).get(ExifTags.Base.DateTimeOriginal):
        found.append("çekim tarihi")
    if exif.get(ExifTags.Base.Artist) or exif.get(ExifTags.Base.Copyright):
        found.append("sahip bilgisi")
    if not found:
        return []
    return [f"Görselin meta verisinde {', '.join(found)} var. Kaydedilen dosyada tüm meta veri silinir."]


def save_page_as_image(page: pymupdf.Page, target: Path) -> None:
    """Sayfayı görselin kendi boyutunda çizer ve hedefin biçiminde kaydeder (meta verisiz)."""
    pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), annots=False, alpha=False)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    fmt = _SAVE_FORMAT.get(target.suffix.lower(), "PNG")
    options = {"quality": 92} if fmt in ("JPEG", "WEBP") else {}
    img.save(target, fmt, **options)
