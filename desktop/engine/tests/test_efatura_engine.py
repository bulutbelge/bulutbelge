"""Masaüstü motorunda e-fatura profili ve ZIP arşivi testleri (tüm veriler sentetiktir)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from bulutbelge_engine import settings
from bulutbelge_engine.protocol import handle_line


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(tmp_path))
    settings.VAULT.lock()
    yield tmp_path
    settings.VAULT.lock()


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    assert "error" not in resp, resp
    return resp["result"]


def test_doc_formats_includes_zip():
    fmts = call("doc.formats")
    assert "zip" in fmts["arsiv"] and "zip" in fmts["all"]


def test_legacy_settings_auto_add_efatura_profile(data_dir):
    # Eski sürümden kalma ayar dosyasında seeded=True ve seeded_builtins yok:
    legacy = {
        "version": 1,
        "active": "musteri",
        "seeded": True,
        "profiles": [p for p in call("settings.get")["profiles"] if p["id"] != "efatura"],
    }
    (data_dir / "settings.json").write_text(json.dumps(legacy), encoding="utf-8")
    loaded = call("settings.get")
    assert "efatura" in [p["id"] for p in loaded["profiles"]]


def test_engine_scans_and_masks_zip_efatura_with_efatura_profile(data_dir):
    ettn = "11111111-2222-3333-4444-555555555555"
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Invoice xmlns:cac="urn:cac" xmlns:cbc="urn:cbc">\n'
        f"  <cbc:UUID>{ettn}</cbc:UUID>\n"
        "  <cac:AccountingSupplierParty><cac:Party>\n"
        '    <cac:PartyIdentification><cbc:ID schemeID="VKN">1234567890</cbc:ID></cac:PartyIdentification>\n'
        "    <cac:PartyName><cbc:Name>Örnek Test Bilişim A.Ş.</cbc:Name></cac:PartyName>\n"
        "    <cac:PostalAddress><cbc:StreetName>Deneme Cad. No:5</cbc:StreetName><cbc:CityName>Ankara</cbc:CityName></cac:PostalAddress>\n"
        "    <cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>Çankaya</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>\n"
        "  </cac:Party></cac:AccountingSupplierParty>\n"
        '  <cac:LegalMonetaryTotal><cbc:PayableAmount currencyID="TRY">1250.00</cbc:PayableAmount></cac:LegalMonetaryTotal>\n'
        "</Invoice>\n"
    )
    zpath = data_dir / "efatura.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr(f"{ettn}.xml", xml)

    ef_prof = next(p for p in call("settings.get")["profiles"] if p["id"] == "efatura")
    scan = call("doc.scan", path=str(zpath), rules=ef_prof)
    assert scan["format"] == "arsiv"
    assert {"kurum_unvani", "adres", "vkn", "vergi_dairesi", "tutar", "ettn"} <= {f["type"] for f in scan["findings"]}

    out_path = data_dir / "efatura_maskeli.zip"
    res = call("doc.mask", source=str(zpath), target=str(out_path), rules=ef_prof)
    assert res["masked"] >= 6
    with zipfile.ZipFile(res["target"], "r") as zf:
        names = zf.namelist()
        assert len(names) == 1 and ettn not in names[0]
        masked_xml = zf.read(names[0]).decode("utf-8")
    for s in ("Örnek Test Bilişim", "Deneme Cad.", "Çankaya", "1234567890", "1250.00", ettn):
        assert s not in masked_xml
