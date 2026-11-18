"""Excel'de elle seçilen satır ve sütunun tamamının silinmesi. Tüm veriler sahtedir."""

import zipfile
from pathlib import Path

import openpyxl
import pytest

from bulutbelge_core import office
from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules


def _xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append(["Ad", "Sicil", "Birim", "Not"])
    ws.append(["Kaan Sahte", "SC-77801", "Muhasebe", "ortak"])
    ws.append(["Deniz Örnek", "SC-77802", "Muhasebe", "=B2"])
    ws.append(["Ece Deneme", 4455, "ortak", ""])
    wb.create_sheet("Diğer").append(["SC-77801"])  # başka sayfada aynı metin (paylaşılan metin)
    wb.save(path)
    return path


def _all_text(path: Path) -> str:
    with zipfile.ZipFile(path) as z:
        return "".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def test_column_is_cleared_everywhere_but_shared_text_kept_where_used(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    counts: dict[str, int] = {}
    out, masked, warnings = office.mask(
        src, tmp_path / "out.xlsx", office.EXCEL, Rules.from_dict(None), counts=counts, manual_cells=[("Liste", "col", 1)]
    )
    sheets = {s["name"]: s for s in office.sheet_preview(out)}
    col_b = [r["cells"][1]["text"] for r in sheets["Liste"]["rows"]]
    assert col_b == [office.BLACKOUT_TEXT] * 4  # başlık dahil sütunun tamamı
    assert [r["cells"][2]["text"] for r in sheets["Liste"]["rows"]][1] == "Muhasebe"  # diğer sütun duruyor
    assert sheets["Diğer"]["rows"][0]["cells"][0]["text"] == "SC-77801"  # başka sayfadaki aynı metin korunur
    text = _all_text(Path(out))
    assert "SC-77802" not in text and "4455" not in text  # yalnızca o sütunda kullanılan değerler dosyadan gider
    assert counts["elle"] == 4 and masked >= 4
    assert any("formül" in w for w in warnings)


def test_row_selection_and_label_method(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    rules = Rules.from_dict({"types": {"elle": {"enabled": True, "method": "etiket"}}})
    out, _m, _w = office.mask(src, tmp_path / "out.xlsx", office.EXCEL, rules, manual_cells=[("Liste", "row", 3)])
    row3 = office.sheet_preview(out)[0]["rows"][2]["cells"]
    assert [c["text"] for c in row3] == ["[GIZLI]"] * 3 + ["[GIZLI]"]
    assert "Deniz Örnek" not in _all_text(Path(out))
    assert "=B2" not in _all_text(Path(out))  # formül de silinir


def test_unknown_sheet_and_non_excel_rejected(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    with pytest.raises(PdfError):
        office.mask(src, tmp_path / "o.xlsx", office.EXCEL, Rules.from_dict(None), manual_cells=[("Yok", "col", 0)])
    with pytest.raises(PdfError):
        office.mask_bytes(src, office.WORD, Rules.from_dict(None), manual_cells=[("Liste", "col", 0)])


def test_line_methods_use_original_values(tmp_path):
    from bulutbelge_core.pseudonym import Pseudonyms

    src = tmp_path / "liste.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append(["Ad Soyad", "Numara", "Kod"])
    ws.append(["Kaan Sahte", 5320001234, "KX-1"])
    ws.append(["Deniz Örnek", "0541 000 56 78", "KX-2"])
    ws.append(["Kaan Sahte", 12, "KX-1"])
    wb.save(src)
    rules = Rules.from_dict(None)
    rules.pseudonyms = Pseudonyms()
    out, _m, _w = office.mask(
        src, tmp_path / "out.xlsx", office.EXCEL, rules,
        manual_cells=[("Liste", "col", 0, "bas_harf"), ("Liste", "col", 1, "son4"), ("Liste", "col", 2, "takma_ad")],
    )
    rows = office.sheet_preview(out)[0]["rows"]
    assert [r["cells"][0]["text"] for r in rows[1:]] == ["K. S.", "D. Ö.", "K. S."]
    assert [r["cells"][1]["text"] for r in rows[1:]] == ["**** 1234", "**** 5678", "****"]
    codes = [r["cells"][2]["text"] for r in rows[1:]]
    assert codes[0] == codes[2] != codes[1] and codes[0].startswith("Değer-")  # aynı değer aynı takma ad
    assert rules.pseudonyms.lookup(codes[1]) == {"type": "elle", "value": "KX-2"}
    text = _all_text(Path(out))
    assert "Kaan Sahte" not in text and "5320001234" not in text and "KX-2" not in text


def test_row_and_column_overlap_uses_stricter_method(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    out, _m, _w = office.mask(
        src, tmp_path / "out.xlsx", office.EXCEL, Rules.from_dict(None),
        manual_cells=[("Liste", "col", 1, "son4"), ("Liste", "row", 2, "karartma")],
    )
    rows = office.sheet_preview(out)[0]["rows"]
    assert rows[1]["cells"][1]["text"] == office.BLACKOUT_TEXT  # kesişimde karartma
    assert rows[2]["cells"][1]["text"] == "**** 7802"


def test_pseudonym_line_needs_vault(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    with pytest.raises(PdfError):
        office.mask(src, tmp_path / "o.xlsx", office.EXCEL, Rules.from_dict(None), manual_cells=[("Liste", "col", 1, "takma_ad")])


def test_dependent_formulas_are_named_in_warning(tmp_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append(["Ad", "Tutar", "Not"])
    ws.append(["Kaan Sahte", 100, "=B2*2"])
    ws.append(["Deniz Örnek", 200, "=SUM(B2:B3)"])
    ws.append(["Ece Deneme", 300, "=LOG10(7)"])
    wb.create_sheet("Özet").append(["=Liste!B3+1", "=B1"])
    src = tmp_path / "bagimli.xlsx"
    wb.save(src)
    _o, _m, warnings = office.mask(
        src, tmp_path / "out.xlsx", office.EXCEL, Rules.from_dict(None), manual_cells=[("Liste", "col", 1)]
    )
    w = next(x for x in warnings if "başvuruyor" in x)
    assert "Liste!C2" in w and "Liste!C3" in w and "Özet!A1" in w
    assert "Liste!C4" not in w and "Özet!B1" not in w
