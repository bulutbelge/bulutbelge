"""Metin ucunda ayraçlı tablo. Tüm veriler sahtedir."""

from bulutbelge_core.paste import clean_text, is_delimited_table, scan_paste
from bulutbelge_core.rules import Rules

RULES = {"column_rules": [
    {"header": "ad", "type": "kisi_adi"},
    {"header": "soyad", "type": "kisi_adi"},
    {"header": "email", "type": "eposta"},
]}


def _maskele(text: str) -> str:
    rules = Rules.from_dict(RULES)
    return clean_text(text, scan_paste(text, rules))


def test_csv_sutun_basligi_kurali_metinde_uygulanir():
    metin = "ad,soyad,email,not\nZeynep,Örnekoğlu,sahte1@example.test,x\nKemal,Denemeli,sahte2@example.test,y\n"
    cikti = _maskele(metin)
    for sahte in ("Zeynep", "Örnekoğlu", "Kemal", "Denemeli", "sahte1@example.test"):
        assert sahte not in cikti
    assert cikti.splitlines()[0] == "ad,soyad,email,not"
    assert [len(s.split(",")) for s in cikti.splitlines()] == [4, 4, 4]


def test_tsv_ayni_sekilde_islenir():
    metin = "ad\tsoyad\temail\nZeynep\tÖrnekoğlu\tsahte1@example.test\n"
    cikti = _maskele(metin)
    assert "Zeynep" not in cikti and "Örnekoğlu" not in cikti
    assert cikti.splitlines()[0] == "ad\tsoyad\temail" and cikti.count("\t") == 4


def test_tablo_algilama_temkinli():
    assert is_delimited_table("ad,soyad\nA,B\n")
    assert not is_delimited_table("ad,soyad\n")  # tek satır
    assert not is_delimited_table("Merhaba, nasılsınız\nİyiyim\n")  # tutarsız sütun
    assert not is_delimited_table("Sayın Zeynep Örnek, toplantı yarın.\nSaygılar, Kemal Deneme\n")  # düz metin


def test_duz_metin_davranisi_degismez():
    metin = "Merhaba, sahte1@example.test adresine yazın."
    assert "sahte1@example.test" not in _maskele(metin)
