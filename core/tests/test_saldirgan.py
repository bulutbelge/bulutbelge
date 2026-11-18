"""Saldırgan gözüyle test: maskeli çıktıda orijinal değerleri ve parçalarını arar (TAKIP 1.72).

Katmanlar: metin, ham bayt (UTF-8/UTF-16/Latin-1), zip parçaları, PDF akışları ve meta veri.
Aranan parçalar: tam değer, rakamlar (ayraçsız), son 4 hane, baş harfler/adın parçaları, biçim.
Yalnızca sahte değerler kullanılır. Bilinçli açık bırakılan parça (IBAN son 4) istisnadır.
"""

import io
import re
import zipfile
import zlib
from pathlib import Path

import docx
import pymupdf
import pytest

from bulutbelge_core.pdf import mask_pdf
from bulutbelge_core.rules import Rules
from bulutbelge_core.textdoc import mask_text_doc
from bulutbelge_core.word import mask_word

from fake_data import fake_iban, fake_tc

TC = fake_tc("234567890")
IBAN = fake_iban()
PHONE = "0532 987 65 43"
EMAIL = "zeynep.kaplan@example.com"
AD = "Zeynep Kaplan"

# Sert kurallar: son 4 hane açık kalan yöntem ve ad parçaları da saldırı konusu olmalı.
RULES = {"types": {
    "tc_kimlik": {"enabled": True, "method": "karartma"},
    "telefon": {"enabled": True, "method": "karartma"},
    "eposta": {"enabled": True, "method": "karartma"},
}}


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s)


# (ad, aranan parça, ne tür saldırı)
def _sirlar() -> list[tuple[str, str]]:
    out = [("tc", TC), ("tc-rakam-6", TC[:6]), ("tc-son4", TC[-4:]), ("tc-orta", TC[3:9]),
           ("telefon", PHONE), ("telefon-rakam", _digits(PHONE)), ("telefon-son4", _digits(PHONE)[-4:]),
           ("eposta", EMAIL), ("eposta-yerel", EMAIL.split("@")[0]), ("eposta-ad", "zeynep"),
           ("ad", AD), ("ad-soyad", "Kaplan"), ("ad-ilk", "Zeynep"),
           ("iban", IBAN), ("iban-ayraçsız", IBAN.replace(" ", "")),
           ("iban-orta", IBAN.replace(" ", "")[6:16])]
    return out


def _katmanlar(data: bytes) -> dict[str, bytes]:
    """Dosyayı saldırganın açabileceği her katmana ayırır (zip parçaları, PDF akışları)."""
    layers = {"ham": data}
    if zipfile.is_zipfile(io.BytesIO(data)):
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for n in z.namelist():
                layers[f"zip:{n}"] = z.read(n)
    if data.startswith(b"%PDF"):
        for i, m in enumerate(re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S)):
            try:
                layers[f"akis{i}"] = zlib.decompress(m.group(1))
            except zlib.error:
                pass
    return layers


def _kodlamalar(text: str) -> list[bytes]:
    return [text.encode("utf-8"), text.encode("utf-16-le"), text.encode("utf-16-be"),
            text.encode("latin-1", "ignore")]


def _kacaklar(data: bytes, extra_text: str, izinli: set[str]) -> list[str]:
    """Bulunan kaçakların yalnızca adını döner (değerin kendisini değil)."""
    bulunan = []
    layers = _katmanlar(data)
    layers["metin"] = extra_text.encode("utf-8")
    for ad, parca in _sirlar():
        if ad in izinli:
            continue
        for katman, icerik in layers.items():
            low = icerik.lower()
            aranan = [parca.encode("utf-8", "ignore").lower()] if katman.startswith("zip:") else []
            aranan += [b.lower() for b in _kodlamalar(parca)]
            if any(a and a in low for a in aranan):
                bulunan.append(f"{ad}@{katman}")
    # Biçim saldırısı: ayraçlı numara kalıpları çıktıda hâlâ var mı? (IBAN satırı hariç)
    satirlar = "\n".join(x for x in extra_text.splitlines() if "IBAN" not in x.upper())
    if re.search(r"(?<!\d)\d{11}(?!\d)", re.sub(r"[ .\-]", "", satirlar)):
        bulunan.append("bicim-11-hane@metin")
    if re.search(r"0?5\d{2}[ .\-]?\d{3}[ .\-]?\d{2}[ .\-]?\d{2}", satirlar):
        bulunan.append("bicim-telefon@metin")
    if re.search(r"[\w.]+@[\w.]+\.\w+", satirlar):
        bulunan.append("bicim-eposta@metin")
    return bulunan


