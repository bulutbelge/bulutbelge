"""Bulgu 20: kaçak denetimi Türkçe büyük/küçük harf ve noktalama farkında da eşleşir. Tüm veriler sahtedir."""

import pytest

from bulutbelge_core.pdf import _normalize


@pytest.mark.parametrize(
    "a, b",
    [
        ("YILMAZ", "Yılmaz"),
        ("yilmaz", "Yılmaz"),
        ("İSTANBUL", "istanbul"),
        ("ŞİŞLİ", "şişli"),
        ("0532-000 (12) 34", "0532 000 12 34"),
        ("123.456.789.50", "12345678950"),
        ("ayse.yilmaz@example.com", "AYSE.YILMAZ@EXAMPLE.COM"),
    ],
)
def test_ayni_degerin_yazim_bicimleri_ayni_anahtara_iner(a, b):
    assert _normalize(a) == _normalize(b)


def test_buyuk_harfli_kopya_kacak_olarak_bulunur():
    """Bir değer maskelenmiş ama başka yerde BÜYÜK harfle kalmışsa denetim onu görür (eskiden kaçıyordu)."""
    cikti = "Sayın [AD SOYAD], ... İMZA: AYŞE YILMAZ"
    assert _normalize("Ayşe Yılmaz") in _normalize(cikti)


def test_farkli_degerler_karismaz():
    assert _normalize("Işık") != _normalize("Isak")
    assert _normalize("") == ""
