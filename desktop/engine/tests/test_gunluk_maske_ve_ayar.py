"""Bulgu 17 (günlükte yol ve amaç maskeli) ve 18 (güvenlik ayarı değişiklikleri günlükte). Tüm veriler sahtedir."""

import json

from bulutbelge_engine import journal, settings
from bulutbelge_engine.protocol import EngineError, handle_line


def fake_tc(first9: str = "123456789") -> str:
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    return first9 + str(d10) + str((sum(d) + d10) % 10)


TC = fake_tc()


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    if "error" in resp:
        raise EngineError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]


def raw_log() -> str:
    p = settings.data_dir() / journal.LOG_FILE
    return p.read_text(encoding="utf-8") if p.exists() else ""


def records() -> list[dict]:
    return [json.loads(x) for x in raw_log().splitlines()]


def test_yol_ve_dosya_adindaki_kisisel_veri_gunluge_acik_girmez(tmp_path):
    klasor = tmp_path / "Ayşe Yılmaz"
    klasor.mkdir()
    belge = klasor / f"kira_Mehmet_Demir_{TC}.txt"
    belge.write_text("Konu: deneme\n", encoding="utf-8")
    hedef = klasor / "kira_maskeli.txt"
    call("doc.mask", source=str(belge), target=str(hedef), rules={"profile_name": "Müşteriye"})
    ham = raw_log()
    for deger in ("Ayşe Yılmaz", "Mehmet_Demir", "Mehmet", TC):
        assert deger not in ham, deger
    kayit = records()[-1]
    assert kayit["source"].endswith(".txt") and "[AD SOYAD]" in kayit["source"]
    assert call("log.verify")["ok"] is True


def test_mask_path_ayraclari_ve_surucuyu_korur():
    assert journal.mask_path("C:\\Belgeler\\fatura.pdf") == "C:\\Belgeler\\fatura.pdf"
    assert journal.mask_path("/tmp/rapor.docx") == "/tmp/rapor.docx"
    assert journal.mask_path(None) is None


def test_ajan_erisimi_degisikligi_gunluge_girer_yol_yazilmaz(tmp_path):
    izinli = tmp_path / "Ayşe Yılmaz belgeleri"
    izinli.mkdir()
    call("agent.save", folders=[str(izinli)], allow_write=True)
    kayit = records()[-1]
    assert kayit["op"] == "yonetim" and kayit["result"] == "basarili"
    assert kayit["source"] == "(ayar) ajan erişimi"
    assert kayit["counts"] == {"klasor": 1, "yazma_izni": 1}
    assert "Ayşe" not in raw_log() and str(tmp_path) not in raw_log()


def test_istisna_ve_kasa_degisiklikleri_deger_yazmadan_girer():
    call("allow.add", values=[TC], type="tc_kimlik")
    call("vault.create", password="sahte-parola-123456")
    call("vault.save", terms={"musteri": ["Gizli Proje Adı"]})
    ops = [(r["op"], r["source"]) for r in records()]
    assert ("yonetim", "(ayar) istisna ekleme") in ops
    assert ("yonetim", "(ayar) kasa oluşturma") in ops
    assert ("yonetim", "(ayar) kasa terimleri") in ops
    assert records()[-1]["counts"] == {"terim": 1}
    ham = raw_log()
    assert TC not in ham and "sahte-parola" not in ham and "Gizli Proje" not in ham
    assert call("log.verify")["ok"] is True


def test_gunluk_yazilamiyorsa_ayar_degismez(monkeypatch, tmp_path):
    def bozuk():
        raise EngineError("log_unwritable", "deneme")

    monkeypatch.setattr(journal, "_preflight", bozuk)
    try:
        call("agent.save", folders=[str(tmp_path)])
    except EngineError as exc:
        assert exc.code == "log_unwritable"
    else:
        raise AssertionError("günlük yazılamazken ayar kaydedildi")
    assert settings.load_agent()["folders"] == []
