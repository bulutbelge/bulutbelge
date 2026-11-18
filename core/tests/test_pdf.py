import re
from pathlib import Path

import pymupdf
import pytest

from bulutbelge_core.ocr import ocr_available
from bulutbelge_core.pdf import PdfError, default_target, mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

from fake_data import fake_card, fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()
CARD = fake_card()


@pytest.fixture
def sample_pdf(tmp_path: Path) -> Path:
    path = tmp_path / "ornek.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    lines = [
        "Musteri bilgileri (sahte veri)",
        f"TC kimlik: {TC}",
        f"IBAN: {IBAN}",
        f"Kart: {CARD}",
        "E-posta: ayse.yilmaz@ornek.com.tr",
        "Proje: Mavi Kartal",
    ]
    for i, line in enumerate(lines):
        page.insert_text((72, 72 + i * 20), line, fontsize=11)
    page.add_text_annot((300, 72), f"Yorum: {TC}")
    doc.set_metadata({"author": "Ayse Yilmaz", "title": "Gizli"})
    doc.save(path)
    doc.close()
    return path


def full_text(path: Path) -> str:
    doc = pymupdf.open(path)
    try:
        return "".join(page.get_text() for page in doc)
    finally:
        doc.close()


def test_scan_finds_and_locates(sample_pdf):
    rules = Rules.from_dict({"terms": ["Mavi Kartal"]})
    result = scan_pdf(sample_pdf, rules)
    found = {f.finding.type for f in result.findings}
    assert found == {"tc_kimlik", "iban", "kredi_karti", "eposta", "ozel_ifade"}
    assert all(f.locatable for f in result.findings)
    assert result.pages == 1


def test_mask_really_removes_text_and_metadata(sample_pdf, tmp_path):
    rules = Rules.from_dict({"terms": ["Mavi Kartal"]})
    result = mask_pdf(sample_pdf, tmp_path / "cikti.pdf", rules)
    out = Path(result.target)
    text = full_text(out)

    assert TC not in text
    assert IBAN not in text
    assert CARD not in text
    assert "ayse.yilmaz" not in text
    assert "Mavi Kartal" not in text
    # Son 4 hane açık yöntemi ve etiket yazılmış olmalı.
    assert "**** " + IBAN.replace(" ", "")[-4:] in text
    assert "[E-POSTA]" in text
    # Maskelenmeyen metin yerinde kalır.
    assert "Musteri bilgileri" in text

    doc = pymupdf.open(out)
    try:
        assert not any(doc.metadata.get(k) for k in ("author", "title"))
        assert not list(doc[0].annots())
    finally:
        doc.close()
    # Orijinal dosyaya dokunulmaz.
    assert TC in full_text(sample_pdf)


def test_excluded_finding_stays(sample_pdf, tmp_path):
    rules = Rules.default()
    scan = scan_pdf(sample_pdf, rules)
    email = next(f for f in scan.findings if f.finding.type == "eposta")
    result = mask_pdf(sample_pdf, tmp_path / "cikti.pdf", rules, excluded_ids={email.id})
    text = full_text(Path(result.target))
    assert "ayse.yilmaz@ornek.com.tr" in text
    assert TC not in text


def test_target_never_overwrites_or_equals_source(sample_pdf, tmp_path):
    rules = Rules.default()
    with pytest.raises(PdfError):
        mask_pdf(sample_pdf, sample_pdf, rules)

    existing = tmp_path / "var.pdf"
    existing.write_bytes(b"dokunma")
    result = mask_pdf(sample_pdf, existing, rules)
    assert result.target != str(existing.resolve())
    assert existing.read_bytes() == b"dokunma"


def test_default_target_suffix(sample_pdf):
    assert default_target(sample_pdf).endswith("ornek_maskeli.pdf")


def test_nbsp_and_soft_hyphen_still_match(tmp_path):
    path = tmp_path / "nbsp.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "IBAN: " + IBAN.replace(" ", " "), fontsize=11)
    page.insert_text((72, 100), "Kod: PRJ­0042", fontsize=11)
    doc.save(path)
    doc.close()

    rules = Rules.from_dict({"patterns": [{"name": "Proje kodu", "pattern": r"PRJ-\d{4}"}]})
    found = {f.finding.type for f in scan_pdf(path, rules).findings}
    assert found == {"iban", "ozel_kalip"}


