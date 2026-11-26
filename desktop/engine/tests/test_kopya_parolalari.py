"""Kayıtlı kopya parolaları (karar 2026-11-25-kayitli-kopya-parolalari). Tüm parolalar ve belgeler sahtedir."""

import inspect
import json

import fitz
import pytest

from bulutbelge_engine import ajan, journal, settings
from bulutbelge_engine.protocol import EngineError, handle_line

KASA = "sahte-kasa-parolasi"
PAROLA = "sahte-kopya-123"


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    if "error" in resp:
        raise EngineError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]


def err(method, **params) -> str:
    with pytest.raises(EngineError) as e:
        call(method, **params)
    return e.value.code


def raw_log() -> str:
    p = settings.data_dir() / journal.LOG_FILE
    return p.read_text(encoding="utf-8") if p.exists() else ""


def pdf(path):
    doc = fitz.open()
    doc.new_page().insert_text((72, 72), "Deneme belgesi, kisisel veri yok.")
    doc.save(str(path))
    doc.close()
    return path


def test_ekle_listele_degistir_sil_ve_degerler_listede_yok():
    call("vault.create", password=KASA)
    out = call("vault.password_add", name="  Denetçi   firma ", value=PAROLA)
    pid = out["id"]
    call("vault.password_add", name="Muhasebe", value="baska-sahte-1")
    liste = call("vault.passwords")["passwords"]
    assert [p["name"] for p in liste] == ["Denetçi firma", "Muhasebe"]
    assert "sahte" not in json.dumps(liste)

    call("vault.password_update", id=pid, name="Denetim")
    assert call("vault.password_reveal", id=pid)["value"] == PAROLA
    call("vault.password_update", id=pid, value="yeni-sahte-9")
    assert call("vault.password_reveal", id=pid)["value"] == "yeni-sahte-9"

    call("vault.password_delete", id=pid)
    assert [p["name"] for p in call("vault.passwords")["passwords"]] == ["Muhasebe"]
    assert err("vault.password_reveal", id=pid) == "not_found"


def test_dogrulamalar():
    call("vault.create", password=KASA)
    assert err("vault.password_add", name="Kısa", value="12345") == "weak_password"
    assert err("vault.password_add", name=" ", value=PAROLA) == "invalid_params"
    call("vault.password_add", name="Muhasebe", value=PAROLA)
    assert err("vault.password_add", name="muhasebe", value=PAROLA) == "duplicate"


def test_kasa_kilitliyken_kullanilamaz_ve_diskte_acik_durmaz():
    call("vault.create", password=KASA)
    call("vault.password_add", name="Gizli Alıcı Adı", value=PAROLA)
    ham = (settings.data_dir() / settings.VAULT_FILE).read_bytes()
    assert PAROLA.encode() not in ham and "Gizli Alıcı".encode() not in ham

    call("vault.lock")
    assert err("vault.passwords") == "vault_locked"
    assert err("vault.password_add", name="X", value=PAROLA) == "vault_locked"

    call("vault.unlock", password=KASA)
    assert [p["name"] for p in call("vault.passwords")["passwords"]] == ["Gizli Alıcı Adı"]


def test_kasa_parolasi_degisince_kayitli_parolalar_korunur():
    call("vault.create", password=KASA)
    pid = call("vault.password_add", name="Muhasebe", value=PAROLA)["id"]
    call("vault.change_password", password="yeni-sahte-kasa-1")
    call("vault.lock")
    assert err("vault.unlock", password=KASA) == "wrong_password"
    call("vault.unlock", password="yeni-sahte-kasa-1")
    assert call("vault.password_reveal", id=pid)["value"] == PAROLA


def test_kaydederken_kayitli_parola_ile_pdf_sifrelenir(tmp_path):
    call("vault.create", password=KASA)
    pid = call("vault.password_add", name="Muhasebe", value=PAROLA)["id"]
    kaynak = pdf(tmp_path / "belge.pdf")
    hedef = tmp_path / "belge_maskeli.pdf"
    out = call("doc.mask", source=str(kaynak), target=str(hedef), rules={"profile_name": "Müşteriye"}, password_id=pid)
    assert out["encrypted"] is True
    doc = fitz.open(str(hedef))
    assert doc.needs_pass and doc.authenticate(PAROLA)
    doc.close()
    assert PAROLA not in raw_log() and "Muhasebe" not in raw_log()


def test_kaydederken_hatalar(tmp_path):
    call("vault.create", password=KASA)
    pid = call("vault.password_add", name="Muhasebe", value=PAROLA)["id"]
    kaynak = pdf(tmp_path / "belge.pdf")
    hedef = str(tmp_path / "c.pdf")
    kural = {"profile_name": "Müşteriye"}
    assert err("doc.mask", source=str(kaynak), target=hedef, rules=kural, password_id=pid, password=PAROLA) == "invalid_params"
    assert err("doc.mask", source=str(kaynak), target=hedef, rules=kural, password_id="yok") == "not_found"
    metin = tmp_path / "not.txt"
    metin.write_text("deneme\n", encoding="utf-8")
    assert err("doc.mask", source=str(metin), target=str(tmp_path / "n2.txt"), rules=kural, password_id=pid) == "invalid_params"
    call("vault.lock")
    assert err("doc.mask", source=str(kaynak), target=hedef, rules=kural, password_id=pid) == "vault_locked"


def test_ayar_degisiklikleri_gunluge_ad_ve_deger_yazmadan_girer():
    call("vault.create", password=KASA)
    pid = call("vault.password_add", name="Denetçi firma", value=PAROLA)["id"]
    call("vault.password_update", id=pid, name="Denetim")
    call("vault.password_reveal", id=pid)
    call("vault.password_delete", id=pid)
    kaynaklar = [json.loads(x)["source"] for x in raw_log().splitlines()]
    for ne in ("ekleme", "değiştirme", "görüntüleme", "silme"):
        assert any(k and ne in k and "kopya parola" in k for k in kaynaklar), ne
    ham = raw_log()
    assert PAROLA not in ham and "Denetçi" not in ham and "Denetim" not in ham and pid not in ham


def test_ajan_yolu_kayitli_parola_kullanamaz():
    """Karar: kayıtlı parolalar yalnızca arayüzden; ajan komutu ve MCP parolalı kopya üretmez."""
    kaynak = inspect.getsource(ajan)
    assert "password" not in kaynak
