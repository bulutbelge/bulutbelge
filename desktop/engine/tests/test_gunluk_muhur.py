"""Masaüstü işlem günlüğünde anahtarlı mühür (HMAC, bağımsız inceleme bulgu 22). Tüm veriler sahtedir."""

from __future__ import annotations

import json
import os
import stat

import pytest

from bulutbelge_core.audit import AuditError, AuditLog, record_hash
from bulutbelge_engine import journal, settings
from bulutbelge_engine.protocol import EngineError


def _log_path():
    return settings.data_dir() / journal.LOG_FILE


def _lines() -> list[dict]:
    return [json.loads(x) for x in _log_path().read_text(encoding="utf-8").splitlines() if x.strip()]


def _write(recs: list[dict]) -> None:
    _log_path().write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")


def _yaz(n: int) -> None:
    lg = journal.log()
    for i in range(n):
        lg.append("okuma", caller="kullanici", result="basarili", source=f"/belgeler/not{i}.txt", counts={"tc_kimlik": 1})


def _anahtarsiz_yeniden_hesapla(recs: list[dict], *, mac_birak: bool) -> list[dict]:
    """Anahtarı bilmeyen saldırgan: zinciri baştan hesaplar. `mac_birak`: eski mac'i olduğu gibi bırakır, değilse siler."""
    prev = "0" * 64
    out = []
    for r in recs:
        r = dict(r)
        r["prev"] = prev
        if not mac_birak:
            r.pop("mac", None)
            r["v"] = 1
        r["hash"] = record_hash(r)
        prev = r["hash"]
        out.append(r)
    return out


def test_yeni_kayitlar_muhurlu_ve_anahtar_ayri_dosyada():
    _yaz(3)
    recs = _lines()
    assert all(r["v"] == 3 and len(r["mac"]) == 64 for r in recs)
    anahtar = journal.key_path()
    assert anahtar.is_file() and anahtar != _log_path()
    veri = json.loads(anahtar.read_text(encoding="utf-8"))
    assert veri["zorunlu_sira"] == 1
    # Anahtar günlüğe girmez.
    assert veri["anahtar"] not in _log_path().read_text(encoding="utf-8")
    if os.name != "nt":
        assert stat.S_IMODE(anahtar.stat().st_mode) == 0o600
    v = journal.log_verify({})
    assert v["ok"] is True and v["count"] == 3 and v["sealed"] == 3 and v["legacy"] == 0


def test_degistirilen_kayit_yakalanir():
    _yaz(3)
    recs = _lines()
    recs[1]["counts"] = {"tc_kimlik": 5}
    _write(recs)
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 2


def test_anahtarsiz_yeniden_hesaplama_yakalanir():
    _yaz(3)
    recs = _lines()
    recs[1]["counts"] = {"tc_kimlik": 5}
    # Düz SHA-256 zinciri tutarlı; ama mac anahtarsız hesaplanamaz.
    sahte = _anahtarsiz_yeniden_hesapla(recs, mac_birak=True)
    _write(sahte)
    assert AuditLog(_log_path()).verify().ok is True  # anahtarsız denetim bunu görmezdi
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 2 and "HMAC" in v["reason"]


def test_eski_bicime_dusurme_yakalanir():
    _yaz(3)
    sahte = _anahtarsiz_yeniden_hesapla(_lines(), mac_birak=False)  # mac'ler silinmiş, v=1
    _write(sahte)
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 1 and "Mühürsüz" in v["reason"]


def test_eski_hmacsiz_gunluk_okunur_ve_dogrulanir():
    # Mühürden önceki sürümün yazdığı günlük (anahtar dosyası yok).
    eski = AuditLog(_log_path())
    eski.append("okuma", caller="kullanici", result="basarili", source="/belgeler/eski.txt")
    eski.append("maskeleme", caller="ajan", agent="deneme", result="basarili", source="/belgeler/eski.txt")
    assert not journal.key_path().exists()

    _yaz(2)  # yeni sürüm: anahtar üretilir, zorunlu sıra 3
    assert json.loads(journal.key_path().read_text(encoding="utf-8"))["zorunlu_sira"] == 3
    recs = _lines()
    assert ["mac" in r for r in recs] == [False, False, True, True]
    assert [r["op"] for r in journal.log_list({})["items"]] == ["okuma", "okuma", "maskeleme", "okuma"]
    v = journal.log_verify({})
    assert v["ok"] is True and v["count"] == 4 and v["sealed"] == 2 and v["legacy"] == 2


def test_eski_kayitlar_ilk_muhurlu_kayitla_baglanir():
    eski = AuditLog(_log_path())
    eski.append("okuma", caller="kullanici", result="basarili", source="/belgeler/eski.txt")
    eski.append("okuma", caller="kullanici", result="basarili", source="/belgeler/eski2.txt")
    _yaz(1)
    recs = _lines()
    # Saldırgan eski (mühürsüz) bölümü değiştirip yalnızca o bölümün zincirini yeniden hesaplar.
    recs[0]["source"] = "/belgeler/baska.txt"
    recs[:2] = _anahtarsiz_yeniden_hesapla(recs[:2], mac_birak=False)
    _write(recs)
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 3


def test_zorunlu_siradan_sonra_muhursuz_kayit_reddedilir():
    eski = AuditLog(_log_path())
    eski.append("okuma", caller="kullanici", result="basarili")
    journal.log()  # anahtar üretilir (zorunlu sıra 2), henüz mühürlü kayıt yok
    eski.append("okuma", caller="kullanici", result="basarili")  # anahtarsız araç ekliyor
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 2


def test_anahtar_kaybolursa_yeni_anahtar_uretilmez_islem_yapilmaz(tmp_path):
    _yaz(1)
    journal.key_path().unlink()
    with pytest.raises(AuditError, match="anahtarı bulunamadı"):
        journal.log()
    with pytest.raises(EngineError) as e:
        journal.run("okuma", lambda: {}, source=None, profile=None, counts_of=lambda _r: {})
    assert e.value.code == "log_unwritable"
    assert not journal.key_path().exists()
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] is None


def test_anahtar_yolu_ortamdan(tmp_path, monkeypatch):
    ayri = tmp_path / "ayri-birim" / "anahtar.json"
    monkeypatch.setenv(journal.KEY_ENV, str(ayri))
    _yaz(1)
    assert ayri.is_file() and not (settings.data_dir() / journal.KEY_FILE).exists()
    assert journal.log_verify({})["ok"] is True


def test_baska_anahtarla_dogrulama_basarisiz(tmp_path):
    _yaz(2)
    yol = journal.key_path()
    veri = json.loads(yol.read_text(encoding="utf-8"))
    veri["anahtar"] = "QUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUFBQUE="  # sahte 32 bayt
    yol.write_text(json.dumps(veri), encoding="utf-8")
    v = journal.log_verify({})
    assert v["ok"] is False and v["broken_at"] == 1
