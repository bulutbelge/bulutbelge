"""Sahte Türkçe örnek set uçtan uca: üretici → maskeleme → kaçak denetimi. Yalnızca sahte değer."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import kacak_kontrol  # noqa: E402
import ornek_veri_uret  # noqa: E402

BICIMLER = {".csv", ".txt", ".docx", ".pptx", ".pdf"}


@pytest.fixture(scope="module")
def set_klasoru(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("ornek")
    for make in (ornek_veri_uret.csv_files, ornek_veri_uret.server_log, ornek_veri_uret.word_contract,
                 ornek_veri_uret.presentation, ornek_veri_uret.text_contract, ornek_veri_uret.application_file):
        make(out)
    ornek_veri_uret.beklenen_yaz(out)
    return out


def test_set_metin_csv_docx_pdf_bicimlerini_kapsar(set_klasoru: Path):
    beklenen = json.loads((set_klasoru / "beklenen.json").read_text(encoding="utf-8"))
    assert {Path(n).suffix for n in beklenen} == BICIMLER
    for ad in beklenen:
        assert (set_klasoru / ad).is_file(), ad


def test_kaynak_belgelerde_degerler_gercekten_var(set_klasoru: Path):
    """Test boş geçmesin: maskelemeden önce her beklenen değer en az bir katmanda bulunur."""
    beklenen = json.loads((set_klasoru / "beklenen.json").read_text(encoding="utf-8"))
    for ad, spec in beklenen.items():
        katmanlar = kacak_kontrol._layers(set_klasoru / ad)
        for deger in spec["degerler"]:
            assert any(kacak_kontrol._norm(deger) in kacak_kontrol._norm(t) for t in katmanlar.values()), ad


def test_maskeli_kopyalarda_kacak_yok(set_klasoru: Path, tmp_path: Path, capsys):
    kod = kacak_kontrol.check(set_klasoru, tmp_path / "kontrol")
    cikti = capsys.readouterr().out
    assert kod == 0, cikti
    assert "Toplam kaçak: 0" in cikti
    assert len(list((tmp_path / "kontrol").iterdir())) == len(json.loads(
        (set_klasoru / "beklenen.json").read_text(encoding="utf-8")))
