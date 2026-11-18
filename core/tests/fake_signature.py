"""Sahte imza içeren test PDF'leri üretir: görsel imza, kalemle çizilmiş imza ve etiketsiz logo."""

import pymupdf


def squiggle_png(width: int = 160, height: int = 50) -> bytes:
    """El yazısı imzaya benzeyen dalgalı bir çizginin PNG'si."""
    doc = pymupdf.open()
    page = doc.new_page(width=width, height=height)
    shape = page.new_shape()
    for i in range(6):
        x = 10 + i * 22
        shape.draw_bezier((x, 35), (x + 8, 5), (x + 14, 45), (x + 22, 20))
    shape.finish(color=(0.1, 0.1, 0.5), width=2)
    shape.commit()
    png = page.get_pixmap(dpi=96, alpha=True).tobytes("png")
    doc.close()
    return png


def logo_png() -> bytes:
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 40, 40), False)
    pix.set_rect(pix.irect, (31, 95, 209))
    return pix.tobytes("png")


def draw_pen_signature(page: pymupdf.Page, x: float, y: float) -> None:
    shape = page.new_shape()
    for i in range(5):
        sx = x + i * 18
        shape.draw_bezier((sx, y + 20), (sx + 6, y), (sx + 12, y + 30), (sx + 18, y + 12))
    shape.finish(color=(0, 0, 0), width=1.2)
    shape.commit()


def make_signed_pdf(path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(480, 30, 520, 70), stream=logo_png())  # logo: etiket yok
    page.insert_text((72, 100), "Sözleşme (sahte veri)", fontsize=12)
    page.insert_text((72, 600), "Imza:", fontsize=11)
    page.insert_image(pymupdf.Rect(72, 610, 232, 660), stream=squiggle_png())
    page.insert_text((330, 600), "Onaylayan", fontsize=11)
    draw_pen_signature(page, 330, 615)
    doc.save(path)
    doc.close()
