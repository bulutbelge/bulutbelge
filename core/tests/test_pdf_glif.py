"""glif konumu ve boşluk sızıntısı denetiminin kapsam testleri.

Yanlış alarm (temiz belgede dosyanın durdurulması ya da gereksiz "kayma" uyarısı) ve kaçak
(kerning'li TJ dizisi, döndürülmüş, çok küçük ve harf harf yazılmış değer) durumları.
"""

from pathlib import Path

import pymupdf
import pytest

from bulutbelge_core.pdf import PdfError, _verify_glyph_gaps, mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()


def _text(path) -> str:
    doc = pymupdf.open(path)
    try:
        return "".join(p.get_text() for p in doc)
    finally:
        doc.close()


def _compact(s: str) -> str:
    return "".join(s.split())


def _tj_pdf(path: Path, value: str) -> None:
    """Değeri tek bir TJ dizisinde, rakamlar arasına kerning (sayısal aralık) koyarak yazar."""
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Baslik", fontsize=11)  # yazı tipini sayfa kaynaklarına ekler
    font = page.get_fonts()[0][4]
    parts = " ".join(f"({c}) -{40 + 15 * (i % 3)}" for i, c in enumerate(value))
    xref = page.get_contents()[0]
    stream = doc.xref_stream(xref) + f"\nBT /{font} 11 Tf 72 120 Td (TC: ) Tj [{parts}] TJ ET\n".encode()
    doc.update_stream(xref, stream)
    doc.save(path)
    doc.close()


def test_kerningli_tj_dizisindeki_deger_silinir(tmp_path):
    src = tmp_path / "tj.pdf"
    _tj_pdf(src, TC)
    assert TC in _compact(_text(src))  # metin katmanı değeri birleşik okuyor
    rules = Rules.from_dict(None)
    assert "tc_kimlik" in {f.finding.type for f in scan_pdf(src, rules).findings}
    out = mask_pdf(src, tmp_path / "tj_m.pdf", rules)
    assert TC not in _compact(_text(out.target))
    assert "Baslik" in _text(out.target)


def test_dondurulmus_ve_kucuk_yazili_deger_silinir(tmp_path):
    src = tmp_path / "don.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((300, 400), f"TC {TC}", fontsize=11, rotate=90)
    page.insert_text((72, 700), f"IBAN {IBAN}", fontsize=3)
    doc.save(src)
    doc.close()
    out = mask_pdf(src, tmp_path / "don_m.pdf", Rules.from_dict(None))
    metin = _compact(_text(out.target))
    assert TC not in metin
    assert _compact(IBAN) not in metin


def test_temiz_belgede_yanlis_alarm_yok(tmp_path):
    """Değerlere bitişik noktalama ve sağında devam eden yazı: dosya yazılır, kayma uyarısı çıkmaz."""
    src = tmp_path / "temiz.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    satirlar = [
        f"Sayin musteri ({TC}), basvurunuz alindi.",
        f"Odeme hesabi: {IBAN}; vade 30 gun.",
        "Telefon: 0532 123 45 67 - mesai saatlerinde.",
        "E-posta:ayse.yilmaz@ornek.com.tr,yanit 2 gun icinde.",
        "Bu satirda kisisel veri yok ve hic dokunulmamali.",
    ]
    for i, s in enumerate(satirlar):
        page.insert_text((72, 90 + i * 18), s, fontsize=11)
    doc.save(src)
    doc.close()
    out = mask_pdf(src, tmp_path / "temiz_m.pdf", Rules.from_dict(None))
    assert Path(out.target).exists() and out.masked >= 4
    assert not any("kaydı" in w or "kaydı" in w for w in out.warnings), out.warnings
    metin = _text(out.target)
    assert "Bu satirda kisisel veri yok ve hic dokunulmamali." in metin
    assert "basvurunuz" in metin and "mesai" in metin


def test_kisa_kalinti_dosyayi_durdurmaz_uc_karakter_durdurur(tmp_path):
    """Eşik: değerin 1-2 karakteri tek başına ele vermez (komşu rakam olabilir); 3+ karakter durdurur."""
    path = tmp_path / "k.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 92), TC[:2], fontsize=11)
    page.insert_text((72, 140), TC[:3], fontsize=11)
    doc.save(path)
    doc.close()
    assert _verify_glyph_gaps(str(path), [(0, pymupdf.Rect(60, 80, 200, 100))], {TC})  # yalnızca uyarı
    with pytest.raises(PdfError, match="glif"):
        _verify_glyph_gaps(str(path), [(0, pymupdf.Rect(60, 128, 200, 148))], {TC})


def test_kutu_disindaki_deger_parcasi_karistirilmaz(tmp_path):
    """Değerin aynısı kutunun dışında başka satırda geçiyorsa (ayrı bulgu) kutu denetimi alarm vermez."""
    path = tmp_path / "d.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 300), TC, fontsize=11)
    doc.save(path)
    doc.close()
    assert _verify_glyph_gaps(str(path), [(0, pymupdf.Rect(60, 80, 200, 100))], {TC}) == []
