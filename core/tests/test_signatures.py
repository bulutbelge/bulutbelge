from pathlib import Path

import pymupdf
import pytest

from bulutbelge_core.pdf import mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules
from bulutbelge_core.signatures import _fold, normalize_tr

from fake_signature import make_signed_pdf


@pytest.fixture
def signed_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "imzali.pdf"
    make_signed_pdf(path)
    return path


def signature_findings(path, rules=None):
    return [f for f in scan_pdf(path, rules or Rules.default(), previews=True).findings if f.finding.type == "imza"]


def test_normalize_turkish_dotted_i():
    assert normalize_tr("İMZA") == "imza"
    assert normalize_tr("IŞIK") == "ışık"
    # Türkçe karakter kullanılmadan yazılmış etiketler de eşleşir.
    assert _fold("Imza") == _fold("İmza") == "imza"
    assert _fold("KASE") == _fold("Kaşe")


def test_finds_image_and_pen_signature_but_not_logo(signed_pdf):
    found = signature_findings(signed_pdf)
    assert sorted(f.kind for f in found) == ["cizim", "gorsel"]
    # Logo (sağ üst, etiketsiz) imza sayılmaz.
    assert all(f.rects[0].y0 > 500 for f in found)
    assert all(f.preview and f.preview.startswith(b"\x89PNG") for f in found)
    assert all(f.finding.confidence == "orta" for f in found)


def test_disabled_type_or_no_labels_finds_nothing(signed_pdf):
    off = Rules.from_dict({"types": {"imza": {"enabled": False, "method": "karartma"}}})
    assert signature_findings(signed_pdf, off) == []
    no_labels = Rules.from_dict({"signature_labels": []})
    assert signature_findings(signed_pdf, no_labels) == []


def test_mask_removes_signature_image_and_strokes(signed_pdf, tmp_path):
    before = pymupdf.open(signed_pdf)
    images_before = len(before[0].get_image_info())
    before.close()

    result = mask_pdf(signed_pdf, tmp_path / "cikti.pdf", Rules.default())
    out = pymupdf.open(result.target)
    try:
        page = out[0]
        # Logo kalır, imza görseli gider.
        boxes = [pymupdf.Rect(i["bbox"]) for i in page.get_image_info()]
        assert len(boxes) < images_before
        assert any(b.y1 < 100 for b in boxes)
        # İmza bölgesinde kalem çizgisi kalmaz.
        assert not [d for d in page.get_drawings() if pymupdf.Rect(d["rect"]).y0 > 600 and len(d["items"]) > 3]
        # Etiketler yerinde durur.
        assert "Imza:" in page.get_text() and "Onaylayan" in page.get_text()
    finally:
        out.close()


def test_excluded_signature_stays(signed_pdf, tmp_path):
    rules = Rules.default()
    img = next(f for f in signature_findings(signed_pdf) if f.kind == "gorsel")
    result = mask_pdf(signed_pdf, tmp_path / "cikti.pdf", rules, excluded_ids={img.id})
    out = pymupdf.open(result.target)
    try:
        assert any(pymupdf.Rect(i["bbox"]).y0 > 600 for i in out[0].get_image_info())
    finally:
        out.close()


def test_ink_remaining_detects_unmasked_signature(signed_pdf, tmp_path):
    from bulutbelge_core.signatures import ink_remaining, ink_snapshot

    doc = pymupdf.open(signed_pdf)
    rect = next(f for f in signature_findings(signed_pdf) if f.kind == "gorsel").rects[0]
    before = ink_snapshot(doc[0], rect)
    # Aynı sayfa maskelenmediyse imza tamamen duruyor.
    assert ink_remaining(before, ink_snapshot(doc[0], rect)) > 0.9
    doc.close()
    # Maskelenen çıktıda iz kalmaz; karartma kutusu mürekkep sayılmaz.
    result = mask_pdf(signed_pdf, tmp_path / "cikti.pdf", Rules.default())
    out = pymupdf.open(result.target)
    assert ink_remaining(before, ink_snapshot(out[0], rect)) < 0.2
    out.close()
    assert not [w for w in result.warnings if "imza izleri" in w]