def test_not_a_pdf(tmp_path):
    bad = tmp_path / "x.pdf"
    bad.write_text("pdf değil")
    with pytest.raises(PdfError):
        scan_pdf(bad, Rules.default())


def test_blur_deletes_text_and_inserts_information_free_fill(sample_pdf, tmp_path):
    rules = Rules.from_dict({"types": {"tc_kimlik": {"enabled": True, "method": "bulanik"}}})
    result = mask_pdf(sample_pdf, tmp_path / "cikti.pdf", rules)
    out = pymupdf.open(result.target)
    try:
        assert TC not in out[0].get_text()
        tc_line = next(r for r in out[0].search_for("TC kimlik:"))
        # Değerin yerinde (aynı satırda, sağda) eklenmiş bir görsel var.
        fills = [pymupdf.Rect(i["bbox"]) for i in out[0].get_image_info()]
        assert any(abs(b.y0 - tc_line.y0) < 6 and b.x0 >= tc_line.x1 - 1 for b in fills)
    finally:
        out.close()


def test_blur_fill_is_random_not_derived_from_content():
    from bulutbelge_core.blur import blur_png

    a, b = blur_png(120, 12), blur_png(120, 12)
    assert a.startswith(b"\x89PNG") and a != b


def test_manual_area_removes_everything_inside(sample_pdf, tmp_path):
    rules = Rules.from_dict({"types": {k: {"enabled": False, "method": "karartma"} for k in
                                       ("tc_kimlik", "iban", "kredi_karti", "eposta", "imza")}})
    # "Musteri bilgileri" satırını (y≈72) elle seç.
    result = mask_pdf(sample_pdf, tmp_path / "cikti.pdf", rules, manual_areas=[(1, (60, 58, 300, 78))])
    text = full_text(Path(result.target))
    assert "Musteri bilgileri" not in text
    assert TC in text  # tür kapalı, elle alan dışında
    assert result.masked == 1


def test_manual_area_rejects_bad_page(sample_pdf, tmp_path):
    with pytest.raises(PdfError):
        mask_pdf(sample_pdf, tmp_path / "c.pdf", Rules.default(), manual_areas=[(5, (0, 0, 10, 10))])


def test_make_dirs_creates_target_folder(sample_pdf, tmp_path):
    result = mask_pdf(sample_pdf, tmp_path / "alt" / "klasor" / "c.pdf", Rules.default(), make_dirs=True)
    assert Path(result.target).is_file()


def test_stroke_signature_with_page_transform_is_removed(tmp_path):
    """Shape ile çizilen (koordinat dönüşümlü) imza da silinmeli; kaçak denetimi durdurmamalı."""
    import math

    from bulutbelge_core.signatures import is_stroke_drawing

    src = tmp_path / "imzali.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((60, 400), "Kiraci Imza:", fontsize=11)
    shape = page.new_shape()
    pts = [pymupdf.Point(150 + t * 3, 420 + 12 * math.sin(t / 4)) for t in range(60)]
    for a, b, c, e in zip(pts[0::3], pts[1::3], pts[2::3], pts[3::3]):
        shape.draw_bezier(a, b, c, e)
    shape.finish(color=(0.1, 0.15, 0.5), width=1.4)
    shape.commit()
    # İmzaya değmeyen tablo çizgisi korunmalı.
    page.draw_line((40, 500), (560, 500))
    doc.save(src)
    doc.close()

    rules = Rules.from_dict(None)
    assert [f.kind for f in scan_pdf(src, rules).findings] == ["cizim"]
    out = pymupdf.open(mask_pdf(src, tmp_path / "out.pdf", rules).target)
    try:
        drawings = out[0].get_drawings()
    finally:
        out.close()
    assert not [d for d in drawings if is_stroke_drawing(d)]  # imza gitti (yerinde yalnızca siyah kutu)
    rects = [pymupdf.Rect(d["rect"]) for d in drawings]
    assert any(abs(r.y0 - 500) < 1 and r.width > 500 for r in rects)  # tablo çizgisi kaldı


