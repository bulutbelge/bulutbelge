"""Denetçiye profili tutarları aralığa çevirir; eski kurulumlara bir kez göç edilir."""

import json

import pytest

from bulutbelge_core.profiles import builtin_profiles
from bulutbelge_core.rules import Rules
from bulutbelge_core.detect import detect
from bulutbelge_engine import settings


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(tmp_path))
    return tmp_path


def _denetci(profiles):
    return next(p for p in profiles if p["id"] == "denetci")


def _eski_kurulum(data_dir, tutar):
    """Göçten önceki bir kurulumun settings.json dosyası (migrations alanı yok)."""
    profiles = builtin_profiles()
    _denetci(profiles)["types"]["tutar"] = tutar
    data = {"version": 1, "active": "denetci", "profiles": profiles, "seeded": True,
            "seeded_builtins": ["musteri", "denetci", "kurum_ici", "efatura"]}
    (data_dir / settings.SETTINGS_FILE).write_text(json.dumps(data), encoding="utf-8")


def test_yeni_kurulumda_denetci_tutari_araliga_cevirir():
    rule = _denetci(settings.load_settings()["profiles"])["types"]["tutar"]
    assert rule == {"enabled": True, "method": "genel"}


def test_eski_varsayilan_bir_kez_gocer_ve_kullanici_kapatirsa_kapali_kalir(data_dir):
    _eski_kurulum(data_dir, {"enabled": False, "method": "genel"})
    s = settings.load_settings()
    assert _denetci(s["profiles"])["types"]["tutar"]["enabled"] is True
    # Kullanıcı göçten sonra tutarı bilerek kapatıp kaydeder: tekrar açılmamalı.
    _denetci(s["profiles"])["types"]["tutar"]["enabled"] = False
    settings.save_settings(s)
    again = settings.load_settings()
    assert _denetci(again["profiles"])["types"]["tutar"]["enabled"] is False


def test_kullanicinin_degistirdigi_tutar_kuralina_dokunulmaz(data_dir):
    _eski_kurulum(data_dir, {"enabled": False, "method": "karartma"})
    rule = _denetci(settings.load_settings()["profiles"])["types"]["tutar"]
    assert rule == {"enabled": False, "method": "karartma"}


def test_denetci_tutari_bulur_ve_araliga_cevirir():
    rules = Rules.from_dict(_denetci(builtin_profiles()))
    text = "Toplam tutar: 12.345,67 TL"
    found = [f for f in detect(text, rules) if f.type == "tutar"]
    assert found, "tutar bulunmalı"
    out = rules.replacement_for(found[0])
    assert "12.345" not in out and "TL" in out  # kesin değer gider, büyüklük aralığı kalır
