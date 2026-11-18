"""tools/degerlendirme.py (TAKIP 1.61) ve tools/kacak_kontrol.py ek katmanları (1.57, 1.80). Yalnızca sahte değer."""

import io
import sys
import zipfile
from pathlib import Path

import pymupdf
import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import degerlendirme  # noqa: E402
import kacak_kontrol  # noqa: E402

from bulutbelge_core.ocr import ocr_available  # noqa: E402
from bulutbelge_core.rules import Rules  # noqa: E402

SECRET = "GIZLI-DEGER-4711"


def test_degerlendirme_covers_types_and_reports_without_values():
    results, false_alarms = degerlendirme.evaluate(Rules.from_dict(None))
    assert {"tc_kimlik", "iban", "telefon", "eposta"} <= set(results)
    for key, r in results.items():
        assert r.n > 0
        assert r.recall >= 0.9, key
        assert r.miss_rate == pytest.approx(1 - r.recall)
    assert sum(false_alarms.values()) == 0
    text = degerlendirme.report(results, false_alarms)
    assert "duyarlılık" in text and "kaçırma" in text
    for values in degerlendirme.CORPUS.values():
        for v in values:
            assert degerlendirme._target(v) not in text


def test_degerlendirme_reports_missed_when_type_disabled():
    rules = Rules.from_dict({"types": {"eposta": {"enabled": False}}})
    results, _ = degerlendirme.evaluate(rules)
    assert results["eposta"].recall == 0.0
    assert results["eposta"].missed
    assert all(len(m) <= 3 for m in results["eposta"].missed)


def _base_pdf() -> pymupdf.Document:
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Merhaba")
    return doc


def test_pdf_layers_see_javascript():
    doc = _base_pdf()
    xref = doc.get_new_xref()
    doc.update_object(xref, f"<</S /JavaScript /JS (app.alert('{SECRET}'))>>")
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", f"{xref} 0 R")
    layers = kacak_kontrol._pdf_layers(doc.tobytes(garbage=0, deflate=False))
    assert SECRET.casefold() in kacak_kontrol._norm(layers["javascript"])
    clean = kacak_kontrol._pdf_layers(_base_pdf().tobytes())
    assert clean["javascript"] == ""


def _png() -> bytes:
    img = Image.new("RGB", (40, 40), "white")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def test_pdf_thumbnail_is_extracted():
    doc = _base_pdf()
    page_xref = doc[0].xref
    img_xref = doc.get_new_xref()
    doc.update_object(
        img_xref,
        "<</Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceRGB /BitsPerComponent 8 /Length 192>>",
    )
    doc.update_stream(img_xref, bytes([255]) * 192, new=True)
    doc.xref_set_key(page_xref, "Thumb", f"{img_xref} 0 R")
    assert len(kacak_kontrol._pdf_thumbnails(doc)) == 1
    assert kacak_kontrol._pdf_thumbnails(_base_pdf()) == []


def test_pdf_old_revisions_are_checked(tmp_path):
    doc = _base_pdf()
    doc.set_metadata({"title": SECRET})
    path = tmp_path / "a.pdf"
    doc.save(path)
    doc.close()
    with pymupdf.open(path) as d:  # artımlı kayıtla başlık "temizlenir"; eski sürüm dosyada kalır
        d.set_metadata({"title": "temiz"})
        d.saveIncr()
    data = path.read_bytes()
    assert len(kacak_kontrol._pdf_revisions(data)) == 1
    layers = kacak_kontrol._pdf_layers(data)
    assert SECRET.casefold() in kacak_kontrol._norm(layers["eski-sürüm-1/meta"])
    assert SECRET.casefold() not in kacak_kontrol._norm(layers["meta"])
    assert kacak_kontrol._pdf_revisions(_base_pdf().tobytes()) == []


def test_zip_layers_include_thumbnail_part():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("word/document.xml", "<w:t>x</w:t>")
        z.writestr("docProps/thumbnail.png", _png())
    layers = kacak_kontrol._zip_layers(buf.getvalue())
    assert "docProps/thumbnail.png" in layers
    if not ocr_available():
        assert "docProps/thumbnail.png (OCR)" not in layers


FAKE_TC = "10000000146"


def _dirty_pdf(tmp_path, kind):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"Merhaba TC {FAKE_TC}")
    if kind == "yer_imi":
        doc.set_toc([[1, f"Ek {FAKE_TC}", 1]])
    else:
        w = pymupdf.Widget()
        w.field_type = pymupdf.PDF_WIDGET_TYPE_TEXT
        w.field_name = "a"
        w.field_value = f"TC {FAKE_TC}"
        w.rect = pymupdf.Rect(100, 200, 300, 220)
        page.add_widget(w)
    path = tmp_path / f"{kind}.pdf"
    doc.save(path)
    doc.close()
    return path


@pytest.mark.parametrize("kind", ["yer_imi", "form"])
def test_pdf_mask_clears_bookmark_and_form_field_layers(tmp_path, kind):
    from bulutbelge_core.pdf import mask_pdf

    out = mask_pdf(_dirty_pdf(tmp_path, kind), tmp_path / f"{kind}_m.pdf", Rules.from_dict(None)).target
    layers = kacak_kontrol._pdf_layers(Path(out).read_bytes())
    for name, text in layers.items():
        assert FAKE_TC not in kacak_kontrol._digits(text), name


def test_office_mask_drops_thumbnail_and_its_relationship(tmp_path):
    import docx

    from bulutbelge_core import office

    src = tmp_path / "k.docx"
    d = docx.Document()
    d.add_paragraph(f"TC {FAKE_TC}")
    d.save(src)
    with zipfile.ZipFile(src) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items["docProps/thumbnail.png"] = _png()
    items["_rels/.rels"] = items["_rels/.rels"].replace(
        b"</Relationships>",
        b'<Relationship Id="rIdT" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"'
        b' Target="docProps/thumbnail.png"/></Relationships>',
    )
    with zipfile.ZipFile(src, "w") as z:
        for n, b in items.items():
            z.writestr(n, b)
    out, _, _ = office.mask(src, tmp_path / "k_m.docx", office.format_of(src), Rules.from_dict(None))
    with zipfile.ZipFile(out) as z:
        assert not any(n.startswith("docProps/thumbnail") for n in z.namelist())
        assert b"thumbnail" not in z.read("_rels/.rels")
    assert FAKE_TC not in "".join(kacak_kontrol._digits(t) for t in kacak_kontrol._zip_layers(Path(out).read_bytes()).values())
