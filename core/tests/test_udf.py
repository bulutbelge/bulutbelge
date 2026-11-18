import io
import zipfile
from pathlib import Path

import pytest

from bulutbelge_core.documents import kind_of
from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules
from bulutbelge_core.udf import mask_udf, preview_text, scan_udf

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()

METIN = f"DİLEKÇE (sahte)\nDavacı TC kimlik no: {TC}\nIBAN: {IBAN}\nSon satır\n"


def _content(metin: str) -> bytes:
    n = len(metin)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n<template format_id="1.8">'
        f"<content><![CDATA[{metin}]]></content><properties><pageFormat/></properties>"
        f'<elements resolver="hvl-default"><paragraph Alignment="1"><content startOffset="0" length="{n}" bold="true"/>'
        "</paragraph></elements></template>"
    ).encode("utf-8")


def _udf(path: Path, metin: str = METIN, **extra: bytes) -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("content.xml", _content(metin))
        z.writestr("documentproperties.xml", f'<properties><entry key="yazar">Ayşe Yılmaz {TC}</entry></properties>')
        z.writestr("sign.sgn", b"sahte-imza")
        for k, v in extra.items():
            z.writestr(k, v)
    return path


@pytest.fixture
def udf_file(tmp_path: Path) -> Path:
    return _udf(tmp_path / "dilekce.udf")


def test_kind_and_preview(udf_file: Path):
    assert kind_of(udf_file) == "udf"
    assert preview_text(udf_file) == METIN


def test_scan_finds_values_with_spans(udf_file: Path):
    scan = scan_udf(udf_file, Rules.default())
    types = {f.finding.type for f in scan.findings}
    assert {"tc_kimlik", "iban"} <= types
    for f in scan.findings:
        assert scan.text[f.finding.start : f.finding.end] == f.finding.value
    assert any("imza" in w for w in scan.warnings)


def test_mask_keeps_length_structure_and_removes_values(udf_file: Path, tmp_path: Path):
    counts: dict[str, int] = {}
    out, n, warnings = mask_udf(udf_file, tmp_path / "cikti.udf", Rules.default(), counts=counts)
    assert n >= 2 and counts
    with zipfile.ZipFile(out) as z:
        assert "sign.sgn" not in z.namelist()
        raw = z.read("content.xml").decode("utf-8")
        props = z.read("documentproperties.xml").decode("utf-8")
    assert TC not in raw and IBAN not in raw and TC not in props and "Ayşe" not in props
    assert "CDATA" in raw and 'startOffset="0"' in raw and f'length="{len(METIN)}"' in raw
    masked = preview_text(out)
    assert len(masked) == len(METIN)
    assert masked.count("\n") == METIN.count("\n")
    assert "Son satır" in masked and "█" in masked


def test_excluded_findings_stay(udf_file: Path, tmp_path: Path):
    scan = scan_udf(udf_file, Rules.default())
    iban = next(f for f in scan.findings if f.finding.type == "iban")
    out, _n, _w = mask_udf(udf_file, tmp_path / "c.udf", Rules.default(), excluded_ids={iban.id})
    text = preview_text(out)
    assert IBAN in text and TC not in text


def test_not_udf_and_doctype_rejected(tmp_path: Path):
    bad = tmp_path / "x.udf"
    bad.write_bytes(b"zip degil")
    with pytest.raises(PdfError):
        scan_udf(bad, Rules.default())
    with zipfile.ZipFile(tmp_path / "y.udf", "w") as z:
        z.writestr("content.xml", b'<?xml version="1.0"?><!DOCTYPE a [<!ENTITY e "x">]><template/>')
    with pytest.raises(PdfError):
        scan_udf(tmp_path / "y.udf", Rules.default())
    with zipfile.ZipFile(tmp_path / "z.udf", "w") as z:
        z.writestr("baska.xml", b"<a/>")
    with pytest.raises(PdfError):
        scan_udf(tmp_path / "z.udf", Rules.default())


def test_source_unchanged_and_target_not_source(udf_file: Path, tmp_path: Path):
    before = udf_file.read_bytes()
    with pytest.raises(PdfError):
        mask_udf(udf_file, udf_file, Rules.default())
    mask_udf(udf_file, tmp_path / "o.udf", Rules.default())
    assert udf_file.read_bytes() == before