def test_replacement_text_matches_surrounding_size_and_baseline(tmp_path):
    src = tmp_path / "boyut.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    sizes = (9, 12, 16)
    for i, fs in enumerate(sizes):
        page.insert_text((72, 100 + i * 40), f"Sayin ali.veli{i}@ornek.test iletisim", fontsize=fs)
    doc.save(src)
    doc.close()
    out = pymupdf.open(mask_pdf(src, tmp_path / "cikti.pdf", Rules.default()).target)
    spans = [
        s
        for b in out[0].get_text("dict")["blocks"]
        for ln in b["lines"]
        for s in ln["spans"]
        if "[E-POSTA]" in s["text"]
    ]
    assert len(spans) == len(sizes)
    for span, fs, i in zip(sorted(spans, key=lambda s: s["origin"][1]), sizes, range(3)):
        assert span["size"] == pytest.approx(fs, abs=0.1)
        assert span["origin"][1] == pytest.approx(100 + i * 40, abs=0.1)


def test_watermark_optional(sample_pdf, tmp_path):
    plain = mask_pdf(sample_pdf, tmp_path / "duz.pdf", Rules.from_dict({}))
    assert "MASKEL" not in full_text(Path(plain.target))
    marked = mask_pdf(sample_pdf, tmp_path / "filigranli.pdf", Rules.from_dict({}), watermark=True)
    text = full_text(Path(marked.target)).replace("\n", "")
    assert "MASKELI KOPYA" in text  # İ noktası ayrıca çizilir
    assert TC not in text and IBAN not in text  # filigran maskelemeyi bozmaz


def _black_width(path: Path, x0: float) -> int:
    doc = pymupdf.open(path)
    try:
        pix = doc[0].get_pixmap(dpi=72)
        row = 88  # TC satırının ortası
        xs = [x for x in range(int(x0), pix.width) if sum(pix.pixel(x, row)[:3]) < 30]
        return (max(xs) - min(xs) + 1) if xs else 0
    finally:
        doc.close()


def test_fixed_box_width_does_not_depend_on_value_length(tmp_path):
    widths = []
    for i, value in enumerate([TC, TC + "9"]):
        path = tmp_path / f"s{i}.pdf"
        doc = pymupdf.open()
        doc.new_page().insert_text((72, 92), f"TC kimlik: {value}", fontsize=11)
        doc.save(path)
        doc.close()
        out = mask_pdf(path, tmp_path / f"c{i}.pdf", Rules.from_dict({"terms": [value]}), fixed_box=True)
        assert value not in full_text(Path(out.target))
        widths.append(_black_width(Path(out.target), 100))
    assert widths[0] > 0 and widths[0] == widths[1]


def test_gap_width_warning_only_for_variable_length_without_fixed_box(tmp_path):
    path = tmp_path / "g.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 92), "Proje: Mavi Kartal devam", fontsize=11)
    doc.save(path)
    doc.close()
    rules = Rules.from_dict({"terms": ["Mavi Kartal"]})
    plain = mask_pdf(path, tmp_path / "a.pdf", rules)
    assert any("uzunluğunu" in w for w in plain.warnings)
    fixed = mask_pdf(path, tmp_path / "b.pdf", rules, fixed_box=True)
    assert not any("uzunluğunu" in w for w in fixed.warnings)


def test_gap_check_catches_glyph_left_inside_box(tmp_path):
    from bulutbelge_core.pdf import _verify_glyph_gaps

    path = tmp_path / "k.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 92), "kalan", fontsize=11)
    doc.save(path)
    doc.close()
    box = [(0, pymupdf.Rect(60, 80, 200, 100))]
    with pytest.raises(PdfError, match="glif"):
        _verify_glyph_gaps(str(path), box, {"kalan"})
    assert _verify_glyph_gaps(str(path), box, {"baska"})  # komşu metin: uyarı
    assert _verify_glyph_gaps(str(path), [(0, pymupdf.Rect(300, 80, 400, 100))], {"kalan"}) == []


def test_char_by_char_value_leaves_no_glyph_in_mask(tmp_path):
    path = tmp_path / "h.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    x = 160
    for ch in TC:
        page.insert_text((x, 92), ch, fontsize=11)
        x += 7.3
    doc.save(path)
    doc.close()
    out = mask_pdf(path, tmp_path / "c.pdf", Rules.from_dict({"terms": [TC]}))
    assert TC not in full_text(Path(out.target))


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_flatten_rasterizes_pages_and_masks_via_ocr(tmp_path):
    path = tmp_path / "duz.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 92), f"TC kimlik no: {TC}", fontsize=14)
    page.insert_text((72, 130), "Proje: Mavi Kartal", fontsize=14)
    page.insert_text((72, 160), "Gizli not: sahte-gizli-metin", fontsize=1, color=(1, 1, 1))
    doc.set_metadata({"author": "Ayse Yilmaz"})
    doc.save(path)
    doc.close()

    scan = scan_pdf(path, Rules.from_dict(None), flatten=True)
    assert scan.ocr_pages == [1]
    assert "tc_kimlik" in {f.finding.type for f in scan.findings}
    assert any("Düzleştirme" in w for w in scan.warnings)

    out = mask_pdf(path, tmp_path / "duz_maskeli.pdf", Rules.from_dict(None), flatten=True)
    assert out.masked >= 1
    res = pymupdf.open(out.target)
    try:
        assert res[0].get_text("text").strip() == ""  # metin katmanı yok, yalnızca görüntü
        assert res[0].get_images()
        assert res.page_count == 1
        assert not res.metadata.get("author")
    finally:
        res.close()
    assert not any(f.finding.type == "tc_kimlik" for f in scan_pdf(out.target, Rules.from_dict(None)).findings)


