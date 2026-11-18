"""Belirsiz bulgular, öğrenilen istisnalar, yapıştırılan metin ve sayfa çıkarma (sahte veri)."""

from pathlib import Path

import pymupdf
import pytest

from bulutbelge_core.allowlist import AllowMatcher, normalize, value_hash
from bulutbelge_core.detect import HIGH, LOW, MEDIUM, detect
from bulutbelge_core.paste import clean_text, scan_paste
from bulutbelge_core.pdf import PdfError, mask_pdf
from bulutbelge_core.rules import Rules

from fake_data import fake_tc

TC = fake_tc()
BAD_TC = TC[:-1] + str((int(TC[-1]) + 1) % 10)


def test_tc_with_wrong_check_digit_is_uncertain():
    found = detect(f"Kimlik {TC}, {BAD_TC}", Rules.default())
    by_value = {f.value: f for f in found if f.type == "tc_kimlik"}
    assert by_value[TC].confidence == HIGH
    assert by_value[BAD_TC].confidence == LOW
    assert by_value[BAD_TC].source == "kontrol hanesi tutmuyor"


def test_grouped_card_without_luhn_is_uncertain():
    found = detect("Numara 1234 5678 9012 3456", Rules.default())
    assert [(f.type, f.confidence, f.source) for f in found] == [
        ("kredi_karti", LOW, "“Numara” etiketli; kart numarasına benziyor")
    ]


# --- Etiket okuma -----------------------------------------------------------


def test_label_reads_last_words_before_value():
    from bulutbelge_core.labels import REFERENCE, label_before, label_kind

    text = f"Önceki Kayıt / Referans No: {BAD_TC}"
    assert label_before(text, text.index(BAD_TC)) == "Önceki Kayıt / Referans No"
    assert label_kind("Önceki Kayıt / Referans No") == REFERENCE
    assert label_kind("T.C. Kimlik No") == "tc_kimlik"
    assert label_kind("Vergi Kimlik No (VKN)") == "vkn"
    assert label_kind("Kimlik Kartı Seri No") == "tc_kimlik"
    assert label_kind("Kredi Kartı") == "kredi_karti"
    assert label_kind("Numara") is None
    # Parantez ve virgül önceki parçayı keser.
    text = f"Uzman: Ali (Tel: {BAD_TC}"
    assert label_before(text, text.index(BAD_TC)) == "Tel"
    # Form düzeni: etiket önceki satırda.
    text = f"TC Kimlik No:\n{BAD_TC}"
    assert label_before(text, text.index(BAD_TC)) == "TC Kimlik No"


def test_reference_label_is_not_a_tc_candidate():
    found = detect(f"Önceki Kayıt / Referans No: {BAD_TC}\nFatura No: 1234 5678 9012 3456", Rules.default())
    assert [f for f in found if f.type in ("tc_kimlik", "kredi_karti")] == []


def test_matching_label_hides_mistyped_value():
    found = detect(f"TC Kimlik No: {BAD_TC}\nIBAN: TR00 0006 1005 1978 6457 8413 26", Rules.default())
    by_type = {f.type: f for f in found}
    assert by_type["tc_kimlik"].confidence == MEDIUM
    assert by_type["tc_kimlik"].source == "“TC Kimlik No” etiketli; kontrol hanesi tutmuyor, yazım hatası olabilir"
    assert by_type["iban"].confidence == MEDIUM


def test_tc_label_with_wrong_length():
    found = detect(f"T.C. Kimlik No: {TC[:10]}", Rules.default())
    assert [(f.type, f.confidence, f.value) for f in found] == [("tc_kimlik", MEDIUM, TC[:10])]


def test_uncertain_never_overrides_confident_finding():
    # Telefon kesin bulgu; içinde TC'ye benzeyen bir parça olsa bile belirsiz aday eklenmez.
    found = detect("Tel: 0532 123 45 67", Rules.default())
    assert [f.type for f in found] == ["telefon"]


