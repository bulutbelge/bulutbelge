"""Para birimi yazılmamış tablo tutarları (dekont/tahsilat): satırda yalnız tutar varsa bulunur."""

from bulutbelge_core.extra_types import amount_range, find_amounts

DEKONT = "Miktarı\n05\n1048\n939,70\n07\n2026\n44.468,17\nTOPLAM    3\n46.098,10\n24.11.2026\n"


def _vals(text):
    return [text[s:e] for s, e in find_amounts(text)]


def test_satirda_yalniz_duran_tutarlar_bulunur():
    assert _vals(DEKONT) == ["939,70", "44.468,17", "46.098,10"]


def test_tarih_kod_ve_satir_ici_sayi_tutar_sayilmaz():
    assert _vals("24.11.2026\n1048\n0003\nOran 18,00 olarak\n10/2026\n") == []


def test_para_birimli_tutar_tekrar_bulunmaz():
    assert _vals("12.345,67 TL\n") == ["12.345,67 TL"]


def test_birimsiz_tutar_birimsiz_araliga_cevrilir():
    assert amount_range("44.468,17") == "10.000-100.000"
    assert amount_range("1.250,00 TL") == "1.000-10.000 TL"
