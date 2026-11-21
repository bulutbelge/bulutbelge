"""kart ve VKN için karışık yazım (noktalı, aralıklı, OCR harfi, satır bölünmesi) ve yanlış pozitif sınırları."""

import pytest

from bulutbelge_core.detect import detect
from bulutbelge_core.rules import Rules
from bulutbelge_core.validators import vkn_valid

from fake_data import fake_card

CARD = fake_card().replace(" ", "")
VKN = next(f"{i:010d}" for i in range(1234567000, 1234569999) if vkn_valid(f"{i:010d}"))


def _bul(metin: str) -> list[tuple[str, str]]:
    return [(f.type, f.value) for f in detect(metin, Rules.from_dict(None))]


def _ocr(s: str) -> str:
    """Yalnızca bir hanede OCR karışıklığı (0→O ya da 1→l)."""
    for a, b in (("0", "O"), ("1", "l")):
        i = s.find(a, 1)
        if i > 0:
            return s[:i] + b + s[i + 1 :]
    raise AssertionError("örnekte 0 ya da 1 yok")


@pytest.mark.parametrize(
    "deger",
    [
        f"{CARD[:4]}.{CARD[4:8]}.{CARD[8:12]}.{CARD[12:]}",
        f"{CARD[:4]} {CARD[4:8]} {_ocr(CARD[8:12])} {CARD[12:]}",
        f"{CARD[:4]}/{CARD[4:8]}/{CARD[8:12]}/{CARD[12:]}",
    ],
)
def test_kart_karisik_yazim(deger):
    assert ("kredi_karti", deger) in _bul(f"Kart: {deger} ile odendi")


def test_kart_satir_sonunda_bolunmus_etiketle_bulunur():
    metin = f"Kart numarasi: {CARD[:8]}\n{CARD[8:]}"
    assert any(t == "kredi_karti" for t, _ in _bul(metin))


def test_satira_bolunmus_sayi_etiketsiz_kart_sayilmaz():
    assert not any(t == "kredi_karti" for t, _ in _bul(f"Toplam {CARD[:8]}\n{CARD[8:]} adet"))


@pytest.mark.parametrize(
    "deger",
    [
        f"{VKN[:3]} {VKN[3:6]} {VKN[6:]}",
        f"{VKN[:3]}.{VKN[3:6]}.{VKN[6:]}",
        " ".join(VKN),
        f"{VKN[:3]} {VKN[3:6]} {_ocr(VKN[6:])}",
    ],
)
def test_vkn_karisik_yazim_etiketle(deger):
    assert ("vkn", deger) in _bul(f"Vergi No: {deger}")


def test_vkn_karisik_yazim_etiketsiz_alinmaz():
    """Kontrol hanesi zayıf: etiketsiz ayraçlı 10 hane VKN sayılmaz (düz yazılmışı asıl kalıp bulur)."""
    assert not any(t == "vkn" for t, _ in _bul(f"Firma {VKN[:3]} {VKN[3:6]} {VKN[6:]} ile"))
    assert ("vkn", VKN) in _bul(f"Firma {VKN} ile")


@pytest.mark.parametrize(
    "metin",
    ["Tel: 532 123 45 67", "Tarih 12.03.2024 10.30.15 kayit", "Fatura No: 123.456.789.012.345", "Siparis 1.234.567,89 TL"],
)
def test_yanlis_pozitif_yok(metin):
    turler = {t for t, _ in _bul(metin)}
    assert not turler & {"vkn", "kredi_karti"}, turler