# IBAN varsayılanı "son 4 açık"tır (tasarım); yalnızca bu parça sızıntı sayılmaz.
IZINLI = set()


def _iban_kontrol(extra_text: str) -> None:
    ham = IBAN.replace(" ", "")
    # Son 4 dışında kalan her 6+ haneli parça yok olmalı
    assert ham[:-4][-8:] not in extra_text.replace(" ", "")


def test_saldirgan_metin_dosyasi(tmp_path: Path):
    p = tmp_path / "not.txt"
    p.write_text(f"Ad: {AD}\nTC: {TC}\nTel: {PHONE}\nE-posta: {EMAIL}\nIBAN: {IBAN}\n", encoding="utf-8")
    rules = Rules.from_dict(RULES)
    target, masked, _ = mask_text_doc(p, tmp_path / "o.txt", rules)
    data = Path(target).read_bytes()
    text = data.decode("utf-8")
    assert masked >= 4
    kacak = _kacaklar(data, text, IZINLI | {"iban-son4", "ad", "ad-soyad", "ad-ilk", "eposta-ad"})
    kacak = [k for k in kacak if not k.startswith(("ad", "eposta-ad"))]
    assert kacak == [], f"kaçak: {kacak}"
    _iban_kontrol(text)


def test_saldirgan_word(tmp_path: Path):
    d = docx.Document()
    d.core_properties.author = AD
    d.core_properties.comments = f"TC {TC}"
    d.add_paragraph("TC kimlik no: ")
    d.paragraphs[0].add_run(TC[:5])
    d.paragraphs[0].add_run(TC[5:])
    d.add_paragraph(f"Tel: {PHONE}  E-posta: {EMAIL}")
    d.add_paragraph(f"IBAN: {IBAN}")
    src = tmp_path / "a.docx"
    d.save(src)
    target, masked, _ = mask_word(src, tmp_path / "o.docx", Rules.from_dict(RULES))
    data = Path(target).read_bytes()
    text = "\n".join(par.text for par in docx.Document(io.BytesIO(data)).paragraphs)
    assert masked >= 4
    kacak = _kacaklar(data, text, {"ad", "ad-soyad", "ad-ilk", "eposta-ad"})
    # Yazar adı meta veride temizlenmiş olmalı: ad parçaları da aranır.
    for k in ("Zeynep", "Kaplan"):
        for katman, icerik in _katmanlar(data).items():
            assert k.encode() not in icerik, f"ad kaçağı: {k}@{katman}"
    assert kacak == [], f"kaçak: {kacak}"
    _iban_kontrol(text)


def test_saldirgan_pdf(tmp_path: Path):
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate([f"Ad: {AD}", f"TC: {TC}", f"Tel: {PHONE}", f"E-posta: {EMAIL}", f"IBAN: {IBAN}"]):
        page.insert_text((72, 72 + i * 20), line, fontsize=11)
    doc.set_metadata({"author": AD, "title": f"Dosya {TC}", "subject": EMAIL})
    src = tmp_path / "a.pdf"
    doc.save(src)
    doc.close()
    res = mask_pdf(src, tmp_path / "o.pdf", Rules.from_dict(RULES))
    target, masked = res.target, res.masked
    data = Path(target).read_bytes()
    with pymupdf.open(target) as out:
        text = "\n".join(pg.get_text() for pg in out)
        meta = " ".join(str(v) for v in (out.metadata or {}).values())
    assert masked >= 4
    kacak = _kacaklar(data, text + "\n" + meta, {"ad", "ad-soyad", "ad-ilk", "eposta-ad"})
    assert kacak == [], f"kaçak: {kacak}"
    for k in ("Zeynep", "Kaplan"):
        assert k not in meta, "ad meta veride kaldı"
    _iban_kontrol(text)


def test_saldirgan_betigi_kacagi_yakalar():
    """Betiğin kendisi çalışıyor mu: bilerek sızdıran çıktıyı yakalamalı."""
    sizan = f"Kişi: Zeynep Kaplan, TC son hane {TC[-4:]}".encode()
    bulunan = _kacaklar(sizan, sizan.decode(), set())
    assert any(b.startswith("tc-son4") for b in bulunan)
    assert any(b.startswith("ad-ilk") for b in bulunan)
    temiz = b"Kisi: [AD], TC: [TC]"
    assert _kacaklar(temiz, temiz.decode(), set()) == []
