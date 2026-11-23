"""Çekirdek günlükte anahtarlı mühür (HMAC, bulgu 22): şifreli zarf ve budama ile birlikte. Veriler sahtedir."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from bulutbelge_core.audit import AuditLog, record_hash

MAC = b"m" * 32
SIFRE = b"s" * 32
SIMDI = datetime(2028, 6, 1, 9, 0, tzinfo=timezone.utc)


def _doldur(log: AuditLog, gunler: list[int]) -> None:
    for g in gunler:
        log.append("okuma", caller="kullanici", result="basarili", at=(SIMDI - timedelta(days=g)).isoformat())


def test_kisa_anahtar_reddedilir(tmp_path):
    with pytest.raises(ValueError):
        AuditLog(tmp_path / "g.jsonl", mac_key=b"kisa")


def test_mac_hash_degerini_degistirmez(tmp_path):
    log = AuditLog(tmp_path / "g.jsonl", mac_key=MAC)
    rec = log.append("okuma", caller="kullanici", result="basarili")
    assert rec["v"] == 3 and rec["hash"] == record_hash(rec)
    # Anahtarsız okuyucu zinciri yine doğrular (geriye uyum), mührü sayamaz.
    v = AuditLog(tmp_path / "g.jsonl").verify()
    assert v.ok and v.mac_checked == 0


def test_sifreli_zarf_icinde_muhur(tmp_path):
    log = AuditLog(tmp_path / "g.jsonl", cipher_key=SIFRE, mac_key=MAC)
    _doldur(log, [3, 2, 1])
    assert all(json.loads(x)["v"] == 2 for x in (tmp_path / "g.jsonl").read_text().splitlines())
    v = log.verify()
    assert v.ok and v.mac_checked == 3 and v.last_seq == 3
    yanlis = AuditLog(tmp_path / "g.jsonl", cipher_key=SIFRE, mac_key=b"x" * 32).verify()
    assert not yanlis.ok and "HMAC" in yanlis.reason


def test_budama_kontrol_noktasi_muhurlu(tmp_path):
    log = AuditLog(tmp_path / "g.jsonl", mac_key=MAC, mac_from_seq=1)
    _doldur(log, [800, 790, 10, 5])
    s = log.prune(730, now=SIMDI)
    assert s.removed == 2 and "mac" in s.checkpoint
    v = log.verify()
    assert v.ok and v.count == 2 and v.last_seq == 4
    # Kontrol noktası anahtarsız yeniden hesaplanırsa yakalanır.
    satirlar = (tmp_path / "g.jsonl").read_text().splitlines()
    cp = json.loads(satirlar[0])
    cp["silinen"] = 1
    cp["hash"] = record_hash(cp)
    (tmp_path / "g.jsonl").write_text("\n".join([json.dumps(cp)] + satirlar[1:]) + "\n")
    v = log.verify()
    assert not v.ok and v.broken_at == 1 and "HMAC" in v.reason
