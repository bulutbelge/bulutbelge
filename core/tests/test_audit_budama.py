"""İşlem günlüğü saklaması: kontrol noktalı budama (TAKIP G.2). Tüm veriler sahtedir, saat enjekte edilir."""

import base64
import json
import os
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from bulutbelge_core.audit import (
    _AUDIT_AAD,
    CHECKPOINT_KIND,
    GENESIS,
    AuditError,
    AuditLog,
    filter_records,
    record_hash,
    to_csv,
)

ANAHTAR = bytes(range(32))  # sahte test anahtarı
SIMDI = datetime(2028, 6, 1, 12, 0, tzinfo=timezone.utc)


def _gunluk(tmp_path: Path, sifreli: bool) -> AuditLog:
    return AuditLog(tmp_path / "islem-gunlugu.jsonl", cipher_key=ANAHTAR if sifreli else None)


def _doldur(log: AuditLog, gunler_once: list[int]) -> list[dict]:
    """Her öğe için `SIMDI - gün` zamanlı bir kayıt ekler (eskiden yeniye)."""
    return [
        log.append("okuma", caller="kullanici", result="basarili", source="(yüklenen belge) ornek.pdf",
                   at=(SIMDI - timedelta(days=g)).isoformat(timespec="seconds"))
        for g in gunler_once
    ]


def _satir_ac(raw: str, sifreli: bool) -> dict:
    obj = json.loads(raw)
    if not sifreli:
        return obj
    blob = base64.urlsafe_b64decode(obj["enc"])
    return json.loads(AESGCM(ANAHTAR).decrypt(blob[:12], blob[12:], _AUDIT_AAD))


def _satir_kapat(rec: dict, sifreli: bool) -> str:
    plain = json.dumps(rec, ensure_ascii=False, separators=(",", ":"))
    if not sifreli:
        return plain
    nonce = os.urandom(12)
    token = base64.urlsafe_b64encode(nonce + AESGCM(ANAHTAR).encrypt(nonce, plain.encode(), _AUDIT_AAD)).decode()
    return json.dumps({"v": 2, "enc": token}, separators=(",", ":"))


def _satirlar(log: AuditLog) -> list[str]:
    return log.path.read_text(encoding="utf-8").splitlines()


def _yaz(log: AuditLog, satirlar: list[str]) -> None:
    log.path.write_text("\n".join(satirlar) + "\n", encoding="utf-8")


@pytest.mark.parametrize("sifreli", [False, True])
def test_budama_sonrasi_zincir_dogrulanir(tmp_path, sifreli):
    log = _gunluk(tmp_path, sifreli)
    kayitlar = _doldur(log, [900, 800, 740, 700, 10, 1])
    eski_satirlar = _satirlar(log)

    s = log.prune(730, now=SIMDI)

    assert s.changed and s.removed == 3 and s.remaining == 3
    satirlar = _satirlar(log)
    assert len(satirlar) == 4
    assert satirlar[1:] == eski_satirlar[3:]  # kalan satırlar bayt bayt aynı
    cp = _satir_ac(satirlar[0], sifreli)
    assert cp["tur"] == CHECKPOINT_KIND
    assert cp["son_seq"] == 3 and cp["son_silinen_ozet"] == kayitlar[2]["hash"]
    assert cp["silinen"] == 3 and cp["budama_sayisi"] == 1 and cp["saklama_gun"] == 730
    if sifreli:
        assert json.loads(satirlar[0])["v"] == 2 and "enc" in json.loads(satirlar[0])
    v = log.verify()
    assert v.ok and v.count == 3 and v.last_hash == kayitlar[-1]["hash"] and v.checkpoint["son_seq"] == 3
    assert [r["seq"] for r in log.records()] == [4, 5, 6]
    assert log.checkpoint() == cp
    # Budama sonrası ekleme zinciri sürdürür.
    yeni = log.append("okuma", caller="kullanici", result="basarili")
    assert yeni["seq"] == 7 and yeni["prev"] == kayitlar[-1]["hash"]
    assert log.verify().ok


@pytest.mark.parametrize("sifreli", [False, True])
def test_hic_suresi_dolmamissa_dosya_degismez(tmp_path, sifreli):
    log = _gunluk(tmp_path, sifreli)
    _doldur(log, [700, 100, 1])
    once = log.path.read_bytes()
    s = log.prune(730, now=SIMDI)
    assert not s.changed and s.removed == 0 and s.remaining == 3 and s.checkpoint is None
    assert log.path.read_bytes() == once