def test_allow_normalizes_phone_spellings():
    assert normalize("0212 555 12 34") == normalize("+90 (212) 555-1234") == "2125551234"
    assert normalize("  Mavi   Kartal ") == "mavi kartal"


def test_allowed_value_is_not_found():
    salt = b"0123456789abcdef"
    rules = Rules.default()
    rules.allow = AllowMatcher({value_hash("0212 555 12 34", salt)}, salt)
    found = detect("Santral: 02125551234, cep: 0532 123 45 67", rules)
    assert [f.value for f in found] == ["0532 123 45 67"]


def test_paste_clean_text_keeps_excluded():
    text = f"Merhaba, TC'm {TC}, e-postam ayse@example.com."
    found = scan_paste(text, Rules.default())
    assert {f.finding.type for f in found} == {"tc_kimlik", "eposta"}
    mail = next(f for f in found if f.finding.type == "eposta")
    out = clean_text(text, found, {mail.id})
    assert TC not in out and "█████" in out and "ayse@example.com" in out


def test_paste_rejects_huge_text():
    with pytest.raises(PdfError):
        scan_paste("a" * 300_000, Rules.default())


def _two_pages(path: Path) -> Path:
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), f"Dilekce sahibi TC: {TC}", fontsize=11)
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Kimlik fotokopisi", fontsize=11)
    p2.insert_text((72, 100), "E-posta: kimlik.sahibi@example.com", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def test_drop_pages_removes_page_and_its_open_values(tmp_path):
    src = _two_pages(tmp_path / "iki.pdf")
    scan_ids = []
    from bulutbelge_core.pdf import scan_pdf

    for f in scan_pdf(src, Rules.default()).findings:
        if f.finding.type == "eposta":
            scan_ids.append(f.id)  # kullanıcı e-postayı açık bıraktı ama sayfayı çıkardı
    res = mask_pdf(src, tmp_path / "out.pdf", Rules.default(), set(scan_ids), drop_pages=[2])
    assert res.dropped == 1
    out = pymupdf.open(res.target)
    try:
        assert out.page_count == 1
        text = out[0].get_text()
    finally:
        out.close()
    assert TC not in text
    assert b"kimlik.sahibi" not in Path(res.target).read_bytes()


def test_drop_all_pages_is_refused(tmp_path):
    src = _two_pages(tmp_path / "iki.pdf")
    with pytest.raises(PdfError):
        mask_pdf(src, tmp_path / "out.pdf", Rules.default(), drop_pages=[1, 2])


def test_address_in_prose_does_not_swallow_neighbours():
    # Düz yazıda adres, önündeki TC ve arkasındaki telefonu yutmamalı.
    text = (
        f"TC numaram {TC}, adresim Alsancak Mah. Kıbrıs Şehitleri Cad. No:8 Konak/İzmir. "
        "Bana 0505 000 90 12 numarasından ulaşın."
    )
    found = {f.type: f.value for f in detect(text, Rules.default())}
    assert found["adres"] == "Alsancak Mah. Kıbrıs Şehitleri Cad. No:8 Konak/İzmir"
    assert found["tc_kimlik"] == TC and found["telefon"] == "0505 000 90 12"


def test_password_protected_copy(tmp_path):
    src = _two_pages(tmp_path / "iki.pdf")
    res = mask_pdf(src, tmp_path / "out.pdf", Rules.default(), password="gizli-123")
    assert res.encrypted
    out = pymupdf.open(res.target)
    try:
        assert out.needs_pass and out.authenticate("gizli-123")
        assert TC not in out[0].get_text()
    finally:
        out.close()


def test_short_password_is_refused(tmp_path):
    src = _two_pages(tmp_path / "iki.pdf")
    with pytest.raises(PdfError):
        mask_pdf(src, tmp_path / "out.pdf", Rules.default(), password="123")
