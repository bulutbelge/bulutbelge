"""Uzun tek satırlı girdide tespit süresi karesel büyümemeli (E.11 denemesinde bulundu).

Boşluksuz uzun bir dizide e-posta kalıbı her konumdan yeniden denendiği için 900 KB'lık tek satırlık metin
sunucu işçisini dakikalarca kilitliyordu (100 bin karakter 9 sn sürüyordu).

Mutlak süre makinenin yüküne bağlıdır (CI'da ya da meşgul bir bilgisayarda kat kat değişir); bu yüzden ölçeklenme
ölçülür: girdi 3 katına çıkınca süre doğrusalda ~3, karesel davranışta ~9 kat artar. Oran 6'nın altında olmalı.
Gürültüye karşı her ölçüm üç denemenin en kısasıdır.
"""

import time

import pytest

from bulutbelge_core.detect import detect
from bulutbelge_core.names import name_hints
from bulutbelge_core.rules import Rules

KUCUK = 20_000
BUYUK = 3 * KUCUK
DESENLER = {
    "harf": "x",
    "rakam": "1",
    "nokta-harf": "a.",
    "tire-rakam": "12-",
    "harf-rakam": "a1",
    "boslukla-sozcuk": "Ab ",
}


def _sure(desen: str, n: int) -> float:
    metin = "Telefon: 0532 111 22 33\n" + desen * (n // len(desen))
    rules = Rules.from_dict(None)
    en_kisa = float("inf")
    for _ in range(3):
        bas = time.perf_counter()
        bulgular = detect(metin, rules, name_hints(metin))
        en_kisa = min(en_kisa, time.perf_counter() - bas)
    assert any(b.type == "telefon" for b in bulgular)
    return en_kisa


@pytest.mark.parametrize("desen", list(DESENLER.values()), ids=list(DESENLER))
def test_uzun_satirda_tespit_dogrusal(desen):
    kucuk, buyuk = _sure(desen, KUCUK), _sure(desen, BUYUK)
    oran = buyuk / max(kucuk, 1e-3)
    assert oran < 6, f"girdi 3 kat büyüyünce süre {oran:.1f} kat arttı ({kucuk:.2f} sn → {buyuk:.2f} sn): karesel davranış"


def test_mrz_bulucu_uzun_satirda_dogrusal_ve_pasaport_satirlarini_bulur():
    """Kullanıcı geliştirmesinde (MRZ) rakamdan oluşan uzun satır 60 bin karakterde 28 sn sürüyordu (karesel)."""
    from bulutbelge_core.ids import find_mrz

    bas = time.perf_counter()
    assert list(find_mrz("x\n" + "1" * 300_000)) == []
    assert time.perf_counter() - bas < 1.0
    td3 = "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<\nL898902C36UTO7408122F1204159ZE184226B<<<<<10"
    (bas_, son_), = list(find_mrz(td3))
    assert td3[bas_:son_] == td3  # iki satır tek blok; "P<" ile başlayan ilk satır da kapsanır
