from pathlib import Path

import pytest

from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules
from bulutbelge_core.textdoc import mask_text_doc, scan_text_doc

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()

XML = f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns:cbc="urn:cbc">
  <!-- Hazırlayan: ayse@ornek.com.tr -->
  <cbc:ID schemeID="TCKN">{TC}</cbc:ID>
  <cbc:Note>IBAN: {IBAN}</cbc:Note>
  <cbc:Contact telefon="0532 123 45 67">Ayşe &amp; Ali</cbc:Contact>
  <cbc:Embedded>{"QUJD" * 400}</cbc:Embedded>
</Invoice>
"""


@pytest.fixture
def xml_file(tmp_path: Path) -> Path:
    p = tmp_path / "fatura.xml"
    p.write_text(XML, encoding="utf-8")
    return p


def test_xml_scan_finds_text_attributes_and_comments(xml_file):
    scan = scan_text_doc(xml_file, Rules.from_dict(None))
    types = sorted(f.finding.type for f in scan.findings)
    assert types == ["eposta", "iban", "tc_kimlik", "telefon"]
    # Etiket adları ve öznitelik adları taranmaz.
    for f in scan.findings:
        assert scan.text[f.finding.start:f.finding.end] == f.finding.value
    assert any("gömülü" in w for w in scan.warnings)


def test_xml_mask_keeps_structure(xml_file, tmp_path):
    target, masked, _ = mask_text_doc(xml_file, tmp_path / "out.xml", Rules.from_dict(None))
    out = Path(target).read_text(encoding="utf-8")
    assert masked == 4
    assert TC not in out and "0532" not in out and "ayse@" not in out
    assert IBAN.replace(" ", "")[-4:] in out  # IBAN varsayılanı: son 4 hane açık
    assert 'schemeID="TCKN"' in out and "<cbc:ID" in out
    assert "QUJD" not in out  # gömülü dosya silindi
    assert "Ayşe &amp; Ali" in out


def test_doctype_is_rejected(tmp_path):
    p = tmp_path / "x.xml"
    p.write_text('<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "x">]><a>&e;</a>', encoding="utf-8")
    with pytest.raises(PdfError):
        scan_text_doc(p, Rules.from_dict(None))


def test_cp1254_csv_roundtrip(tmp_path):
    p = tmp_path / "liste.csv"
    p.write_bytes(f"ad;tc;şehir\r\nAyşe;{TC};İzmir\r\n".encode("cp1254"))
    rules = Rules.from_dict({"types": {"tc_kimlik": {"enabled": True, "method": "karartma"}}, "varsayilan_sutun_sozlugu": False})
    target, masked, _ = mask_text_doc(p, tmp_path / "out.csv", rules)
    raw = Path(target).read_bytes()
    assert masked == 1
    # Kodlama ve satır sonları korunur; █ 1254'te yazılamadığı için yıldız kullanılır.
    assert raw == "ad;tc;şehir\r\nAyşe;*****;İzmir\r\n".encode("cp1254")


def test_excluded_value_stays(tmp_path):
    p = tmp_path / "not.txt"
    p.write_text(f"TC: {TC}\n", encoding="utf-8")
    scan = scan_text_doc(p, Rules.from_dict(None))
    target, masked, _ = mask_text_doc(p, tmp_path / "o.txt", Rules.from_dict(None), {scan.findings[0].id})
    assert masked == 0 and TC in Path(target).read_text(encoding="utf-8")


def test_masking_twice_with_generalize_is_allowed(tmp_path):
    """İkinci kez maskelemede genelleştirilmiş il adı yeniden bulunur; kaçak sayılmamalı."""
    p = tmp_path / "a.txt"
    p.write_text("Adres: Moda Cad. No:12 Kadıköy/İstanbul\n", encoding="utf-8")
    once, _, _ = mask_text_doc(p, tmp_path / "b.txt", Rules.from_dict(None))
    twice, masked, _ = mask_text_doc(once, tmp_path / "c.txt", Rules.from_dict(None))
    # Metin dosyasında Türkçe harf korunur (PDF'te "Istanbul" yazılır).
    assert Path(twice).read_text(encoding="utf-8") == "Adres: İstanbul\n"


def test_csv_split_cells_are_found_and_masked(tmp_path):
    tc = fake_tc("198765432")
    src = tmp_path / "liste.csv"
    src.write_text(f"ad,a,b,c,d,not\nAli,{tc[:3]},{tc[3:6]},{tc[6:9]},{tc[9:]},x\nVeli,12,34,5,6,y\n", encoding="utf-8")
    scan = scan_text_doc(src, Rules.from_dict({"varsayilan_sutun_sozlugu": False}))
    assert [f.finding.type for f in scan.findings] == ["tc_kimlik"] * 4
    target, count, _w = mask_text_doc(src, tmp_path / "out.csv", Rules.from_dict({"varsayilan_sutun_sozlugu": False}))
    out = Path(target).read_text(encoding="utf-8")
    assert tc[:3] not in out and tc[9:] not in out and "Veli,12,34,5,6,y" in out
