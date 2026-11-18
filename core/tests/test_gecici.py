"""Geçici klasör hijyeni (TAKIP 1.73). Yalnızca sahte veri."""

import os
import stat
import tempfile
import zipfile
from pathlib import Path

import pytest

from bulutbelge_core.gecici import DIZINLEME_EKI, gecici_klasor, klasor_ac
from bulutbelge_core.rules import Rules


def test_klasor_dizinlenmez_ozeldir_ve_hata_olsa_silinir():
    with pytest.raises(RuntimeError):
        with gecici_klasor("bb-deneme-") as k:
            assert k.name.endswith(DIZINLEME_EKI) and k.name.startswith("bb-deneme-")
            (k / "ham.txt").write_text("sahte", encoding="utf-8")
            yol = k
            if os.name != "nt":  # Windows'ta izin bitleri anlamlı değil
                assert stat.S_IMODE(k.stat().st_mode) == 0o700
            raise RuntimeError("işlem yarıda kesildi")
    assert not yol.exists()


def test_klasor_ac_sistem_gecici_klasorunde_acilir():
    k = klasor_ac("bb-deneme-")
    try:
        assert Path(tempfile.gettempdir()).resolve() in k.resolve().parents
    finally:
        k.rmdir()


def _gecici_klasorler() -> set[str]:
    return {p.name for p in Path(tempfile.gettempdir()).glob(f"bb-*{DIZINLEME_EKI}")} | {
        p.name for p in Path(tempfile.gettempdir()).glob(f"bulutbelge-*{DIZINLEME_EKI}")
    }


def test_arsiv_ve_eposta_islemi_gecici_klasor_birakmaz(tmp_path):
    from bulutbelge_core.archive import mask_archive, scan_archive
    from bulutbelge_core.eposta import mask_eml, scan_eml

    once = _gecici_klasorler()
    zip_yolu = tmp_path / "a.zip"
    with zipfile.ZipFile(zip_yolu, "w") as z:
        z.writestr("not.txt", "E-posta: ayse@ornek.com.tr\n")
    scan_archive(zip_yolu, Rules.default())
    mask_archive(zip_yolu, tmp_path / "o.zip", Rules.default())
    eml = tmp_path / "a.eml"
    eml.write_bytes("From: a@ornek.com.tr\nTo: b@ornek.com.tr\nSubject: x\n\nTelefon: 0532 000 12 34\n".encode("utf-8"))
    scan_eml(eml, Rules.default())
    mask_eml(eml, tmp_path / "o.eml", Rules.default())
    assert _gecici_klasorler() == once  # işlem sonunda ham içerik taşıyan klasör kalmadı
