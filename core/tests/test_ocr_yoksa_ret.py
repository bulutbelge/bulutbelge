"""K3: OCR kullanılamıyorsa metin katmanı olmayan sayfa ya da görsel sessizce maskesiz yazılmaz.

`ocr_available` yamalanır (monkeypatch). Tüm veriler sahtedir.
"""

from __future__ import annotations

import io
from pathlib import Path

import docx
import pymupdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from bulutbelge_core import ocr, office, pdf
from bulutbelge_core.pdf import OcrUnavailable, mask_pdf, scan_pdf
from bulutbelge_core.readout import read_masked
from bulutbelge_core.rules import Rules

from fake_data import fake_tc

TC = fake_tc("123456789")


def _scan_png(text: str) -> bytes:
    img = Image.new("RGB", (1200, 300), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 48)
    except OSError:
        font = ImageFont.load_default()
    draw.text((40, 110), text, fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _scanned_pdf(path: Path) -> Path:
    """1. sayfa metinli, 2. sayfa yalnızca görsel (taranmış sayfa)."""
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Kapak sayfasi: basvuru dosyasi")
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(40, 100, 560, 230), stream=_scan_png(f"TC Kimlik No: {TC}"))
    doc.save(path)
    doc.close()
    return path


@pytest.fixture
def no_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "ocr_available", lambda: False)
    monkeypatch.setattr(pdf, "ocr_available", lambda: False)


def test_scanned_page_mask_refused_without_ocr(tmp_path, no_ocr):
    src = _scanned_pdf(tmp_path / "taranmis.pdf")
    target = tmp_path / "taranmis_maskeli.pdf"
    with pytest.raises(OcrUnavailable) as e:
        mask_pdf(src, target, Rules.default())
    assert "OCR kullanılamıyor" in str(e.value) and "Sayfa 2" in str(e.value) and "dosya yazılmadı" in str(e.value)
    assert not target.exists() and not list(tmp_path.glob("*.tmp"))


def test_scan_continues_with_warning_without_ocr(tmp_path, no_ocr):
    result = scan_pdf(_scanned_pdf(tmp_path / "taranmis.pdf"), Rules.default())
    assert result.no_ocr_pages == [2]
    assert any("OCR dil dosyaları kurulu değil" in w and "maskeli kopya yazılmaz" in w for w in result.warnings)


def test_excluded_or_dropped_unreadable_page_is_allowed(tmp_path, no_ocr):
    """Kullanıcı sayfayı maskelenmesin dedi ya da kopyadan çıkardıysa sessiz değildir; ret yok."""
    src = _scanned_pdf(tmp_path / "taranmis.pdf")
    mask_pdf(src, tmp_path / "a.pdf", Rules.default(), drop_pages=[2])
    mask_pdf(src, tmp_path / "b.pdf", Rules.default(), exclude_pages="2")


def test_image_mask_refused_without_ocr(tmp_path, no_ocr):
    src = tmp_path / "foto.png"
    src.write_bytes(_scan_png(f"TC {TC}"))
    with pytest.raises(OcrUnavailable, match="Görselin"):
        mask_pdf(src, tmp_path / "foto_maskeli.png", Rules.default())


def test_masked_read_continues_with_warning_without_ocr(tmp_path, no_ocr):
    """Okuma (ajan read) reddedilmez: kopya diske kalmaz ve okunamayan sayfa çıktıya girmez."""
    r = read_masked(_scanned_pdf(tmp_path / "taranmis.pdf"), Rules.default())
    assert TC not in r.text and "Kapak sayfasi" in r.text
    assert any("OCR dil dosyaları kurulu değil" in w for w in r.warnings)


def test_office_with_image_refused_without_ocr_but_readable(tmp_path, no_ocr):
    src = tmp_path / "ekli.docx"
    d = docx.Document()
    d.add_paragraph("Ekte kimlik fotokopisi")
    d.add_picture(io.BytesIO(_scan_png(f"TC {TC}")))
    d.save(src)
    with pytest.raises(OcrUnavailable, match="1 görselin"):
        office.mask(src, tmp_path / "ekli_maskeli.docx", office.WORD, Rules.default())
    assert not (tmp_path / "ekli_maskeli.docx").exists()
    r = read_masked(src, Rules.default())
    assert "Ekte kimlik fotokopisi" in r.text


@pytest.mark.skipif(not ocr.ocr_available(), reason="OCR dil dosyaları yok")
def test_with_ocr_behaviour_unchanged(tmp_path):
    src = _scanned_pdf(tmp_path / "taranmis.pdf")
    res = mask_pdf(src, tmp_path / "taranmis_maskeli.pdf", Rules.default())
    assert Path(res.target).is_file()
    assert scan_pdf(src, Rules.default()).no_ocr_pages == []
