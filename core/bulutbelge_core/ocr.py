"""Görselden metin okuma (OCR).

PyMuPDF'in içindeki MuPDF, Tesseract OCR motoruyla birlikte derlenmiştir; ayrıca
program kurmak gerekmez. Eksik olan yalnızca dil dosyalarıdır (`tur.traineddata`,
`eng.traineddata`). Motor bunların yerini `BULUTBELGE_TESSDATA` ortam
değişkeniyle bildirir. Dosyalar yoksa OCR kapalıdır: fotoğraflar ve taranmış
sayfalar yine açılır ama yalnızca "Alan seç" ile elle maskelenebilir.

OCR sonucu bellekte kalır, diske yazılmaz.
"""

from __future__ import annotations

import os
from pathlib import Path

import pymupdf

LANGUAGES = "tur+eng"
ENV_VAR = "BULUTBELGE_TESSDATA"

# Taranmış PDF sayfaları bu çözünürlükte okunur. Fotoğraflarda çözünürlük
# görselin kendi piksel boyutundan hesaplanır (bkz. ocr_dpi).
SCAN_DPI = 300
# OCR'ın küçük yazıyı okuyabilmesi için fotoğrafın en az bu genişlikte (px) işlenmesi.
_MIN_OCR_WIDTH = 2000


def tessdata_dir() -> str | None:
    """Dil dosyalarının klasörü; kullanılamıyorsa None."""
    raw = os.environ.get(ENV_VAR)
    if not raw:
        return None
    path = Path(raw)
    if all((path / f"{lang}.traineddata").is_file() for lang in LANGUAGES.split("+")):
        return str(path)
    return None


def ocr_available() -> bool:
    return tessdata_dir() is not None


def ocr_dpi(page: pymupdf.Page, is_image: bool) -> int:
    if not is_image:
        # Taranmış PDF sayfasında tek/ana görselin kendi çözünürlüğünü kullanmak
        # kesirli yeniden örnekleme kaynaklı karakter bozulmalarını (ör. @ -> d) önler.
        imgs = page.get_images()
        if imgs and page.rect.width > 0:
            max_w = max((img[2] for img in imgs if len(img) > 2 and img[2]), default=0)
            if max_w > 0:
                native = round(max_w * 72 / page.rect.width)
                if 140 <= native <= 400:
                    return native
        return SCAN_DPI
    # Görsel belgede 1 pt = 1 px; tam sayı katlarıyla (72, 144, 216 DPI) ölçekleme yapılır.
    # Kesirli ölçekleme (ör. 1.56x) PNG ekran görüntülerindeki ince karakterleri bozar.
    w = max(page.rect.width, 1)
    scale = 1 if w >= 900 else (2 if w >= 450 else 3)
    return 72 * scale


def ocr_textpage(page: pymupdf.Page, is_image: bool) -> pymupdf.TextPage:
    tessdata = tessdata_dir()
    if tessdata is None:
        raise RuntimeError("OCR dil dosyaları bulunamadı")
    return page.get_textpage_ocr(
        flags=pymupdf.TEXT_PRESERVE_WHITESPACE,
        language=LANGUAGES,
        dpi=ocr_dpi(page, is_image),
        full=True,
        tessdata=tessdata,
    )
