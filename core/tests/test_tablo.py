"""Tablo verisi: üstten kodlama, tarih kaydırma, k-anonimlik uyarısı (CSV ve Excel). Tüm veriler sahtedir."""

from datetime import date
from pathlib import Path

import openpyxl
import pytest

from bulutbelge_core import office, tablo
from bulutbelge_core.rules import RuleError, Rules
from bulutbelge_core.textdoc import mask_text_doc, scan_text_doc

ACTIONS = {
    "column_rules": [
        {"header": "Yaş", "action": "yas"},
        {"header": "Başvuru Tarihi", "action": "tarih"},
        {"header": "İl", "action": "dolayli"},
        {"header": "Cinsiyet", "action": "dolayli"},
    ]
}


def test_top_code_age():
    assert tablo.top_code_age("93") == "90+"
    assert tablo.top_code_age("90") == "90+"
    assert tablo.top_code_age("89") is None
    assert tablo.top_code_age("abc") is None
    assert tablo.top_code_age("95", 80) == "80+"


def test_shift_date_keeps_format_and_relative_distance():
    assert tablo.shift_date("15.03.2020", 10) == "25.03.2020"
    assert tablo.shift_date("2020-12-25", 10) == "2021-01-04"
    assert tablo.shift_date("01/03/2020", -1) == "29/02/2020"
    assert tablo.shift_date("metin", 5) is None
    assert tablo.shift_date("31.02.2020", 5) is None


def test_new_shift_days_nonzero_and_bounded():
    for _ in range(50):
        d = tablo.new_shift_days()
        assert d != 0 and abs(d) <= tablo.MAX_SHIFT_DAYS


def test_k_anonymity_warning_has_no_values():
    rows = [["Ankara", "K"]] * 5 + [["Sinop", "E"]]
    w = tablo.k_anonymity_warning(rows, [0, 1], 5, ["İl", "Cinsiyet"])
    assert w and "1 satır" in w and "Sinop" not in w
    assert tablo.k_anonymity_warning([["Ankara", "K"]] * 5, [0, 1], 5) is None


def test_invalid_action_and_thresholds_rejected():
    with pytest.raises(RuleError):
        Rules.from_dict({"column_rules": [{"header": "X", "action": "yok"}]})
    with pytest.raises(RuleError):
        Rules.from_dict({"k_threshold": 1})
    with pytest.raises(RuleError):
        Rules.from_dict({"age_limit": "x"})
    r = Rules.from_dict({**ACTIONS, "k_threshold": 3, "age_limit": 85})
    assert r.k_threshold == 3 and r.age_limit == 85 and r.column_action("YAS") == "yas"


def test_shift_days_constant_per_rules_instance():
    r = Rules.from_dict(ACTIONS)
    assert r.shift_days() == r.shift_days() != 0


def test_csv_actions(tmp_path):
    src = tmp_path / "t.csv"
    src.write_text(
        "Yaş;Başvuru Tarihi;İl;Cinsiyet\n95;01.01.2020;Ankara;K\n40;11.01.2020;Ankara;K\n"
        "91;2020-02-01;Sinop;E\n",
        encoding="utf-8",
    )
    rules = Rules.from_dict({**ACTIONS, "k_threshold": 2})
    rules.date_shift_days = 10
    scan = scan_text_doc(src, rules)
    assert any("k-anonimlik" in w for w in scan.warnings)
    counts: dict[str, int] = {}
    out, n, warnings = mask_text_doc(src, tmp_path / "o.csv", rules, counts=counts)
    lines = Path(out).read_text(encoding="utf-8").splitlines()
    assert lines[1] == "90+;11.01.2020;Ankara;K"
    assert lines[2] == "40;21.01.2020;Ankara;K"
    assert lines[3] == "90+;2020-02-11;Sinop;E"
    assert n == 5 and counts["dogum_tarihi"] == 5
    assert any("Sinop" not in w and "k-anonimlik" in w for w in warnings)


def test_csv_type_rule_wins_over_action(tmp_path):
    src = tmp_path / "t.csv"
    src.write_text("Yaş\n95\n", encoding="utf-8")
    rules = Rules.from_dict({"column_rules": [{"header": "Yaş", "type": "tc_kimlik"}, {"header": "Yaş", "action": "yas"}]})
    f = scan_text_doc(src, rules).findings
    assert [x.finding.source for x in f] == ["sütun"]


def test_csv_without_actions_unchanged(tmp_path):
    src = tmp_path / "t.csv"
    src.write_text("Yaş\n95\n", encoding="utf-8")
    scan = scan_text_doc(src, Rules.from_dict(None))
    assert scan.findings == [] and scan.warnings == []


def test_excel_actions(tmp_path):
    src = tmp_path / "t.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Yaş", "Başvuru Tarihi", "İl", "Cinsiyet"])
    ws.append([95, "01.01.2020", "Ankara", "K"])
    ws.append([40, date(2020, 1, 11), "Ankara", "K"])
    ws.append([91, "2020-02-01", "Sinop", "E"])
    wb.save(src)
    rules = Rules.from_dict({**ACTIONS, "k_threshold": 2})
    rules.date_shift_days = 10
    counts: dict[str, int] = {}
    out, masked, warnings = office.mask(src, tmp_path / "o.xlsx", office.EXCEL, rules, counts=counts)
    assert any("k-anonimlik" in w for w in warnings)
    ws2 = openpyxl.load_workbook(out).active
    assert ws2.cell(2, 1).value == "90+" and ws2.cell(4, 1).value == "90+" and int(ws2.cell(3, 1).value) == 40
    assert ws2.cell(2, 2).value == "11.01.2020"
    assert ws2.cell(4, 2).value == "2020-02-11"
    shifted = ws2.cell(3, 2).value
    assert (shifted.date() if hasattr(shifted, "date") else shifted) == date(2020, 1, 21)