def test_flatten_without_ocr_refuses(tmp_path, monkeypatch):
    monkeypatch.delenv("BULUTBELGE_TESSDATA", raising=False)
    path = tmp_path / "duz.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 92), f"TC kimlik: {TC}", fontsize=11)
    doc.save(path)
    doc.close()
    with pytest.raises(PdfError):
        mask_pdf(path, tmp_path / "c.pdf", Rules.from_dict(None), flatten=True)
    assert not (tmp_path / "c.pdf").exists()


def test_bosluk_ve_kutu_genisligi_uyarisi_deger_icermez():
    from bulutbelge_core.pdf import _boslukluk_uyarilari, _bosluk_sizar

    assert _bosluk_sizar(100, 30) and not _bosluk_sizar(100, 80) and not _bosluk_sizar(0, 10)
    assert _boslukluk_uyarilari(0, 0) == []
    u = _boslukluk_uyarilari(2, 3)
    assert len(u) == 2 and "2 yerde" in u[0] and "3 karartma" in u[1]


def test_password_copy_is_aes256_and_masked(sample_pdf, tmp_path):
    result = mask_pdf(sample_pdf, tmp_path / "parolali.pdf", Rules.from_dict({}), password="sahte-parola-123")
    out = Path(result.target)
    assert result.encrypted

    doc = pymupdf.open(out)
    try:
        assert doc.needs_pass
        assert not doc.authenticate("yanlis-parola")
        assert doc.authenticate("sahte-parola-123")
        assert doc.metadata["encryption"].startswith("Standard V5 R6")
        text = "".join(p.get_text() for p in doc)
    finally:
        doc.close()
    assert TC not in text
    assert IBAN not in text
    # Orijinal kaynak şifrelenmez.
    assert not pymupdf.open(sample_pdf).needs_pass


def test_password_too_short_is_rejected(sample_pdf, tmp_path):
    target = tmp_path / "kisa.pdf"
    with pytest.raises(PdfError):
        mask_pdf(sample_pdf, target, Rules.from_dict({}), password="12345")
    assert not target.exists()


def test_no_password_means_plain_copy(sample_pdf, tmp_path):
    result = mask_pdf(sample_pdf, tmp_path / "acik.pdf", Rules.from_dict({}))
    assert not result.encrypted
    assert not pymupdf.open(result.target).needs_pass


def test_text_right_of_mask_keeps_original_position(tmp_path):
    path = tmp_path / "kay.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 92), "Proje: Mavi Kartal devam eder", fontsize=11)
    doc.save(path)
    doc.close()

    def x_of(p, word):
        d = pymupdf.open(p)
        try:
            return {w[4]: w[0] for w in d[0].get_text("words")}[word]
        finally:
            d.close()

    before = x_of(path, "devam")
    out = mask_pdf(path, tmp_path / "kay_m.pdf", Rules.from_dict({"terms": ["Mavi Kartal"]}))
    assert "Mavi" not in full_text(Path(out.target))
    assert abs(x_of(out.target, "devam") - before) < 1.0
    assert not any("kaydı" in w for w in out.warnings)


def test_iban_wrapped_at_line_end_is_blacked_out(tmp_path):
    raw = IBAN.replace(" ", "")
    src = tmp_path / "bolunmus.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), f"IBAN: {raw[:14]} ", fontsize=11)
    page.insert_text((72, 114), raw[14:], fontsize=11)
    doc.save(src)
    doc.close()
    rules = Rules.from_dict(None)
    scan = scan_pdf(src, rules)
    assert [f.finding.type for f in scan.findings] == ["iban"] and len(scan.findings[0].rects) == 2
    out = mask_pdf(src, tmp_path / "out.pdf", rules)
    text = full_text(Path(out[0] if isinstance(out, tuple) else out.target if hasattr(out, "target") else out))
    assert raw[14:] not in text.replace(" ", "").replace("\n", "") and raw[:14] not in text.replace(" ", "")


