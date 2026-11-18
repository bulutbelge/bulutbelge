"""Varsayılan sütun başlığı sözlüğü (TAKIP 1.105). Tüm veriler sahtedir."""

from bulutbelge_core.paste import clean_text, scan_paste
from bulutbelge_core.rules import Rules, header_key


def test_sozluk_basliklari_turlere_eslenir():
    r = Rules.default()
    beklenen = {
        "Ad": "kisi_adi", "SOYADI": "kisi_adi", "Ad_Soyad": "kisi_adi", "Full-Name": "kisi_adi",
        "Telefon": "telefon", "GSM": "telefon", "E-Posta": "eposta", "e mail": "eposta",
        "T.C. Kimlik": "tc_kimlik", "TCKN": "tc_kimlik", "IBAN": "iban", "Address": "adres",
        "Doğum Tarihi": "dogum_tarihi", "dogum_tarihi": "dogum_tarihi", "Birth Date": "dogum_tarihi",
    }
    for baslik, tur in beklenen.items():
        assert r.column_type(baslik) == tur, baslik


def test_yanlis_pozitif_yok():
    r = Rules.default()
    for baslik in ("durum", "aktif", "adet", "adres_tipi", "telefon_tipi", "ad_soyad_notu"):
        assert r.column_type(baslik) is None, baslik


def test_takim_kurali_oncelikli_ve_kapatilabilir():
    r = Rules.from_dict({"column_rules": [{"header": "ad", "type": "adres"}]})
    assert r.column_type("Ad") == "adres" and r.column_type("Soyad") == "kisi_adi"
    kapali = Rules.from_dict({"varsayilan_sutun_sozlugu": False})
    assert kapali.column_type("Ad") is None and not kapali.column_rules
    assert header_key("Adı") == "adi"


def test_metin_csv_varsayilan_kuralla_tam_maskelenir():
    metin = "ad,soyad,email,durum\nZeynep,Örnekoğlu,sahte1@example.test,aktif\nKemal,Denemeli,sahte2@example.test,pasif\n"
    cikti = clean_text(metin, scan_paste(metin, Rules.from_dict(None)))
    for sahte in ("Zeynep", "Örnekoğlu", "Kemal", "Denemeli", "sahte1@example.test", "sahte2@example.test"):
        assert sahte not in cikti
    assert cikti.splitlines()[0] == "ad,soyad,email,durum"
    assert "aktif" in cikti and "pasif" in cikti
