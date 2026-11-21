"""Fotoğraflarda ve taranmış sayfalarda yüz tespiti (çevrimdışı çoklu model + profil/açı desteği).

Varsayılan olarak OpenCV'nin pakete gömülü Haar kaskadları birlikte kullanılır:
- Önden yüzler (`haarcascade_frontalface_default.xml` + `alt2.xml`)
- Yan profil yüzler (`haarcascade_profileface.xml`, sağ + sol ayna görüntüsü)
- Eğik/açılı başlar (±18° döndürme) ve loş çekimler (CLAHE + histogram eşitleme)
İsteğe bağlı olarak yerel bir YuNet ONNX dosyası (`BULUTBELGE_YUNET_MODEL` veya
`models/face_detection_yunet_2023mar.onnx`) konulursa internet bağlantısı olmadan
otomatik olarak birleştirilir.

Yüz bölgesi diğer bulgular gibi gerçekten silinir (pikseller boşaltılır),
ardından seçilen yönteme göre bilgi taşımayan bulanık dolgu ya da siyah kutu
konur (bkz. docs/kararlar/2026-11-04-bulanik-yontem.md).
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pymupdf

# İşlenecek en uzun kenar (px): hızlı çoklu tarama için dengeli boyut.
_MAX_SIDE = 960
_AUX_SIDE = 680
# Yüz bölgesine eklenen pay (yüz boyutuna oranla): saç, kulak, çene de kapansın.
_PAD = 0.18
# En küçük yüz (kısa kenara oranla) ve kalabalık eşiği.
_MIN_FACE = 0.035
_MIN_NEIGHBORS = 6

_models: dict[str, object] | None = None
_yunet = None
_yunet_checked = False


def _detectors() -> dict[str, object]:
    global _models
    if _models is None:
        import cv2  # ilk kullanımda yüklensin (motor hızlı açılsın)

        base = cv2.data.haarcascades
        frontal = cv2.CascadeClassifier(base + "haarcascade_frontalface_default.xml")
        if frontal.empty():
            raise RuntimeError("Yüz modeli yüklenemedi")
        loaded: dict[str, object] = {"frontal": frontal}
        for key, fname in (
            ("alt2", "haarcascade_frontalface_alt2.xml"),
            ("profile", "haarcascade_profileface.xml"),
        ):
            clf = cv2.CascadeClassifier(base + fname)
            if not clf.empty():
                loaded[key] = clf
        _models = loaded
    return _models


def _yunet_detector(w: int, h: int):
    """Varsa yerel YuNet ONNX yüz tespitçisini (internet yok) hazırlar."""
    global _yunet, _yunet_checked
    if not _yunet_checked:
        _yunet_checked = True
        import cv2

        candidates = [
            os.environ.get("BULUTBELGE_YUNET_MODEL", ""),
            str(Path(__file__).resolve().parent / "models" / "face_detection_yunet_2023mar.onnx"),
        ]
        model_path = next((p for p in candidates if p and Path(p).is_file()), None)
        if model_path and hasattr(cv2, "FaceDetectorYN"):
            try:
                _yunet = cv2.FaceDetectorYN.create(model_path, "", (max(w, 64), max(h, 64)), 0.72, 0.3, 50)
            except Exception:
                _yunet = None
    if _yunet is not None:
        _yunet.setInputSize((w, h))
    return _yunet


def _rotate_gray(gray, angle_deg: float):
    import cv2

    h, w = gray.shape[:2]
    cx, cy = w / 2.0, h / 2.0
    mat = cv2.getRotationMatrix2D((cx, cy), angle_deg, 1.0)
    rot = cv2.warpAffine(gray, mat, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    inv = cv2.invertAffineTransform(mat)
    return rot, inv


def _unrotate_box(x: int, y: int, bw: int, bh: int, inv) -> tuple[float, float, float, float]:
    import numpy as np

    corners = np.array([[x, y, 1.0], [x + bw, y, 1.0], [x, y + bh, 1.0], [x + bw, y + bh, 1.0]])
    mapped = corners @ inv.T
    xs, ys = mapped[:, 0], mapped[:, 1]
    return float(xs.min()), float(ys.min()), float(xs.max() - xs.min()), float(ys.max() - ys.min())


def _is_plausible_face(w: float, h: float, min_side: int) -> bool:
    if w < min_side * 0.85 or h < min_side * 0.85:
        return False
    ratio = w / max(h, 1.0)
    return 0.6 <= ratio <= 1.6


def find_faces(page: pymupdf.Page) -> list[pymupdf.Rect]:
    """Sayfadaki önden, yan profil ve eğik yüzlerin kutuları (sayfa koordinatı, pt)."""
    import cv2
    import numpy as np

    rect = page.rect
    zoom = min(3.0, _MAX_SIDE / max(rect.width, rect.height))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), colorspace=pymupdf.csRGB, alpha=False, annots=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    img = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    min_side = max(24, int(min(pix.width, pix.height) * _MIN_FACE))
    det = _detectors()
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(img)
    eq = cv2.equalizeHist(img)

    raw_boxes: list[tuple[float, float, float, float]] = []

    # 0. İsteğe bağlı yerel YuNet ONNX (en yüksek açı/ışık isabeti)
    yn = _yunet_detector(pix.width, pix.height)
    if yn is not None:
        try:
            _, yfaces = yn.detect(bgr)
            if yfaces is not None:
                for row in yfaces:
                    x, y, w, h, conf = float(row[0]), float(row[1]), float(row[2]), float(row[3]), float(row[-1])
                    if conf >= 0.72 and _is_plausible_face(w, h, min_side):
                        raw_boxes.append((x, y, w, h))
        except Exception:
            pass

    # 1. Önden yüzler (ham + CLAHE; alt2 yalnızca CLAHE'de çalışır)
    frontal = det["frontal"]
    alt2 = det.get("alt2")
    for variant in (img, clahe):
        hits = frontal.detectMultiScale(
            variant, scaleFactor=1.12, minNeighbors=_MIN_NEIGHBORS, minSize=(min_side, min_side)
        )
        for x, y, w, h in hits if len(hits) else []:
            if _is_plausible_face(w, h, min_side):
                raw_boxes.append((float(x), float(y), float(w), float(h)))

    # Yardımcı taramalar (alt2, yan profil, ±18° eğik baş) daha kompakt çözünürlükte hızlı koşar
    aux_scale = min(1.0, _AUX_SIDE / max(pix.width, pix.height))
    aux_gray = clahe if aux_scale >= 0.98 else cv2.resize(clahe, (max(1, int(pix.width * aux_scale)), max(1, int(pix.height * aux_scale))))
    aux_min = max(20, int(min_side * aux_scale))

    if alt2 is not None:
        hits = alt2.detectMultiScale(
            aux_gray, scaleFactor=1.14, minNeighbors=_MIN_NEIGHBORS + 1, minSize=(aux_min, aux_min)
        )
        for x, y, w, h in hits if len(hits) else []:
            fx, fy, fw, fh = x / aux_scale, y / aux_scale, w / aux_scale, h / aux_scale
            if _is_plausible_face(fw, fh, min_side):
                raw_boxes.append((fx, fy, fw, fh))

    # 2. Yan profil yüzler (sol bakan + sağ bakan ayna kopyası)
    profile = det.get("profile")
    if profile is not None:
        flipped = cv2.flip(aux_gray, 1)
        aux_w = aux_gray.shape[1]
        for source_mat, is_flipped in ((aux_gray, False), (flipped, True)):
            hits = profile.detectMultiScale(
                source_mat, scaleFactor=1.15, minNeighbors=_MIN_NEIGHBORS + 1, minSize=(aux_min, aux_min)
            )
            for x, y, w, h in hits if len(hits) else []:
                real_x = float(aux_w - x - w) if is_flipped else float(x)
                fx, fy, fw, fh = real_x / aux_scale, y / aux_scale, w / aux_scale, h / aux_scale
                if _is_plausible_face(fw, fh, min_side):
                    raw_boxes.append((fx, fy, fw, fh))

    # 3. Eğik/açılı başlar (±18° tarama, alt2 ile yüksek eşik)
    tilt_clf = alt2 or frontal
    for angle in (-18.0, 18.0):
        rot, inv = _rotate_gray(aux_gray, angle)
        hits = tilt_clf.detectMultiScale(
            rot, scaleFactor=1.16, minNeighbors=_MIN_NEIGHBORS + 2, minSize=(aux_min, aux_min)
        )
        for x, y, w, h in hits if len(hits) else []:
            ux, uy, uw, uh = _unrotate_box(int(x), int(y), int(w), int(h), inv)
            fx, fy, fw, fh = ux / aux_scale, uy / aux_scale, uw / aux_scale, uh / aux_scale
            if _is_plausible_face(fw, fh, min_side):
                # Döndürme AABB büyümesini hafif daralt (pay tekrar eklenecek)
                shrink = 1.0 - 0.15 * abs(math.sin(math.radians(angle)))
                cx, cy = fx + fw / 2.0, fy + fh / 2.0
                nw, nh = fw * shrink, fh * shrink
                raw_boxes.append((cx - nw / 2.0, cy - nh / 2.0, nw, nh))

    out = []
    for x, y, w, h in raw_boxes:
        pad_w, pad_h = w * _PAD, h * _PAD * 1.4
        box = pymupdf.Rect(x - pad_w, y - pad_h, x + w + pad_w, y + h + pad_h * 0.8) / zoom
        b = box & rect
        if not b.is_empty:
            out.append(b)
    return _merge(out)


def _merge(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Çakışan kutuları birleştirir (farklı açı/model aynı yüzü birden fazla bulabilir)."""
    out: list[pymupdf.Rect] = []
    for r in sorted(rects, key=lambda r: (r.y0, r.x0)):
        merged = False
        for i, o in enumerate(out):
            inter = r & o
            if not inter.is_empty and inter.get_area() > 0.2 * min(r.get_area(), o.get_area()):
                out[i] = o | r
                merged = True
                break
        if not merged:
            out.append(r)
    return out


def face_remains(page: pymupdf.Page, region: pymupdf.Rect) -> bool:
    """Maskelemeden sonra bölgede hâlâ yüz bulunuyor mu (kaçak denetimi)."""
    for face in find_faces(page):
        overlap = face & region
        if not overlap.is_empty and overlap.get_area() > 0.4 * face.get_area():
            return True
    return False
