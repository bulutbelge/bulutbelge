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


# ---------- Yeniden kodlamadan meta veri silme (Office içindeki bulgusuz görseller) ----------

# JPEG: kalan işaretler (APP0 JFIF, APP14 Adobe renk dönüşümü, APP2 yalnızca ICC renk profili); diğer APPn
# (EXIF, XMP, IPTC, MPF ek görselleri) ve COM silinir. EOI'den sonrası (ek görsel, gizli veri) atılır.
_JPEG_KEEP_APP = {0xE0: b"JFIF\x00", 0xEE: b"Adobe", 0xE2: b"ICC_PROFILE\x00"}
# PNG: görüntü için gereken ve renk/oran yardımcı parçaları; metin (tEXt/zTXt/iTXt), eXIf, tIME ve bilinmeyen
# yardımcı parçalar silinir. Bilinmeyen zorunlu parça (büyük harfle başlar) kalır, yoksa dosya bozulur.
_PNG_KEEP = {b"PLTE", b"tRNS", b"cHRM", b"gAMA", b"iCCP", b"sBIT", b"sRGB", b"bKGD", b"pHYs", b"hIST",
             b"acTL", b"fcTL", b"fdAT", b"cICP"}


def _jpeg_orientation_app1(data: bytes) -> bytes:
    """Özgün EXIF'teki yön bilgisi (yalnızca o) korunur: silinirse görsel yan dönmüş görünebilir."""
    try:
        with Image.open(io.BytesIO(data)) as im:
            orientation = im.getexif().get(ExifTags.Base.Orientation)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return b""
    if not isinstance(orientation, int) or orientation in (0, 1):
        return b""
    exif = Image.Exif()
    exif[ExifTags.Base.Orientation] = orientation
    body = exif.tobytes()
    return b"\xff\xe1" + (len(body) + 2).to_bytes(2, "big") + body


def _strip_jpeg(data: bytes) -> bytes:
    if data[:2] != b"\xff\xd8":
        raise ImageError("JPEG değil")
    out = bytearray(b"\xff\xd8")
    out += _jpeg_orientation_app1(data)
    i, n = 2, len(data)
    while i < n:
        if data[i] != 0xFF:
            raise ImageError("JPEG bozuk")
        while i < n and data[i] == 0xFF:
            i += 1  # dolgu
        if i >= n:
            raise ImageError("JPEG bozuk")
        marker = data[i]
        i += 1
        if marker == 0xD9:  # EOI: sonrası atılır
            out += b"\xff\xd9"
            return bytes(out)
        if 0xD0 <= marker <= 0xD7 or marker == 0x01:
            out += bytes((0xFF, marker))
            continue
        if i + 2 > n:
            raise ImageError("JPEG bozuk")
        length = int.from_bytes(data[i : i + 2], "big")
        segment = data[i + 2 : i + length]
        end = i + length
        keep = not (0xE0 <= marker <= 0xEF or marker == 0xFE)
        if marker in _JPEG_KEEP_APP and segment.startswith(_JPEG_KEEP_APP[marker]):
            keep = True
            if marker == 0xE0 and length > 16:  # JFIF içindeki küçük önizleme resmi atılır
                segment = segment[:12] + b"\x00\x00"
                length = 16
        if keep:
            out += bytes((0xFF, marker)) + length.to_bytes(2, "big") + segment
        i = end
        if marker == 0xDA:  # SOS: sıkıştırılmış veri bir sonraki gerçek işarete kadar sürer
            start = i
            while i + 1 < n and not (data[i] == 0xFF and data[i + 1] not in (0x00, 0xFF) and not 0xD0 <= data[i + 1] <= 0xD7):
                i += 1
            out += data[start:i]
    raise ImageError("JPEG bozuk (EOI yok)")


def _strip_png(data: bytes) -> bytes:
    sig = b"\x89PNG\r\n\x1a\n"
    if not data.startswith(sig):
        raise ImageError("PNG değil")
    out = bytearray(sig)
    i = len(sig)
    while i + 8 <= len(data):
        length = int.from_bytes(data[i : i + 4], "big")
        kind = data[i + 4 : i + 8]
        chunk = data[i : i + 12 + length]
        if len(chunk) != 12 + length:
            raise ImageError("PNG bozuk")
        if kind[:1].isupper() or kind in _PNG_KEEP:
            out += chunk
        i += 12 + length
        if kind == b"IEND":
            return bytes(out)
    raise ImageError("PNG bozuk (IEND yok)")


def _strip_webp(data: bytes) -> bytes:
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ImageError("WEBP değil")
    body = bytearray()
    i = 12
    while i + 8 <= len(data):
        kind = data[i : i + 4]
        size = int.from_bytes(data[i + 4 : i + 8], "little")
        chunk = bytearray(data[i : i + 8 + size + (size & 1)])
        if len(chunk) < 8 + size:
            raise ImageError("WEBP bozuk")
        if kind == b"VP8X":
            chunk[8] &= ~0x0C & 0xFF  # EXIF ve XMP var bayrakları
        if kind not in (b"EXIF", b"XMP "):
            body += chunk
        i += 8 + size + (size & 1)
    return b"RIFF" + (len(body) + 4).to_bytes(4, "little") + b"WEBP" + bytes(body)


def _strip_by_reencode(data: bytes, fmt: str) -> bytes:
    """Kayıpsız biçimler (TIFF): pikseller aynen yeni dosyaya yazılır, özgün etiketler (EXIF, XMP, IPTC) taşınmaz."""
    img = _open_image(io.BytesIO(data))
    with img:
        frames = []
        for i in range(max(1, int(getattr(img, "n_frames", 1)))):
            if i:
                img.seek(i)
            frame = img.copy()
            frame.info = {}
            frames.append(frame)
    out = io.BytesIO()
    frames[0].save(out, fmt, save_all=len(frames) > 1, append_images=frames[1:], compression="tiff_lzw")
    return out.getvalue()


def strip_metadata(data: bytes, suffix: str) -> bytes:
    """Görselin EXIF/XMP/IPTC/metin meta verisini siler; pikseller yeniden kodlanmaz (JPEG kalitesi bozulmaz).

    JPEG'de yalnızca yön bilgisi korunur. BMP meta veri taşımaz, olduğu gibi döner. Görsel
    çözümlenemezse ImageError (çağıran dosyayı yazmaz).
    """
    ext = suffix.lower()
    try:
        if ext in (".jpg", ".jpeg"):
            return _strip_jpeg(data)
        if ext == ".png":
            return _strip_png(data)
        if ext == ".webp":
            return _strip_webp(data)
        if ext in (".tif", ".tiff"):
            return _strip_by_reencode(data, "TIFF")
    except (IndexError, ValueError, OSError) as exc:
        raise ImageError("Görselin meta verisi silinemedi") from exc
    return data


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

