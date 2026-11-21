"""Word ve PowerPoint tablosunda hücrelere bölünmüş TC/IBAN/telefon."""

from pathlib import Path

import docx
import pptx
from pptx.util import Inches

from bulutbelge_core import office
from bulutbelge_core.rules import Rules

from fake_data import fake_iban, fake_tc

TC = fake_tc("198765432")
IBAN = fake_iban().replace(" ", "")


def _docx(path: Path, rows: list[list[str]]) -> Path:
    d = docx.Document()
    d.add_paragraph("Liste (sahte veri)")
    t = d.add_table(rows=len(rows), cols=len(rows[0]))
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            t.cell(r, c).text = val
    d.save(path)
    return path


def _pptx(path: Path, rows: list[list[str]]) -> Path:
    p = pptx.Presentation()
    s = p.slides.add_slide(p.slide_layouts[6])
    tbl = s.shapes.add_table(len(rows), len(rows[0]), Inches(0.5), Inches(0.5), Inches(8), Inches(2)).table
    for r, row in enumerate(rows):
        for c, val in enumerate(row):
            tbl.cell(r, c).text = val
    p.save(path)
    return path


def _docx_text(path: str) -> list[list[str]]:
    t = docx.Document(path).tables[0]
    return [[c.text for c in row.cells] for row in t.rows]


def _pptx_text(path: str) -> list[list[str]]:
    p = pptx.Presentation(path)
    tbl = next(sh for sh in p.slides[0].shapes if sh.has_table).table
    return [[c.text for c in row.cells] for row in tbl.rows]


ROWS = [
    ["Ad", "a", "b", "c", "d"],
    ["Ali", TC[:3], TC[3:6], TC[6:9], TC[9:]],
    ["Veli", "12", "34", "56", "78"],  # doğrulanmayan parçalar dokunulmaz
]


def test_word_tablosunda_bolunmus_tc(tmp_path):
    src = _docx(tmp_path / "t.docx", ROWS)
    rules = Rules.from_dict(None)
    scan = office.scan(src, office.WORD, rules)
    assert sorted(f.finding.type for f in scan.findings if f.finding.source == office.SPLIT_NOTE) == ["tc_kimlik"] * 4
    target, _n, _w = office.mask(src, tmp_path / "o.docx", office.WORD, rules)
    tablo = _docx_text(target)
    assert not any(p in tablo[1] for p in (TC[:3], TC[3:6], TC[6:9], TC[9:]))
    assert tablo[2] == ["Veli", "12", "34", "56", "78"]


def test_powerpoint_tablosunda_bolunmus_iban(tmp_path):
    gruplar = [IBAN[i : i + 4] for i in range(0, 26, 4)]  # TR33 0006 ... 26 (4'erli yazım, 7 hücre)
    rows = [["IBAN", *gruplar], ["Not", *[str(i) for i in range(7)]]]
    src = _pptx(tmp_path / "t.pptx", rows)
    rules = Rules.from_dict(None)
    target, _n, _w = office.mask(src, tmp_path / "o.pptx", office.POWERPOINT, rules)
    tablo = _pptx_text(target)
    assert not any(g in tablo[0][1:] for g in gruplar)
    assert tablo[1] == rows[1]