def test_open_action_javascript_is_removed(tmp_path):
    """Katalogdaki OpenAction betiği (içinde değer olsa da) çıktıdan silinir (TAKIP 1.57)."""
    tc = fake_tc("376543219")
    src = tmp_path / "betik.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 100), f"TC Kimlik No: {tc}", fontsize=11, fontname="helv")
    doc.save(src)
    doc.close()
    doc = pymupdf.open(src)
    doc.xref_set_key(doc.pdf_catalog(), "OpenAction", f"<< /S /JavaScript /JS (app.alert\('Sahte: {tc}'\);) >>")
    doc.saveIncr()
    doc.close()
    out = mask_pdf(src, tmp_path / "betik_maskeli.pdf", Rules.from_dict(None)).target
    raw = Path(out).read_bytes()
    assert tc.encode() not in raw and b"JavaScript" not in raw


def _kotu_niyetli_pdf(path: Path) -> None:
    """Yalnızca yapı: gerçek zararlı kod yok, eylem sözlükleri sahte komutlar içerir."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), f"TC kimlik: {TC}", fontsize=11)

    def add(obj: str) -> int:
        xref = doc.get_new_xref()
        doc.update_object(xref, obj)
        return xref

    launch = add("<</S/Launch/F(sahte-program.exe)>>")
    link = add(f"<</Type/Annot/Subtype/Link/Rect[0 100 50 150]/A {launch} 0 R>>")
    widget = add(
        "<</Type/Annot/Subtype/Widget/FT/Btn/T(gonder)/Rect[0 160 50 190]/A<</S/SubmitForm/F(http://sahte.invalid)>>"
        "/AA<</E<</S/JavaScript/JS(sahteBetik\\(\\))>>>>>>"
    )
    filespec = add("<</Type/Filespec/F(ek.bin)/EF<</F 1 0 R>>>>")
    attach = add(f"<</Type/Annot/Subtype/FileAttachment/Rect[0 200 20 220]/FS {filespec} 0 R>>")
    doc.xref_set_key(page.xref, "Annots", f"[{link} 0 R {widget} 0 R {attach} 0 R]")
    doc.xref_set_key(page.xref, "AA", "<</O<</S/JavaScript/JS(sahtePageOpen)>>>>")
    cat = doc.pdf_catalog()
    doc.xref_set_key(cat, "OpenAction", "<</S/Launch/F(sahte-acilis.exe)>>")
    doc.xref_set_key(cat, "AA", "<</WC<</S/JavaScript/JS(sahteKapanis)>>>>")
    doc.xref_set_key(cat, "AcroForm", f"<</Fields[{widget} 0 R]/XFA(sahte-xfa)>>")
    doc.xref_set_key(
        cat, "Names", f"<</EmbeddedFiles<</Names[(ek.bin) {filespec} 0 R]>>/JavaScript<</Names[(j)<</S/JavaScript/JS(sahte)>>]>>>>"
    )
    doc.save(path)
    doc.close()


def test_mask_pdf_aktif_icerik_kalmaz(tmp_path):
    src = tmp_path / "kotu.pdf"
    _kotu_niyetli_pdf(src)
    out = Path(mask_pdf(src, tmp_path / "cikti.pdf", Rules.from_dict({})).target)
    raw = out.read_bytes()
    doc = pymupdf.open(out)
    nesneler = "".join(doc.xref_object(x, compressed=True) for x in range(1, doc.xref_length()))
    doc.close()
    nesneler = re.sub(r"/\w+(/\w+)* null", "", nesneler)  # boşaltılmış anahtarlar zararsız
    for iz in ("Launch", "SubmitForm", "JavaScript", "/JS", "/AA", "OpenAction", "XFA", "EmbeddedFile", "/EF", "Filespec"):
        assert iz not in nesneler, iz
    for iz in (b"sahte-program", b"sahte-acilis", b"sahteBetik", b"sahtePageOpen", b"sahteKapanis", b"sahte-xfa"):
        assert iz not in raw, iz
    assert TC not in full_text(out)
