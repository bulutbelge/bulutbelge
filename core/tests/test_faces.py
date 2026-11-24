from pathlib import Path

import pymupdf
from PIL import Image

from bulutbelge_core.pdf import mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

from fake_face import draw_face


def _photo(path: Path) -> Path:
    # Beyaz bir kartın solunda vesikalık, sağında yazı alanı.
    card = Image.new("RGB", (1200, 700), (245, 245, 240))
    card.paste(draw_face(150).resize((300, 300)), (60, 160))
    card.save(path)
    return path


def test_face_found_and_removed_in_photo(tmp_path):
    src = _photo(tmp_path / "kart.jpg")
    rules = Rules.from_dict(None)
    faces = [f for f in scan_pdf(src, rules).findings if f.finding.type == "yuz"]
    assert len(faces) == 1
    r = faces[0].rects[0]
    assert 40 < r.x0 < 200 and r.x1 < 420  # soldaki vesikalık

    out = mask_pdf(src, tmp_path / "out.jpg", rules)  # kaçak denetimi yüzü yeniden arar
    assert not [f for f in scan_pdf(out.target, rules).findings if f.finding.type == "yuz"]


def test_face_can_be_turned_off(tmp_path):
    src = _photo(tmp_path / "kart.png")
    rules = Rules.from_dict({"types": {"yuz": {"enabled": False, "method": "bulanik"}}})
    assert not [f for f in scan_pdf(src, rules).findings if f.finding.type == "yuz"]


def test_text_only_pdf_is_not_searched_for_faces(tmp_path):
    src = tmp_path / "metin.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Yalnızca metin", fontsize=12)
    doc.save(src)
    doc.close()
    assert not [f for f in scan_pdf(src, Rules.from_dict(None)).findings if f.finding.type == "yuz"]


def test_face_box_stays_inside_its_image_and_keeps_nearby_text(tmp_path):
    # Windows denemesi 6, D1: yüze sıkı kırpılmış fotoğraf metnin hemen altında; pay görselin
    # dışına taşınca üstteki cümlenin başı da siliniyordu.
    import io

    buf = io.BytesIO()
    draw_face(200).crop((90, 40, 310, 330)).save(buf, "PNG")
    src = tmp_path / "basvuru.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "SAHTE BASVURU FORMU", fontsize=14)
    page.insert_text((72, 95), "Bu belge tamamen sahtedir ve gercek kisi icermez.", fontsize=10)
    image_rect = pymupdf.Rect(72, 99, 182, 244)
    page.insert_image(image_rect, stream=buf.getvalue())
    doc.save(src)
    doc.close()

    rules = Rules.from_dict(None)
    faces = [f for f in scan_pdf(src, rules).findings if f.finding.type == "yuz"]
    assert len(faces) == 1
    assert image_rect.contains(faces[0].rects[0])

    out = mask_pdf(src, tmp_path / "out.pdf", rules)
    text = pymupdf.open(out.target)[0].get_text()
    assert "Bu belge tamamen sahtedir ve gercek kisi icermez." in text
    assert "SAHTE BASVURU FORMU" in text
