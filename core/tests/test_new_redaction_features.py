"""Yeni eklenen belge, görsel, sayfa aralığı, Excel ve muafiyet kodu özelliklerinin testleri."""

from pathlib import Path

import cv2
import numpy as np
import openpyxl
import pymupdf
import pytest
from openpyxl.comments import Comment
from PIL import Image

from bulutbelge_core import office
from bulutbelge_core.ocr import ocr_available
from bulutbelge_core.pdf import mask_pdf, parse_page_spec, scan_pdf
from bulutbelge_core.rules import Rules

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()


def _make_7page_pdf(path: Path) -> None:
    doc = pymupdf.open()
    for i in range(1, 8):
        p = doc.new_page()
        p.insert_text((72, 72), f"Sayfa {i} baslik\nTC: {TC}", fontsize=12)
    doc.set_toc([[1, f"Bolum 1 - {TC}", 1], [1, "Bolum 4", 4]])
    doc.save(path)
    doc.close()


def test_parse_page_spec_and_validation():
    assert parse_page_spec("4-6", 7) == [4, 5, 6]
    assert parse_page_spec("1, 4-5, 7", 7) == [1, 4, 5, 7]
    assert parse_page_spec(None, 7) == []
    with pytest.raises(Exception):
        parse_page_spec("6-4", 7)
    with pytest.raises(Exception):
        parse_page_spec("8", 7)


def test_pdf_mask_only_page_range_preserves_other_pages_and_strips_bookmarks(tmp_path):
    src = tmp_path / "yedi.pdf"
    _make_7page_pdf(src)
    rules = Rules.default()

    result = mask_pdf(src, tmp_path / "out_4_6.pdf", rules, mask_pages="4-6")
    out = pymupdf.open(result.target)
    try:
        assert out.page_count == 7
        assert out.get_toc() == []  # yer işaretleri temizlendi
        for pno in (1, 2, 3, 7):
            assert TC in out[pno - 1].get_text()
        for pno in (4, 5, 6):
            assert TC not in out[pno - 1].get_text()
    finally:
        out.close()


def test_pdf_exclude_pages_and_flatten(tmp_path):
    src = tmp_path / "yedi.pdf"
    _make_7page_pdf(src)
    rules = Rules.default()

    # 1 ve 7 korunur; 2-6 maskelenir; tüm sayfalar düzleştirilir
    result = mask_pdf(src, tmp_path / "out_flat.pdf", rules, exclude_pages="1, 7", flatten=True)
    assert result.flattened == 7
    out = pymupdf.open(result.target)
    try:
        assert out.page_count == 7
        # Düzleştirilmiş PDF'te metin katmanı tamamen kalkar
        assert all(not page.get_text().strip() for page in out)
        assert all(len(page.get_images()) == 1 for page in out)
    finally:
        out.close()


def test_exemption_codes_and_manual_reason_overlay(tmp_path):
    src = tmp_path / "muafiyet.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"TC: {TC}\nOzel satir: Gizli ihale bedeli", fontsize=11)
    doc.save(src)
    doc.close()

    rules = Rules.from_dict(
        {
            "types": {"tc_kimlik": {"enabled": True, "method": "etiket"}},
            "reasons": {"tc_kimlik": "KVKK Md.28"},
        }
    )
    res = mask_pdf(
        src,
        tmp_path / "out.pdf",
        rules,
        manual_areas=[(1, (65, 80, 260, 102), "Ticari Sir")],
    )
    out = pymupdf.open(res.target)
    try:
        text = out[0].get_text()
        assert TC not in text
        assert "[KVKK Md.28]" in text
        assert "[Ticari Sir]" in text
    finally:
        out.close()


def test_multipage_tiff_supported(tmp_path):
    src = tmp_path / "tarama.tiff"
    f1 = Image.new("RGB", (300, 180), "white")
    f2 = Image.new("RGB", (300, 180), "white")
    f1.save(src, "TIFF", save_all=True, append_images=[f2])

    scan = scan_pdf(src, Rules.default())
    assert scan.pages == 2
    res = mask_pdf(src, tmp_path / "out.tiff", Rules.default(), manual_areas=[(2, (10, 10, 120, 60))])
    out = Image.open(res.target)
    assert getattr(out, "n_frames", 1) == 2
    out.seek(1)
    assert out.getpixel((40, 30))[0] < 30  # 2. sayfa alanı karartıldı


def test_visual_blue_stamp_and_qr_detection_and_redaction(tmp_path):
    # Mavi kaşe + QR kod (sentetik finder kareleri olmasa bile OpenCV ile üretilebilen gerçek desen yoksa kaşe test edilir)
    img = np.full((320, 480, 3), 255, dtype=np.uint8)
    # Sol üstte mavi renkli sahte kaşe dikdörtgeni/ovalı (BGR: mavi yüksek)
    cv2.rectangle(img, (40, 40), (190, 120), (190, 55, 20), 3)
    cv2.ellipse(img, (115, 80), (50, 25), 0, 0, 360, (190, 55, 20), 2)
    cv2.putText(img, "KASE", (75, 86), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (190, 55, 20), 2)

    src = tmp_path / "kase.png"
    cv2.imwrite(str(src), img)

    scan = scan_pdf(src, Rules.default())
    stamps = [f for f in scan.findings if f.finding.type == "imza"]
    assert stamps, "Mavi kaşe görsel olarak tespit edilmeli"
    res = mask_pdf(src, tmp_path / "kase_out.png", Rules.default())
    assert res.masked >= 1
    out = cv2.imread(res.target)
    # Kaşe merkezi karartılmış/silinmiş olmalı
    assert int(out[80, 115, 0]) < 40


