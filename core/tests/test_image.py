from pathlib import Path

import pymupdf
import pytest
from PIL import Image

from bulutbelge_core.ocr import ocr_available
from bulutbelge_core.pdf import mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

from fake_data import fake_tc

TC = fake_tc()


def _make_image(path: Path, lines: list[str], exif_gps: bool = False) -> None:
    doc = pymupdf.open()
    page = doc.new_page(width=500, height=40 + 30 * len(lines))
    for i, line in enumerate(lines):
        page.insert_text((20, 40 + i * 30), line, fontsize=18)
    pix = page.get_pixmap(dpi=144)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    exif = Image.Exif()
    if exif_gps:
        exif[0x8825] = {1: "N", 2: (41.0, 0.0, 0.0)}
        exif[0x0110] = "Sahte Kamera"
    img.save(path, exif=exif)


def test_image_manual_area_and_metadata(tmp_path):
    src = tmp_path / "foto.jpg"
    _make_image(src, ["Merhaba"], exif_gps=True)
    scan = scan_pdf(src, Rules.from_dict(None))
    assert scan.pages == 1
    assert any("konum (GPS)" in w for w in scan.warnings)

    result = mask_pdf(src, tmp_path / "out.jpg", Rules.from_dict(None), manual_areas=[(1, (0, 0, 200, 60))])
    out = Image.open(result.target)
    assert result.target.endswith(".jpg")
    assert out.size == Image.open(src).size
    assert not out.getexif()  # meta veri taşınmaz
    assert out.getpixel((40, 30))[0] < 30  # alan karartıldı


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_image_ocr_finds_and_masks(tmp_path):
    src = tmp_path / "kimlik.png"
    _make_image(src, [f"TC kimlik no: {TC}", "Telefon: 0532 123 45 67"])
    scan = scan_pdf(src, Rules.from_dict(None))
    types = {f.finding.type for f in scan.findings}
    assert {"tc_kimlik", "telefon"} <= types
    assert all(f.locatable for f in scan.findings)

    result = mask_pdf(src, tmp_path / "out.png", Rules.from_dict(None))
    assert result.masked == len(scan.findings)
    again = scan_pdf(result.target, Rules.from_dict(None))
    assert not {"tc_kimlik", "telefon"} & {f.finding.type for f in again.findings}


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_scanned_pdf_is_ocrd_and_masked(tmp_path):
    png = tmp_path / "tarama.png"
    _make_image(png, [f"TC kimlik no: {TC}"])
    src = tmp_path / "tarama.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(50, 50, 550, 130), filename=str(png))
    doc.save(src)
    doc.close()

    scan = scan_pdf(src, Rules.from_dict(None))
    assert scan.ocr_pages == [1]
    assert [f.finding.type for f in scan.findings] == ["tc_kimlik"]
    result = mask_pdf(src, tmp_path / "out.pdf", Rules.from_dict(None))
    assert not scan_pdf(result.target, Rules.from_dict(None)).findings


def _imza_formu(path: Path, yon: int) -> None:
    """Etiketin altında, etiketin başından başlayan el imzası; EXIF yönüyle döndürülmüş fotoğraf (TAKIP 1.74)."""
    import math

    from PIL import ImageDraw

    doc = pymupdf.open()
    page = doc.new_page(width=600, height=750)
    page.insert_text((40, 60), f"TC Kimlik No: {TC}", fontsize=16)
    page.insert_text((350, 575), "Teslim alan imza:", fontsize=14)
    pix = page.get_pixmap(dpi=144)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    d = ImageDraw.Draw(img)
    pts = [(760 + i * 3.2, 1200 + 30 * math.sin(i / 5)) for i in range(80)]
    d.line(pts, fill=(25, 40, 120), width=4, joint="curve")
    aci = {3: 180, 6: 90, 8: 270}[yon]
    exif = Image.Exif()
    exif[0x0112] = yon
    img.rotate(aci, expand=True).save(path, quality=92, exif=exif)


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
@pytest.mark.parametrize("yon", [3, 6, 8])
def test_exif_yonlu_fotografta_imza_tamamen_silinir(tmp_path, yon):
    from PIL import ImageOps

    src = tmp_path / f"form-{yon}.jpg"
    _imza_formu(src, yon)
    result = mask_pdf(src, tmp_path / "out.jpg", Rules.from_dict(None))
    assert result.masked >= 2  # TC ve imza
    out = ImageOps.exif_transpose(Image.open(result.target)).convert("RGB")
    # İmzanın lacivert mürekkebinden hiçbir piksel kalmamalı (yalnızca bir kısmı karartılmasın).
    lacivert = sum(1 for r, g, b in out.getdata() if b > 90 and b - r > 50 and b - g > 40)
    assert lacivert < 20, lacivert


def _renkli_imzali_gorsel(path: Path, renk: tuple[int, int, int]) -> None:
    import math

    from PIL import ImageDraw

    img = Image.new("RGB", (900, 700), "white")
    d = ImageDraw.Draw(img)
    d.line([(300 + i * 3.2, 520 + 30 * math.sin(i / 5)) for i in range(80)], fill=renk, width=5, joint="curve")
    img.save(path)


def test_gorselde_renkli_imza_etiketsiz_onerilir_ve_silinir(tmp_path):
    """OCR olsun olmasın: renkli imza lekesi önerilir (TAKIP 1.17); elle seçim yine çalışır."""
    src = tmp_path / "imza.png"
    _renkli_imzali_gorsel(src, (25, 40, 120))
    scan = scan_pdf(src, Rules.from_dict(None))
    imzalar = [f for f in scan.findings if f.finding.type == "imza"]
    assert imzalar and all(f.kind == "gorsel" for f in imzalar)

    result = mask_pdf(src, tmp_path / "out.png", Rules.from_dict(None))
    out = Image.open(result.target).convert("RGB")
    lacivert = sum(1 for r, g, b in out.getdata() if b > 90 and b - r > 50 and b - g > 40)
    assert lacivert < 20, lacivert

    # Elle seçim korunur: öneri kapalıyken de alan karartılır.
    kapali = Rules.from_dict({"types": {"imza": {"enabled": False}}})
    assert not [f for f in scan_pdf(src, kapali).findings if f.finding.type == "imza"]
    elle = mask_pdf(src, tmp_path / "elle.png", kapali, manual_areas=[(1, (0, 0, 300, 100))])
    assert Image.open(elle.target).getpixel((40, 30))[0] < 30


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_gorselde_sabit_kutu_degerden_genis_ve_komsu_metni_siler(tmp_path):
    src = tmp_path / "kimlik.png"
    _make_image(src, [f"TC: {TC}"])
    kurallar = Rules.from_dict({"types": {"tc_kimlik": {"method": "karartma"}}})

    def karanlik_genislik(yol: str) -> int:
        img = Image.open(yol).convert("L")
        satir = 75  # metin satırının ortası (144 dpi)
        xs = [x for x in range(img.width) if img.getpixel((x, satir)) < 30]
        return (max(xs) - min(xs) + 1) if xs else 0

    normal = mask_pdf(src, tmp_path / "n.png", kurallar)
    sabit = mask_pdf(src, tmp_path / "s.png", kurallar, fixed_box=True)
    assert karanlik_genislik(sabit.target) > karanlik_genislik(normal.target) > 0