def test_eski_gunluk_kontrol_noktasiz_dogrulanir(tmp_path):
    log = _gunluk(tmp_path, False)
    _doldur(log, [3, 2, 1])
    v = log.verify()
    assert v.ok and v.count == 3 and v.checkpoint is None and log.checkpoint() is None


@pytest.mark.parametrize("sifreli", [False, True])
def test_ardisik_iki_budama_kontrol_noktasini_degistirir(tmp_path, sifreli):
    log = _gunluk(tmp_path, sifreli)
    kayitlar = _doldur(log, [1000, 900, 800, 600, 550, 5])
    assert log.prune(730, now=SIMDI).removed == 3
    s = log.prune(730, now=SIMDI + timedelta(days=200))  # 600 ve 550 gün öncekiler de doldu

    assert s.removed == 2 and s.remaining == 1
    satirlar = _satirlar(log)
    assert len(satirlar) == 2
    cp = _satir_ac(satirlar[0], sifreli)
    assert cp["silinen"] == 5 and cp["budama_sayisi"] == 2
    assert cp["son_seq"] == 5 and cp["son_silinen_ozet"] == kayitlar[4]["hash"]
    v = log.verify()
    assert v.ok and v.count == 1


@pytest.mark.parametrize("sifreli", [False, True])
def test_butun_kayitlar_budanirsa_ekleme_surer(tmp_path, sifreli):
    log = _gunluk(tmp_path, sifreli)
    kayitlar = _doldur(log, [900, 800])
    s = log.prune(730, now=SIMDI)
    assert s.removed == 2 and s.remaining == 0
    v = log.verify()
    assert v.ok and v.count == 0 and v.last_hash == kayitlar[-1]["hash"]
    assert log.records() == []
    yeni = log.append("okuma", caller="kullanici", result="basarili")
    assert yeni["seq"] == 3 and yeni["prev"] == kayitlar[-1]["hash"]
    assert log.verify().ok


def test_yalnizca_bastaki_kesintisiz_dilim_silinir(tmp_path):
    """Zamanı geriye dönük yazılmış (eski `at`) bir kayıt, önündeki yeni kayıt silinmedikçe silinmez."""
    log = _gunluk(tmp_path, False)
    _doldur(log, [900, 10, 900, 800])
    s = log.prune(730, now=SIMDI)
    assert s.removed == 1 and s.remaining == 3
    assert [r["seq"] for r in log.records()] == [2, 3, 4]
    assert log.verify().ok


def test_okunamayan_zamanda_durulur(tmp_path):
    log = _gunluk(tmp_path, False)
    _doldur(log, [900])
    log.append("okuma", caller="kullanici", result="basarili", at="zaman-yok")
    _doldur(log, [800])
    s = log.prune(730, now=SIMDI)
    assert s.removed == 1 and [r["seq"] for r in log.records()] == [2, 3]


def test_esik_zamaniyla_budama(tmp_path):
    log = _gunluk(tmp_path, False)
    _doldur(log, [50, 40, 30])
    s = log.prune(older_than=SIMDI - timedelta(days=35), now=SIMDI)
    assert s.removed == 2
    cp = log.checkpoint()
    assert cp["saklama_gun"] is None and datetime.fromisoformat(cp["esik"]) == SIMDI - timedelta(days=35)


def test_gecersiz_budama_parametreleri(tmp_path):
    log = _gunluk(tmp_path, False)
    _doldur(log, [1])
    for kw in ({}, {"days": 0}, {"days": -5}, {"days": True}, {"days": 10, "older_than": SIMDI}):
        with pytest.raises(ValueError):
            log.prune(now=SIMDI, **kw)


def test_bozuk_zincir_budanmaz(tmp_path):
    """Şüphede reddet: bozuk bölüm budamayla örtülmesin."""
    log = _gunluk(tmp_path, False)
    _doldur(log, [900, 800, 1])
    satirlar = _satirlar(log)
    rec = json.loads(satirlar[1])
    rec["result"] = "hata"
    satirlar[1] = json.dumps(rec, ensure_ascii=False)
    _yaz(log, satirlar)
    once = log.path.read_bytes()
    with pytest.raises(AuditError, match="budama yapılmadı"):
        log.prune(730, now=SIMDI)
    assert log.path.read_bytes() == once


