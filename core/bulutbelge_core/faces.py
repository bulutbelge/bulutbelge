"""Fotoğraflarda ve taranmış sayfalarda yüz tespiti.

OpenCV'nin pakete gömülü yüz modeli (Haar kaskadı, önden yüz) kullanılır;
internet ya da ek model indirmesi gerekmez, görüntü bilgisayardan çıkmaz.

Yüz bölgesi diğer bulgular gibi gerçekten silinir (pikseller boşaltılır),
ardından seçilen yönteme göre bilgi taşımayan bulanık dolgu ya da siyah kutu
konur. Orijinal yüzü bulanıklaştırmak/pikselleştirmek yapılmaz: geri
çözülebilir (bkz. docs/kararlar/2026-11-04-bulanik-yontem.md).

Sınırlar: yandan ya da çok küçük yüzler kaçabilir, desenli alanlar yüz
sanılabilir. Bulgular orta güvenlidir; kullanıcı önizlemede onaylar ve
kaçanları "Alan seç" ile ekler.
"""

from __future__ import annotations

import pymupdf

# İşlenecek en uzun kenar (px): büyük fotoğraflar küçültülerek hızlanır.
_MAX_SIDE = 1600
# Yüz bölgesine eklenen pay (yüz boyutuna oranla): saç, kulak, çene de kapansın.
_PAD = 0.18
# En küçük yüz (kısa kenara oranla) ve kalabalık eşiği: küçük değerler yanlış bulguyu artırır.
_MIN_FACE = 0.035
_MIN_NEIGHBORS = 6

_cascade = None


def _detector():
    global _cascade
    if _cascade is None:
        import cv2  # ilk kullanımda yüklensin (motor hızlı açılsın)

        _cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        if _cascade.empty():
            raise RuntimeError("Yüz modeli yüklenemedi")
    return _cascade


def find_faces(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Sayfadaki yüzlerin kutuları (sayfa koordinatı, pt)."""
    import cv2
    import numpy as np

    rect = page.rect
    zoom = min(3.0, _MAX_SIDE / max(rect.width, rect.height))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csGRAY, alpha=False, annots=False)
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width)
    min_side = max(24, int(min(pix.width, pix.height) * _MIN_FACE))
    found = []
    # Kontrast eşitleme loş fotoğraflarda yüzü belirginleştirir ama çoğu beyaz belgede
    # yüzü siler; iki hâli de taranıp sonuçlar birleştirilir.
    for variant in (img, cv2.equalizeHist(img)):
        hits = _detector().detectMultiScale(
            variant, scaleFactor=1.1, minNeighbors=_MIN_NEIGHBORS, minSize=(min_side, min_side)
        )
        found.extend(hits if len(hits) else [])
    out = []
    for x, y, w, h in found:
        pad_w, pad_h = w * _PAD, h * _PAD * 1.4
        box = pymupdf.Rect(x - pad_w, y - pad_h, x + w + pad_w, y + h + pad_h * 0.8) / zoom
        out.append(box & rect)
    return _merge(out)


def _merge(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Çakışan kutuları birleştirir (aynı yüz iki kez bulunabiliyor)."""
    out: list[pymupdf.Rect] = []
    for r in sorted(rects, key=lambda r: (r.y0, r.x0)):
        for i, o in enumerate(out):
            if r.intersects(o):
                out[i] = o | r
                break
        else:
            out.append(r)
    return out


def face_remains(page: pymupdf.Page, region: pymupdf.Rect) -> bool:
    """Maskelemeden sonra bölgede hâlâ yüz bulunuyor mu (kaçak denetimi)."""
    for face in find_faces(page):
        overlap = face & region
        if not overlap.is_empty and overlap.get_area() > 0.4 * face.get_area():
            return True
    return False
