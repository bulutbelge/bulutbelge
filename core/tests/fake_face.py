"""Testler için çizilmiş (gerçek kişiye ait olmayan) yüz.

OpenCV'nin yüz modeli koyu göz bölgeleri, açık yanaklar ve burun sırtı gibi
ışık/gölge desenlerine bakar; bu çizim o desenleri taşır.
"""

from PIL import Image, ImageDraw, ImageFilter


def draw_face(size: int = 200, bg: int = 235) -> Image.Image:
    w = h = size * 2
    img = Image.new("L", (w, h), bg)
    d = ImageDraw.Draw(img)
    cx, cy = w // 2, h // 2
    fw, fh = size * 0.42, size * 0.55
    d.ellipse((cx - fw - 10, cy - fh - 30, cx + fw + 10, cy + fh * 0.2), fill=50)  # saç
    d.ellipse((cx - fw, cy - fh, cx + fw, cy + fh), fill=190)  # yüz
    ey = cy - fh * 0.18
    for sx in (-1, 1):
        ex = cx + sx * fw * 0.42
        d.ellipse((ex - fw * 0.22, ey - fh * 0.07, ex + fw * 0.22, ey + fh * 0.07), fill=70)  # göz
        d.rectangle((ex - fw * 0.28, ey - fh * 0.2, ex + fw * 0.25, ey - fh * 0.14), fill=80)  # kaş
    d.rectangle((cx - fw * 0.08, ey, cx + fw * 0.08, cy + fh * 0.2), fill=215)  # burun sırtı
    d.ellipse((cx - fw * 0.18, cy + fh * 0.15, cx + fw * 0.18, cy + fh * 0.27), fill=140)  # burun altı
    d.ellipse((cx - fw * 0.38, cy + fh * 0.42, cx + fw * 0.38, cy + fh * 0.56), fill=90)  # ağız
    return img.filter(ImageFilter.GaussianBlur(size / 40)).convert("RGB")
