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
from collections.abc import Iterable, Iterator
from pathlib import Path

import pymupdf
from PIL import ExifTags, Image, ImageOps, UnidentifiedImageError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
# Sıkıştırma bombasına karşı üst sınır (yaklaşık 12000 x 8000).
MAX_PIXELS = 100_000_000
# Çok kareli görsel (TIFF, WEBP, APNG): kare sayısı ve karelerin toplam pikseli (güvenlik taraması F10/F21).
# Kare sayısı ve boyutu dosya başlığından gelir; küçük bir dosya binlerce büyük kare bildirebilir. Sınırlar
# ZIP, e-posta, UDF ve Office içindeki görseller için de geçerlidir (hepsi bu modülden açılır).
# Tek kare için Pillow'un hata eşiği (2 x MAX_PIXELS) korunur; ilk kare için Pillow zaten bunu uygular.
MAX_FRAMES = 1000
MAX_TOTAL_PIXELS = 1_000_000_000

_SAVE_FORMAT = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".tif": "TIFF", ".tiff": "TIFF", ".bmp": "BMP", ".webp": "WEBP"}


class ImageError(Exception):
    """Kullanıcıya gösterilecek görsel hatası."""


def is_image(path: str | Path) -> bool:
    return Path(path).suffix.lower() in IMAGE_EXTS


def _iter_frames(img: Image.Image) -> Iterator[Image.Image]:
    """Kareleri tek tek çözer; bellekte aynı anda tek kare tutulur. Sınır aşılırsa ImageError."""
    try:
        n = max(1, int(getattr(img, "n_frames", 1)))
        if n > MAX_FRAMES:
            raise ImageError(f"Görselde çok fazla kare var (en çok {MAX_FRAMES})")
        total = 0
        for i in range(n):
            if i:
                img.seek(i)
            w, h = img.size
            if w * h > 2 * MAX_PIXELS:
                raise ImageError("Görselin bir karesi çok büyük")
            total += w * h
            if total > MAX_TOTAL_PIXELS:
                raise ImageError("Görselin karelerinin toplam boyutu sınırı aşıyor")
            frame = ImageOps.exif_transpose(img.copy())
            if frame.mode not in ("RGB", "L"):
                frame = frame.convert("RGB")
            yield frame
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, EOFError):
        raise ImageError("Dosya görsel olarak açılamadı") from None


def _frames_to_doc(frames: Iterable[Image.Image]) -> pymupdf.Document:
    doc = pymupdf.open()
    try:
        for frame in frames:
            buf = io.BytesIO()
            frame.save(buf, "PNG")
            page = doc.new_page(width=frame.width, height=frame.height)
            page.insert_image(page.rect, stream=buf.getvalue())
    except BaseException:
        doc.close()
        raise
    return doc


def _open_image(src: str | Path | io.BytesIO, message: str = "Dosya görsel olarak açılamadı") -> Image.Image:
    Image.MAX_IMAGE_PIXELS = MAX_PIXELS
    try:
        return Image.open(src)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, EOFError):
        raise ImageError(message) from None


def image_to_doc(path: str | Path) -> pymupdf.Document:
    """Tekli ya da çok sayfalı görseli (TIFF dahil) bellek içi PDF olarak açar (EXIF yönlü)."""
    with _open_image(path) as img:
        return _frames_to_doc(_iter_frames(img))


def image_bytes_to_doc(data: bytes) -> pymupdf.Document:
    """Ham görsel baytlarını (ör. Office media/* içi) bellek içi PDF olarak açar (EXIF yönlü)."""
    with _open_image(io.BytesIO(data), "Görsel baytları açılamadı") as img:
        return _frames_to_doc(_iter_frames(img))


def metadata_warnings(path: str | Path) -> list[str]:
    """Görselin meta verisinde kişisel olabilecek bilgiler (kaydedilen dosyada silinir)."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
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


def save_doc_as_image(doc: pymupdf.Document, target: Path) -> None:
    """Tekli veya çok sayfalı (TIFF) görsel belgeyi meta verisiz olarak kaydeder."""
    target.write_bytes(save_doc_to_image_bytes(doc, target.suffix))


def save_doc_to_image_bytes(doc: pymupdf.Document, suffix: str) -> bytes:
    """Görsel belgeyi hedef uzantı biçiminde meta verisiz ham bayt olarak döndürür."""
    fmt = _SAVE_FORMAT.get(suffix.lower(), "PNG")
    out = io.BytesIO()
    if doc.page_count <= 1:
        pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(1, 1), annots=False, alpha=False)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        options = {"quality": 92} if fmt in ("JPEG", "WEBP") else {}
        img.save(out, fmt, **options)
        return out.getvalue()
    frames: list[Image.Image] = []
    for page in doc:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(1, 1), annots=False, alpha=False)
        frames.append(Image.frombytes("RGB", (pix.width, pix.height), pix.samples))
    if fmt == "TIFF":
        frames[0].save(out, "TIFF", save_all=True, append_images=frames[1:])
    else:
        frames[0].save(out, fmt)
    return out.getvalue()

