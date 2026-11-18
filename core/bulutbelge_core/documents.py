"""Desteklenen belge biçimleri ve biçime göre doğru modülü seçme.

- "pdf":    PDF (metin katmanlı ya da taranmış)          → pdf.py
- "gorsel": fotoğraf ve görseller (PNG, JPG, TIFF…)      → pdf.py + image.py
- "metin":  XML, TXT, CSV                                → textdoc.py
- "word":   Word (.docx)                                 → word.py  (office.py)
- "sunum":  PowerPoint (.pptx)                           → office.py
- "tablo":  Excel (.xlsx)                                → office.py
- "udf":    UYAP belgesi (.udf, ZIP içinde content.xml)  → udf.py
- "eposta": E-posta (.eml; .msg kapsam dışı)             → eposta.py
- "arsiv":  ZIP arşivi (.zip)                            → archive.py

Yeni bir biçim eklemek için: tarama/maskeleme modülünü yazın, uzantısını
aşağıdaki tabloya ekleyin ve masaüstü motorundaki komutlara bağlayın.
"""

from __future__ import annotations

import os
from pathlib import Path

from .eposta import EML_EXTS
from .archive import ARCHIVE_EXTS
from .image import IMAGE_EXTS
from .pdf import PdfError
from .textdoc import TEXT_EXTS
from .udf import UDF_EXTS
from .word import WORD_EXTS

PDF_EXTS = {".pdf"}
SLIDE_EXTS = {".pptx"}
SHEET_EXTS = {".xlsx"}
SUPPORTED_EXTS = PDF_EXTS | IMAGE_EXTS | TEXT_EXTS | WORD_EXTS | SLIDE_EXTS | SHEET_EXTS | EML_EXTS | UDF_EXTS | ARCHIVE_EXTS
_OLD_OFFICE = {".doc": "Word", ".xls": "Excel", ".ppt": "PowerPoint"}


def kind_of(path: str | os.PathLike) -> str:
    ext = Path(path).suffix.lower()
    if ext in PDF_EXTS:
        return "pdf"
    if ext in IMAGE_EXTS:
        return "gorsel"
    if ext in TEXT_EXTS:
        return "metin"
    if ext in WORD_EXTS:
        return "word"
    if ext in SLIDE_EXTS:
        return "sunum"
    if ext in SHEET_EXTS:
        return "tablo"
    if ext in EML_EXTS:
        return "eposta"
    if ext in UDF_EXTS:
        return "udf"
    if ext in ARCHIVE_EXTS:
        return "arsiv"
    if ext in _OLD_OFFICE:
        app = _OLD_OFFICE[ext]
        raise PdfError(f"Eski {app} biçimi ({ext}) desteklenmiyor; {app}'de {ext}x olarak kaydedip deneyin")
    raise PdfError(f"Bu dosya türü desteklenmiyor ({ext or 'uzantısız'})")


def is_supported(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_EXTS
