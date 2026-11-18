"""Başlığa göre sütun türü kuralı (Excel ve CSV). Tüm veriler sahtedir."""

import zipfile
from pathlib import Path

import openpyxl
import pytest

from bulutbelge_core import office
from bulutbelge_core.rules import RuleError, Rules, header_key
from bulutbelge_core.textdoc import mask_text_doc, scan_text_doc

RULES = {"varsayilan_sutun_sozlugu": False, "column_rules": [{"header": "TC", "type": "tc_kimlik"}, {"header": "Çalışan Adı", "type": "kisi_adi"}]}


def test_header_key_folds_turkish_and_punctuation():
    assert header_key("T.C.") == "tc"
    assert header_key("  ÇALIŞAN adı ") == header_key("Çalışan Adı") == "calisanadi"
    assert header_key("IŞIK") == header_key("ışık")


def test_invalid_column_rules_rejected():
    with pytest.raises(RuleError):
        Rules.from_dict({"column_rules": [{"header": "X", "type": "yok"}]})
    with pytest.raises(RuleError):
        Rules.from_dict({"column_rules": [{"header": "X", "type": "elle"}]})
    with pytest.raises(RuleError):
        Rules.from_dict({"column_rules": [{"header": "...", "type": "iban"}]})


def test_csv_column_rule_masks_whole_column_regardless_of_content(tmp_path):
    src = tmp_path / "liste.csv"
    # Değerler TC biçiminde değil: içeriğe değil başlığa göre maskelenmeli.
    src.write_text('Ad;TC;Not\nSahte Kişi;AB-123456;"a;b"\nÖrnek Kişi;"CD-654321";TC: yok\n', encoding="utf-8")
    rules = Rules.from_dict(RULES)
    scan = scan_text_doc(src, rules)
    assert [f.finding.value for f in scan.findings if f.finding.source == "sütun"] == ["AB-123456", "CD-654321"]
    counts: dict[str, int] = {}
    out, n, _w = mask_text_doc(src, tmp_path / "o.csv", rules, counts=counts)
    text = Path(out).read_text(encoding="utf-8")
    assert "AB-123456" not in text and "CD-654321" not in text
    assert text.splitlines()[0] == "Ad;TC;Not" and '"a;b"' in text
    assert counts["tc_kimlik"] == 2 and n >= 2


def test_csv_without_rule_unchanged(tmp_path):
    src = tmp_path / "liste.csv"
    src.write_text("Ad,TC\nSahte,AB-123456\n", encoding="utf-8")
    assert not [f for f in scan_text_doc(src, Rules.from_dict({"varsayilan_sutun_sozlugu": False})).findings if f.finding.source == "sütun"]


def test_csv_disabled_type_skips_column_rule(tmp_path):
    src = tmp_path / "liste.csv"
    src.write_text("TC\nAB-123456\n", encoding="utf-8")
    rules = Rules.from_dict({**RULES, "types": {"tc_kimlik": {"enabled": False}}})
    assert scan_text_doc(src, rules).findings == []


def _xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append(["Ad", "T.C.", "Birim"])
    ws.append(["Kaan Sahte", "AB-123456", "Muhasebe"])
    ws.append(["Deniz Örnek", "CD-654321", "Muhasebe"])
    wb.save(path)
    return path


def test_excel_column_rule_masks_column_and_keeps_others(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    rules = Rules.from_dict({"column_rules": [{"header": "tc", "type": "tc_kimlik"}]})
    counts: dict[str, int] = {}
    out, masked, warnings = office.mask(src, tmp_path / "o.xlsx", office.EXCEL, rules, counts=counts)
    rows = office.sheet_preview(out)[0]["rows"]
    assert rows[0]["cells"][1]["text"] == "T.C."  # başlık durur
    assert [r["cells"][1]["text"] for r in rows[1:]] == [office.BLACKOUT_TEXT] * 2
    assert [r["cells"][2]["text"] for r in rows[1:]] == ["Muhasebe"] * 2
    with zipfile.ZipFile(out) as z:
        blob = "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())
    assert "AB-123456" not in blob and "CD-654321" not in blob
    assert counts["tc_kimlik"] == 2 and masked >= 2
    assert any("sütun kuralı" in w for w in warnings)


def test_excel_column_rule_uses_type_method(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    rules = Rules.from_dict(
        {"column_rules": [{"header": "TC", "type": "tc_kimlik"}], "types": {"tc_kimlik": {"method": "son4"}}}
    )
    out, _m, _w = office.mask(src, tmp_path / "o.xlsx", office.EXCEL, rules)
    rows = office.sheet_preview(out)[0]["rows"]
    assert rows[1]["cells"][1]["text"] == "**** 3456"


def test_excel_column_rule_does_not_double_count_auto_finding(tmp_path):
    # Hücre hem otomatik bulguya (geçerli sahte TC) hem sütun kuralına denk gelir: bir kez sayılır.
    src = tmp_path / "liste.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Ad", "TC"])
    ws.append(["Kaan Sahte", "10000000146"])
    ws.append(["Deniz Örnek", "AB-123456"])
    wb.save(src)
    rules = Rules.from_dict({"column_rules": [{"header": "TC", "type": "tc_kimlik"}]})
    counts: dict[str, int] = {}
    out, masked, _w = office.mask(src, tmp_path / "o.xlsx", office.EXCEL, rules, counts=counts)
    rows = office.sheet_preview(out)[0]["rows"]
    assert [r["cells"][1]["text"] for r in rows[1:]] == [office.BLACKOUT_TEXT] * 2
    assert counts["tc_kimlik"] == 2 and masked >= 2
