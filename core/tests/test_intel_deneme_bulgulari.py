"""25 Kasım Intel Mac denemesi bulguları (sahte veriyle): başlık yazısı plaka sayılmaz, kaçak iletisi türü söyler,
ham metin çıktısında 1-2 karakterlik değerler kaydı engellemez."""
from __future__ import annotations

from pathlib import Path

import pymupdf
import pytest

from bulutbelge_core.detect import Finding
from bulutbelge_core.pdf import PdfError, PdfFinding, _yazi_plakalarini_ele
from bulutbelge_core.rules import kacak_iletisi
from bulutbelge_core.textdoc import _verify


def _plaka(rect: pymupdf.Rect) -> PdfFinding:
    return PdfFinding("p1:plaka:gorsel:0", 1, Finding("plaka", -1, -1, "", "orta", "görsel plaka"), [rect], "", "gorsel_kod")


def _kelime(rect: pymupdf.Rect, metin: str) -> tuple:
    return (rect.x0, rect.y0, rect.x1, rect.y1, metin, 0, 0, 0)


def test_rakamsiz_baslik_yazisi_gorsel_plaka_sayilmaz():
    bolge = pymupdf.Rect(30, 20, 160, 50)
    kelimeler = [_kelime(pymupdf.Rect(35, 25, 100, 45), "ÖRNEK"), _kelime(pymupdf.Rect(105, 25, 155, 45), "BİLİŞİM")]
    assert _yazi_plakalarini_ele([_plaka(bolge)], 0, kelimeler) == []


def test_rakamli_ya_da_okunamayan_plaka_korunur():
    bolge = pymupdf.Rect(30, 20, 160, 50)
    plaka_yazisi = [_kelime(pymupdf.Rect(35, 25, 155, 45), "34 ABC 123")]
    assert len(_yazi_plakalarini_ele([_plaka(bolge)], 0, plaka_yazisi)) == 1
    assert len(_yazi_plakalarini_ele([_plaka(bolge)], 0, [])) == 1  # bulanık plaka: OCR bir şey okuyamadı
    # Başka sayfanın kelimeleri bu sayfadaki bulguyu etkilemez
    assert len(_yazi_plakalarini_ele([_plaka(bolge)], 1, [_kelime(pymupdf.Rect(35, 25, 155, 45), "PERSONEL")])) == 1


def test_kacak_iletisi_tur_adlarini_verir_degeri_vermez():
    ileti = kacak_iletisi(["adres", "adres", "kisi_adi"])
    assert ileti == "Kaçak tespiti: maskelenmesi gereken 3 değer çıktıda hâlâ okunuyor (Adres, Kişi adı). Dosya yazılmadı."


class _Ic:
    def __init__(self, i: int, tur: str, deger: str, yerine: str = "[X]"):
        self.id = i
        self.finding = Finding(tur, 0, len(deger), deger, "yüksek")
        self.replacement = yerine


class _Tarama:
    fmt = "txt"

    def __init__(self, bulgular):
        self.findings = bulgular


def test_ham_metin_kacak_denetimi_kisa_degeri_saymaz_uzunu_turle_bildirir(tmp_path: Path):
    """Bina no "5" XML'in başka yerinde rastlantıyla geçer; kaydı engellememeli. Uzun değer kaçarsa tür yazılır."""
    bina = _Ic(1, "adres", "5")
    sokak = _Ic(2, "adres", "Bahariye Caddesi")
    _verify("<cbc:BuildingNumber>[X]</cbc:BuildingNumber><cbc:ID>5</cbc:ID>", _Tarama([bina]), [bina])
    with pytest.raises(PdfError, match=r"1 değer çıktıda hâlâ okunuyor \(Adres\)"):
        _verify("<a>[X]</a><b>Bahariye Caddesi</b>", _Tarama([bina, sokak]), [bina, sokak])