# ---------------------------------------------------------------- kurcalama yakalanır


def _budanmis(tmp_path: Path, sifreli: bool) -> AuditLog:
    log = _gunluk(tmp_path, sifreli)
    _doldur(log, [900, 800, 10, 5, 1])
    assert log.prune(730, now=SIMDI).removed == 2
    assert log.verify().ok
    return log


@pytest.mark.parametrize("sifreli", [False, True])
def test_kalan_kaydi_degistirmek_yakalanir(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    satirlar = _satirlar(log)
    rec = _satir_ac(satirlar[2], sifreli)
    rec["result"] = "hata"
    satirlar[2] = _satir_kapat(rec, sifreli)
    _yaz(log, satirlar)
    v = log.verify()
    assert not v.ok and v.broken_at == 3


@pytest.mark.parametrize("sifreli", [False, True])
def test_kontrol_noktasini_silmek_yakalanir(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    _yaz(log, _satirlar(log)[1:])
    v = log.verify()
    assert not v.ok and v.broken_at == 1 and "Zincir kopuk" in v.reason


@pytest.mark.parametrize("sifreli", [False, True])
def test_kontrol_noktasini_degistirmek_yakalanir(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    satirlar = _satirlar(log)
    cp = _satir_ac(satirlar[0], sifreli)
    cp["silinen"] = 1  # özet yeniden hesaplanmadan
    satirlar[0] = _satir_kapat(cp, sifreli)
    _yaz(log, satirlar)
    v = log.verify()
    assert not v.ok and v.broken_at == 1 and "Kontrol noktası" in v.reason


def test_sifreli_kontrol_noktasinin_baytini_bozmak_yakalanir(tmp_path):
    log = _budanmis(tmp_path, True)
    satirlar = _satirlar(log)
    obj = json.loads(satirlar[0])
    blob = bytearray(base64.urlsafe_b64decode(obj["enc"]))
    blob[20] ^= 1
    obj["enc"] = base64.urlsafe_b64encode(bytes(blob)).decode()
    satirlar[0] = json.dumps(obj)
    _yaz(log, satirlar)
    v = log.verify()
    assert not v.ok and v.broken_at == 1


def test_sifresiz_kontrol_noktasi_ozetiyle_dogrulanir(tmp_path):
    """Şifresiz günlükte özet yeniden hesaplanırsa sahte kontrol noktası tutarlı görünebilir; sınır karar
    kaydında yazılı. Ama zincire uymayan bir kontrol noktası (yanlış son özet) yine yakalanır."""
    log = _budanmis(tmp_path, False)
    satirlar = _satirlar(log)
    cp = json.loads(satirlar[0])
    cp["son_silinen_ozet"] = "a" * 64
    cp["hash"] = record_hash(cp)
    satirlar[0] = json.dumps(cp)
    _yaz(log, satirlar)
    v = log.verify()
    assert not v.ok and v.broken_at == 2 and "Zincir kopuk" in v.reason


@pytest.mark.parametrize("sifreli", [False, True])
def test_kontrol_noktasi_oncesine_kayit_eklemek_yakalanir(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    sahte = {"v": 1, "seq": 1, "at": SIMDI.isoformat(), "op": "okuma", "source": None, "target": None,
             "source_sha256": None, "target_sha256": None, "counts": {}, "profile": None, "purpose": None,
             "caller": "kullanici", "agent": None, "result": "basarili", "error": None, "prev": GENESIS}
    sahte["hash"] = record_hash(sahte)
    _yaz(log, [_satir_kapat(sahte, sifreli)] + _satirlar(log))
    v = log.verify()
    assert not v.ok and v.broken_at == 2 and "ilk kaydı" in v.reason


@pytest.mark.parametrize("sifreli", [False, True])
def test_kontrol_noktasi_ortada_olamaz(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    satirlar = _satirlar(log)
    _yaz(log, [satirlar[1], satirlar[0], *satirlar[2:]])
    assert not log.verify().ok


def test_kontrol_noktasindan_sonraki_ilk_kaydi_silmek_yakalanir(tmp_path):
    log = _budanmis(tmp_path, True)
    satirlar = _satirlar(log)
    _yaz(log, [satirlar[0], *satirlar[2:]])
    v = log.verify()
    assert not v.ok and v.broken_at == 2


def test_anahtarsiz_sifreli_budama_reddedilir(tmp_path):
    log = _budanmis(tmp_path, True)
    once = log.path.read_bytes()
    with pytest.raises(AuditError):
        AuditLog(log.path).prune(730, now=SIMDI + timedelta(days=400))
    assert log.path.read_bytes() == once


# ---------------------------------------------------------------- atomiklik ve eşzamanlılık


def test_yarida_kalan_gecici_dosya_eski_gunlugu_bozmaz(tmp_path, monkeypatch):
    log = _gunluk(tmp_path, True)
    _doldur(log, [900, 800, 1])
    # Önceki bir budamadan kalmış yarım geçici dosya.
    kalinti = log.path.with_name(log.path.name + ".budama.tmp")
    kalinti.write_bytes(b'{"yarim')
    assert log.verify().ok and len(log.records()) == 3
    once = log.path.read_bytes()

    # Bu budama os.replace aşamasında kesilir: eski günlük yerinde, geçici dosya temizlenir.
    def kesik(*_a, **_k):
        raise OSError("yapay kesinti")

    monkeypatch.setattr(os, "replace", kesik)
    with pytest.raises(AuditError, match="budanamadı"):
        log.prune(730, now=SIMDI)
    monkeypatch.undo()
    assert log.path.read_bytes() == once and log.verify().ok
    assert not kalinti.exists()

    # Sonraki deneme başarılı.
    assert log.prune(730, now=SIMDI).removed == 2 and log.verify().ok


def test_yazma_sirasinda_kesinti_eski_gunlugu_bozmaz(tmp_path, monkeypatch):
    log = _gunluk(tmp_path, False)
    _doldur(log, [900, 800, 1])
    once = log.path.read_bytes()

    def kesik(_fd):
        raise OSError("disk dolu")

    monkeypatch.setattr(os, "fsync", kesik)
    with pytest.raises(AuditError):
        log.prune(730, now=SIMDI)
    monkeypatch.undo()
    assert log.path.read_bytes() == once and log.verify().ok


@pytest.mark.parametrize("sifreli", [False, True])
def test_eszamanli_ekleme_ve_budama(tmp_path, sifreli):
    log = _gunluk(tmp_path, sifreli)
    _doldur(log, [900] * 20 + [1] * 5)
    hatalar: list[BaseException] = []

    def ekle() -> None:
        try:
            for _ in range(15):
                AuditLog(log.path, cipher_key=ANAHTAR if sifreli else None).append(
                    "okuma", caller="ajan", result="basarili")
        except BaseException as exc:  # noqa: BLE001
            hatalar.append(exc)

    sonuclar = []

    def buda() -> None:
        try:
            for i in range(5):
                sonuclar.append(log.prune(730, now=SIMDI + timedelta(days=i)))
        except BaseException as exc:  # noqa: BLE001
            hatalar.append(exc)

    isler = [threading.Thread(target=ekle) for _ in range(3)] + [threading.Thread(target=buda)]
    for t in isler:
        t.start()
    for t in isler:
        t.join()

    assert not hatalar
    assert sum(s.removed for s in sonuclar) == 20
    v = log.verify()
    assert v.ok and v.count == 5 + 45 and v.checkpoint["silinen"] == 20
    assert [r["seq"] for r in log.records()] == list(range(21, 71))


# ---------------------------------------------------------------- okuma yolları


@pytest.mark.parametrize("sifreli", [False, True])
def test_csv_ve_suzgec_kontrol_noktasini_olay_gibi_gostermez(tmp_path, sifreli):
    log = _budanmis(tmp_path, sifreli)
    kayitlar = log.records()
    assert all("tur" not in r for r in kayitlar)
    assert len(filter_records(kayitlar)) == 3
    assert len(filter_records(kayitlar, op="okuma")) == 3
    csv = to_csv(kayitlar)
    satirlar = csv.strip().split("\r\n")
    assert len(satirlar) == 4  # başlık + 3 kayıt
    assert CHECKPOINT_KIND not in csv


def test_sifresiz_gunluk_gocle_sifrelenince_kontrol_noktasi_korunur(tmp_path):
    log = _budanmis(tmp_path, False)
    enc = AuditLog(log.path, cipher_key=ANAHTAR)
    assert enc.migrate_to_encrypted() == 4
    v = enc.verify()
    assert v.ok and v.count == 3 and v.checkpoint["silinen"] == 2
