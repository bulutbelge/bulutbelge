"""Office içindeki görsellerde yüz tespiti ve OCR. Yalnızca sahte değerler."""

import io
import zipfile
from pathlib import Path

import docx
import pytest
from PIL import Image, ImageDraw, ImageFont

from bulutbelge_core.faces import find_faces
from bulutbelge_core.ocr import ocr_available
from bulutbelge_core.rules import Rules
from bulutbelge_core.word import mask_word, scan_word

from fake_face import draw_face


def _png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def _docx_with_image(tmp_path: Path, img: Image.Image) -> Path:
    d = docx.Document()
    d.add_paragraph("Görselli belge (sahte veri)")
    d.add_picture(io.BytesIO(_png(img)))
    path = tmp_path / "gorselli.docx"
    d.save(path)
    return path


def _media(path: Path) -> list[Image.Image]:
    with zipfile.ZipFile(path) as z:
        return [Image.open(io.BytesIO(z.read(n))).convert("RGB") for n in z.namelist() if "/media/" in n]


def _card() -> Image.Image:
    card = Image.new("RGB", (1200, 700), (245, 245, 240))
    card.paste(draw_face(150).resize((300, 300)), (60, 160))
    return card


def _has_face(img: Image.Image) -> bool:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page(width=img.width, height=img.height)
    page.insert_image(page.rect, stream=_png(img))
    return bool(find_faces(page))


def test_face_in_docx_image_is_found_and_removed(tmp_path):
    src = _docx_with_image(tmp_path, _card())
    rules = Rules.from_dict(None)
    assert any("görsellerde 1 bulgu" in w for w in scan_word(src, rules).warnings)
    assert _has_face(_media(src)[0])

    target, n, warnings = mask_word(src, tmp_path / "out.docx", rules)
    assert n >= 1
    assert any("silindi" in w for w in warnings)
    assert not _has_face(_media(Path(target))[0])


def test_face_off_leaves_image_untouched(tmp_path):
    src = _docx_with_image(tmp_path, _card())
    rules = Rules.from_dict({"types": {"yuz": {"enabled": False, "method": "bulanik"}}})
    target, _n, _w = mask_word(src, tmp_path / "out.docx", rules)
    assert _has_face(_media(Path(target))[0])


def test_image_without_findings_keeps_original_bytes(tmp_path):
    src = _docx_with_image(tmp_path, Image.new("RGB", (400, 300), (250, 250, 250)))
    with zipfile.ZipFile(src) as z:
        before = {n: z.read(n) for n in z.namelist() if "/media/" in n}
    target, _n, _w = mask_word(src, tmp_path / "out.docx", Rules.from_dict(None))
    with zipfile.ZipFile(target) as z:
        assert {n: z.read(n) for n in z.namelist() if "/media/" in n} == before


@pytest.mark.skipif(not ocr_available(), reason="OCR dil dosyaları yok")
def test_text_in_docx_image_is_read_and_masked(tmp_path):
    from fake_data import fake_tc

    tc = fake_tc()
    img = Image.new("RGB", (1400, 300), "white")
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 64)
    except OSError:
        pytest.skip("yazı tipi yok")
    ImageDraw.Draw(img).text((40, 100), f"TC Kimlik No: {tc}", fill="black", font=font)
    src = _docx_with_image(tmp_path, img)
    rules = Rules.from_dict(None)
    assert any("görsellerde" in w and "bulgu" in w for w in scan_word(src, rules).warnings)
    target, n, _w = mask_word(src, tmp_path / "out.docx", rules)
    assert n >= 1
    import pymupdf

    out = _media(Path(target))[0]
    doc = pymupdf.open()
    page = doc.new_page(width=out.width, height=out.height)
    page.insert_image(page.rect, stream=_png(out))
    from bulutbelge_core.ocr import ocr_textpage

    assert tc not in page.get_text("text", textpage=ocr_textpage(page, True)).replace(" ", "")