def test_leftover_warning_when_signature_not_removed(signed_pdf, tmp_path):
    from bulutbelge_core.pdf import _signature_leftover_warnings
    from bulutbelge_core.signatures import ink_snapshot

    doc = pymupdf.open(signed_pdf)
    before = [(f, ink_snapshot(doc[0], f.rects[0])) for f in signature_findings(signed_pdf)]
    doc.close()
    # Girdinin kendisi "çıktı" sayılırsa imza duruyordur: uyarı çıkar.
    assert any("imza izleri" in w for w in _signature_leftover_warnings(str(signed_pdf), before))
    # Gerçek maskeli çıktıda uyarı çıkmaz.
    out = mask_pdf(signed_pdf, tmp_path / "cikti.pdf", Rules.default())
    assert _signature_leftover_warnings(out.target, before) == []


# --- Etiketsiz imza ve kaşe (TAKIP 1.11) ---


def _etiketsiz_pdf(tmp_path, logo_alta=False, cizgisiz=False):
    from fake_signature import draw_pen_signature, logo_png, squiggle_png

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Sözleşme (sahte veri)", fontsize=12)
    # Etiket yok: bölüm başlıkları imza etiketi değil.
    page.insert_text((72, 560), "Taraflar yukarıdaki şartları kabul eder.", fontsize=11)
    if not cizgisiz:
        page.insert_image(pymupdf.Rect(72, 620, 232, 670), stream=squiggle_png())
        draw_pen_signature(page, 330, 625)
        draw_pen_signature(page, 420, 625)  # 10 eğri: etiketsiz eşik (6) aşılır
    if logo_alta:
        page.insert_image(pymupdf.Rect(400, 700, 440, 740), stream=logo_png())
    path = tmp_path / "etiketsiz.pdf"
    doc.save(path)
    doc.close()
    return path


def test_unlabeled_signature_found_without_label(tmp_path):
    found = signature_findings(_etiketsiz_pdf(tmp_path))
    assert sorted(f.kind for f in found) == ["cizim", "gorsel"]
    assert all(f.rects[0].y0 > 600 for f in found)


def test_unlabeled_solid_logo_and_top_images_are_not_signatures(tmp_path):
    # Düz dolgulu logo sayfa altında bile imza sayılmaz; üstteki sezgi dışı.
    assert signature_findings(_etiketsiz_pdf(tmp_path, logo_alta=True, cizgisiz=True)) == []


def test_unlabeled_drawing_over_text_is_ignored(tmp_path):
    from fake_signature import draw_pen_signature

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 650), "Uzun bir paragraf satırı sahte metin " * 2, fontsize=11)
    draw_pen_signature(page, 72, 635)  # yazının üzerinde: imza değil
    path = tmp_path / "yazi.pdf"
    doc.save(path)
    doc.close()
    assert signature_findings(path) == []


def test_unlabeled_signature_masked(tmp_path):
    path = _etiketsiz_pdf(tmp_path)
    result = mask_pdf(path, tmp_path / "cikti.pdf", Rules.default())
    out = pymupdf.open(result.target)
    try:
        assert not [i for i in out[0].get_image_info() if pymupdf.Rect(i["bbox"]).y0 > 600]
        assert not [d for d in out[0].get_drawings() if pymupdf.Rect(d["rect"]).y0 > 600 and len(d["items"]) > 3]
    finally:
        out.close()


def test_scanned_colored_stamp_found_but_black_ink_and_mostly_color_ignored():
    from bulutbelge_core.signatures import find_scanned_stamps

    def sayfa(renk, kaplama=None):
        doc = pymupdf.open()
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 595, 842), False)
        pix.set_rect(pix.irect, (255, 255, 255))
        sh = pymupdf.Document()
        pg = sh.new_page(width=595, height=842)
        pg.draw_circle((300, 650), 40, color=renk, width=3)
        pg.draw_circle((300, 650), 25, color=renk, width=2)
        if kaplama:
            pg.draw_rect(pg.rect, fill=kaplama)
        png = pg.get_pixmap(dpi=72).tobytes("png")
        page.insert_image(page.rect, stream=png)
        return doc, page

    doc, page = sayfa((0.7, 0.1, 0.1))
    bulunan = find_scanned_stamps(page, [], [])
    assert len(bulunan) == 1 and bulunan[0].rect.y0 > 580
    doc, page = sayfa((0, 0, 0))
    assert find_scanned_stamps(page, [], []) == []
    # Sayfa büyük ölçüde renkliyse (fotoğraf, renkli belge) aranmaz.
    doc, page = sayfa((0.7, 0.1, 0.1), kaplama=(0.2, 0.6, 0.2))
    assert find_scanned_stamps(page, [], []) == []