def test_qr_code_detector_with_minimal_valid_qr(tmp_path):
    # Sabit 7x7 finder deseni + veri dolgu alanı + ayrı 1D barkod şeridiyle test.
    m = np.full((21, 21), 255, dtype=np.uint8)

    def finder(r0, c0):
        m[r0 : r0 + 7, c0 : c0 + 7] = 0
        m[r0 + 1 : r0 + 6, c0 + 1 : c0 + 6] = 255
        m[r0 + 2 : r0 + 5, c0 + 2 : c0 + 5] = 0

    finder(0, 0)
    finder(0, 14)
    finder(14, 0)
    for k in range(8, 13):
        val = 0 if k % 2 == 0 else 255
        m[6, k] = val
        m[k, 6] = val
    rng = np.random.default_rng(7)
    m[9:20, 9:20] = (rng.integers(0, 2, (11, 11), dtype=np.uint8) * 255)
    m[13, 8] = 0

    big = np.full((310, 310, 3), 255, dtype=np.uint8)
    scaled = cv2.resize(m, (210, 210), interpolation=cv2.INTER_NEAREST)
    big[50:260, 50:260] = cv2.cvtColor(scaled, cv2.COLOR_GRAY2BGR)
    src = tmp_path / "qr.png"
    cv2.imwrite(str(src), big)

    scan = scan_pdf(src, Rules.default())
    qrs = [f for f in scan.findings if f.finding.type == "barkod_qr"]
    assert qrs, "QR kodu tespit edilmeli"
    res = mask_pdf(src, tmp_path / "qr_out.png", Rules.default())
    assert res.masked >= 1
    assert not [f for f in scan_pdf(res.target, Rules.default()).findings if f.finding.type == "barkod_qr"]

    # 1D Barkod testi
    bar = np.full((160, 360, 3), 255, dtype=np.uint8)
    for i in range(65):
        if (i * 7 + 3) % 5 < 3:
            cv2.rectangle(bar, (40 + i * 4, 40), (42 + i * 4, 110), (0, 0, 0), -1)
    bar_src = tmp_path / "barkod.png"
    cv2.imwrite(str(bar_src), bar)
    bar_scan = scan_pdf(bar_src, Rules.default())
    assert any(f.finding.type == "barkod_qr" for f in bar_scan.findings), "1D barkod tespit edilmeli"
    bar_res = mask_pdf(bar_src, tmp_path / "barkod_out.png", Rules.default())
    assert not [f for f in scan_pdf(bar_res.target, Rules.default()).findings if f.finding.type == "barkod_qr"]


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_hybrid_pdf_digital_header_and_scanned_body(tmp_path):
    # Dijital üstbilgi (vektör metin) + taranmış gövde (görsel) içeren karma PDF:
    img_doc = pymupdf.open()
    ip = img_doc.new_page(width=450, height=120)
    ip.insert_text((20, 60), f"TC kimlik no: {TC}", fontsize=18)
    png = tmp_path / "govde.png"
    img_doc[0].get_pixmap(dpi=150).save(png)
    img_doc.close()

    pdf = tmp_path / "karma.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 40), "Sayfa 1 - Bates 0001", fontsize=11)  # dijital metin katmanı dolu!
    page.insert_image(pymupdf.Rect(50, 120, 500, 320), filename=str(png))
    doc.save(pdf)
    doc.close()

    scan = scan_pdf(pdf, Rules.default())
    assert 1 in scan.ocr_pages
    assert any(f.finding.type == "tc_kimlik" for f in scan.findings)
    res = mask_pdf(pdf, tmp_path / "karma_out.pdf", Rules.default())
    again = scan_pdf(res.target, Rules.default())
    assert not any(f.finding.type == "tc_kimlik" for f in again.findings)


def test_excel_unhide_flatten_formulas_and_strip_comments(tmp_path):
    src = tmp_path / "gizli.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Ana"
    ws["A1"] = 10
    ws["A2"] = 20
    ws["A3"] = "=SUM(A1:A2)"
    ws["A1"].comment = Comment("Dahili gizli not", "Yazar Ad")
    ws_hidden = wb.create_sheet("GizliSayfa")
    ws_hidden.sheet_state = "veryHidden"
    ws_hidden.append(["IBAN", IBAN])
    wb.save(src)

    rules = Rules.default()
    scan = office.scan(src, office.EXCEL, rules)
    assert any("gizli" in w.lower() for w in scan.warnings)
    assert any(f.finding.type == "iban" for f in scan.findings)
    preview = office.sheet_preview(src)
    assert any(s["name"] == "GizliSayfa" and s["hidden"] for s in preview)

    target, _masked, _ = office.mask(
        src,
        tmp_path / "out.xlsx",
        office.EXCEL,
        rules,
        options={"unhide_sheets": True, "flatten_formulas": True, "strip_comments": True},
    )
    out_wb = openpyxl.load_workbook(target, data_only=False)
    assert out_wb["GizliSayfa"].sheet_state == "visible"
    assert not str(out_wb["Ana"]["A3"].value or "").startswith("=")
    assert (out_wb["Ana"]["A1"].comment is None) or (out_wb["Ana"]["A1"].comment.text == "")
    everything = office.all_text(Path(target).read_bytes())
    assert IBAN not in everything
