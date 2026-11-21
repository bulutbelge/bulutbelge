"""Görsel ve fotoğraf katmanında kişisel veri ve nesne tespiti (çevrimdışı OpenCV).

Bu modül harici ağ çağrısı ya da ağır model indirmesi yapmadan, yalnızca gömülü
OpenCV (`QRCodeDetector`, `BarcodeDetector`, HSV mürekkep segmentasyonu ve plaka
kaskadı) ile sayfadaki/fotoğraftaki şu görsel öğeleri bulur:

- QR kodlar ve 1D/2D barkodlar (`find_barcodes_qr`)
- Islak imza ve mavi/kırmızı kaşe/mühür bölgeleri (`find_visual_stamps`)
- Fotoğraflardaki araç plakaları (`find_visual_plates`)
"""

from __future__ import annotations

import pymupdf

_plate_cascade = None


def _load_plate_cascade():
    global _plate_cascade
    if _plate_cascade is None:
        import cv2

        path = cv2.data.haarcascades + "haarcascade_russian_plate_number.xml"
        clf = cv2.CascadeClassifier(path)
        _plate_cascade = False if clf.empty() else clf
    return _plate_cascade if _plate_cascade else None


def page_to_bgr(page: pymupdf.Page, max_side: int = 1800):
    """Sayfayı BGR OpenCV görüntüsüne ve kullanılan ölçek çarpanına (zoom) çevirir."""
    import cv2
    import numpy as np

    rect = page.rect
    longest = max(rect.width, rect.height, 1.0)
    zoom = min(3.0, max(1.0, max_side / longest))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, annots=False)
    rgb = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), zoom


def _quad_to_rect(quad, zoom: float, page_rect: pymupdf.Rect) -> pymupdf.Rect | None:
    xs = [float(p[0]) for p in quad]
    ys = [float(p[1]) for p in quad]
    x0, x1 = min(xs), max(xs)
    y0, y1 = min(ys), max(ys)
    if (x1 - x0) < 12 or (y1 - y0) < 12:
        return None
    r = pymupdf.Rect(x0 / zoom, y0 / zoom, x1 / zoom, y1 / zoom) & page_rect
    return r if not r.is_empty and r.width >= 6 and r.height >= 6 else None


def _merge_rects(items: list[tuple[pymupdf.Rect, str]]) -> list[tuple[pymupdf.Rect, str]]:
    out: list[tuple[pymupdf.Rect, str]] = []
    for r, label in sorted(items, key=lambda x: (x[0].y0, x[0].x0)):
        merged = False
        for i, (existing, elabel) in enumerate(out):
            inter = r & existing
            if not inter.is_empty and inter.get_area() > 0.35 * min(r.get_area(), existing.get_area()):
                out[i] = (existing | r, elabel)
                merged = True
                break
        if not merged:
            out.append((r, label))
    return out


def find_barcodes_qr(page: pymupdf.Page) -> list[tuple[pymupdf.Rect, str]]:
    """Sayfadaki QR kodları ve 1D barkodları bulur: `[(Rect, açıklama)]`."""
    import cv2

    bgr, zoom = page_to_bgr(page, max_side=1800)
    found: list[tuple[pymupdf.Rect, str]] = []

    qd = cv2.QRCodeDetector()
    try:
        ok, decoded, points, _ = qd.detectAndDecodeMulti(bgr)
    except cv2.error:
        ok, decoded, points = False, (), None
    if ok and points is not None:
        for i, quad in enumerate(points):
            r = _quad_to_rect(quad, zoom, page.rect)
            if r is None:
                continue
            ratio = r.width / max(r.height, 1e-3)
            if 0.6 <= ratio <= 1.65:
                info = decoded[i] if i < len(decoded) else ""
                found.append((r + (-2, -2, 2, 2), "QR kod (içerik okundu)" if info else "QR kod"))
    else:
        for multi_fn in (qd.detectMulti, qd.detect):
            try:
                ok_loc, loc_pts = multi_fn(bgr)
            except cv2.error:
                ok_loc, loc_pts = False, None
            if ok_loc and loc_pts is not None:
                for quad in loc_pts:
                    r = _quad_to_rect(quad, zoom, page.rect)
                    if r is None:
                        continue
                    ratio = r.width / max(r.height, 1e-3)
                    if 0.72 <= ratio <= 1.38 and r.get_area() >= 180:
                        found.append((r + (-2, -2, 2, 2), "QR kod"))
                if found:
                    break

    def _scan_barcode(mat, z: float) -> bool:
        hit = False
        try:
            bd = cv2.barcode.BarcodeDetector()
            b_ok, b_info, b_types, b_pts = bd.detectAndDecodeWithType(mat)
        except (AttributeError, cv2.error):
            bd = None
            b_ok, b_info, b_types, b_pts = False, (), (), None
        if b_ok and b_pts is not None:
            for i, quad in enumerate(b_pts):
                r = _quad_to_rect(quad, z, page.rect)
                if r is None:
                    continue
                code_type = b_types[i] if i < len(b_types) and b_types[i] else "Barkod"
                val = b_info[i] if i < len(b_info) else ""
                if val or r.width >= 20:
                    found.append((r + (-2, -2, 2, 2), f"Barkod ({code_type})" if code_type else "Barkod"))
                    hit = True
        elif bd is not None:
            try:
                bm_ok, bm_pts = bd.detectMulti(mat)
            except cv2.error:
                bm_ok, bm_pts = False, None
            if bm_ok and bm_pts is not None:
                for quad in bm_pts:
                    r = _quad_to_rect(quad, z, page.rect)
                    if r is not None and r.width >= 24 and r.height >= 12 and r.get_area() >= 300:
                        found.append((r + (-2, -2, 2, 2), "Barkod"))
                        hit = True
        return hit

    if not _scan_barcode(bgr, zoom) and zoom > 1.2:
        bgr_native, zoom_native = page_to_bgr(page, max_side=int(max(page.rect.width, page.rect.height, 1.0)))
        if zoom_native < zoom:
            _scan_barcode(bgr_native, zoom_native)

    return _merge_rects([(r & page.rect, lbl) for r, lbl in found if not (r & page.rect).is_empty])


def find_visual_stamps(
    page: pymupdf.Page, existing_rects: list[pymupdf.Rect] | None = None
) -> list[tuple[pymupdf.Rect, str]]:
    """Fotoğraf ve taranmış belgelerdeki renkli mühür/kaşe ve ıslak imza mürekkebini bulur.

    Yalnızca belirgin doygunluktaki (mavi/lacivert/kırmızı/mor) mürekkep konturlarını seçer;
    siyah-beyaz metin üzerinde yanlış pozitif üretmez.
    """
    import cv2
    import numpy as np

    bgr, zoom = page_to_bgr(page, max_side=1400)
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    h, w = bgr.shape[:2]
    page_area = float(h * w)

    # Mavi/lacivert/mor (H: 90..168) + Kırmızı/bordo (H: 0..12 veya 168..180), S >= 52
    blue_purple = cv2.inRange(hsv, np.array([90, 52, 20]), np.array([168, 255, 225]))
    red_low = cv2.inRange(hsv, np.array([0, 62, 25]), np.array([12, 255, 225]))
    red_high = cv2.inRange(hsv, np.array([168, 62, 25]), np.array([180, 255, 225]))
    mask = cv2.bitwise_or(blue_purple, cv2.bitwise_or(red_low, red_high))

    # Yakın harf/mürekkep çizgilerini tek kaşe/imza bloğunda birleştir.
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (9, 7))
    closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    occupied = existing_rects or []
    out: list[tuple[pymupdf.Rect, str]] = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < 24 or ch < 14:
            continue
        area = cw * ch
        if area > 0.25 * page_area or cw > 0.45 * w or ch > 0.35 * h:
            continue
        roi = mask[y : y + ch, x : x + cw]
        ink_ratio = float(np.count_nonzero(roi)) / float(area)
        if not (0.025 <= ink_ratio <= 0.72):
            continue
        rect = (pymupdf.Rect(x / zoom, y / zoom, (x + cw) / zoom, (y + ch) / zoom) + (-3, -3, 3, 3)) & page.rect
        if rect.is_empty:
            continue
        if any(
            not (rect & er).is_empty and (rect & er).get_area() > 0.45 * min(rect.get_area(), er.get_area())
            for er in occupied
        ):
            continue
        kind_label = "renkli kaşe/mühür" if 0.55 <= (cw / max(ch, 1)) <= 2.2 else "ıslak imza / kaşe"
        out.append((rect, kind_label))
    return _merge_rects(out)


def find_visual_plates(
    page: pymupdf.Page, exclude_rects: list[pymupdf.Rect] | None = None
) -> list[pymupdf.Rect]:
    """Fotoğraflardaki araç plakası bölgelerini görsel olarak tespit eder (OCR başarısız olsa da)."""
    clf = _load_plate_cascade()
    if clf is None:
        return []
    import cv2

    bgr, zoom = page_to_bgr(page, max_side=1600)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    # Metin ağırlıklı saf siyah-beyaz taramalarda tablo kutularını plaka sanmayı engelle:
    # Gerçek fotoğraflarda renk varyansı belirgindir.
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    if float(hsv[:, :, 1].mean()) < 8.0:
        return []

    hits = clf.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=8, minSize=(56, 16))
    occupied = exclude_rects or []
    out: list[tuple[pymupdf.Rect, str]] = []
    for x, y, w, h in hits if len(hits) else []:
        ratio = w / max(h, 1)
        if not (2.0 <= ratio <= 6.8):
            continue
        rect = pymupdf.Rect(x / zoom, y / zoom, (x + w) / zoom, (y + h) / zoom) & page.rect
        if rect.is_empty:
            continue
        if any(
            not (rect & er).is_empty and (rect & er).get_area() > 0.45 * rect.get_area()
            for er in occupied
        ):
            continue
        out.append((rect, "plaka"))
    return [r for r, _ in _merge_rects(out)]


def find_visual_mrz(
    page: pymupdf.Page, exclude_rects: list[pymupdf.Rect] | None = None
) -> list[tuple[pymupdf.Rect, str]]:
    """Kimlik/pasaport altındaki 2–3 satırlık MRZ (<<<) bölgesini görsel doku olarak bulur (OCR yedeği)."""
    import cv2
    import numpy as np

    bgr, zoom = page_to_bgr(page, max_side=1600)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    roi_y0 = int(h * 0.45)
    sub = gray[roi_y0:, :]
    if sub.shape[0] < 40 or w < 220:
        return []

    # BlackHat ile açık/hologram arka plan üzerindeki koyu monospace karakterleri çıkar
    bh_k = cv2.getStructuringElement(cv2.MORPH_RECT, (19, 7))
    blackhat = cv2.morphologyEx(sub, cv2.MORPH_BLACKHAT, bh_k)
    _, bw = cv2.threshold(blackhat, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
    horiz_k = cv2.getStructuringElement(cv2.MORPH_RECT, (max(12, w // 38), 3))
    band = cv2.dilate(bw, horiz_k, iterations=1)
    contours, _ = cv2.findContours(band, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    # Genişliği tam satıra yakın (≥ %45), boyu monospace satır aralığında aday satırları seç
    candidates: list[tuple[int, int, int, int]] = []
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        if cw < 0.45 * w or not (7 <= ch <= max(28, int(0.065 * h))):
            continue
        cell = bw[y : y + ch, x : x + cw]
        slices = 20
        sw = max(1, cw // slices)
        filled_slices = sum(1 for i in range(slices) if np.any(cell[:, i * sw : (i + 1) * sw]))
        ink = float(np.count_nonzero(cell)) / float(max(cw * ch, 1))
        if filled_slices >= 17 and 0.14 <= ink <= 0.72:
            candidates.append((x, y + roi_y0, cw, ch))

    if len(candidates) < 2:
        return []
    candidates.sort(key=lambda b: b[1])

    # Dikey olarak hizalı 2–3 satırlık MRZ gruplarını birleştir (x0 ve genişlik tutarlı olmalı)
    groups: list[list[tuple[int, int, int, int]]] = [[candidates[0]]]
    for box in candidates[1:]:
        prev = groups[-1][-1]
        gap = box[1] - (prev[1] + prev[3])
        if (
            0 <= gap <= max(26, int(2.6 * max(prev[3], box[3])))
            and abs(box[0] - prev[0]) <= 0.05 * w
            and abs(box[2] - prev[2]) <= 0.08 * w
        ):
            groups[-1].append(box)
        else:
            groups.append([box])

    occupied = exclude_rects or []
    out: list[tuple[pymupdf.Rect, str]] = []
    for grp in groups:
        if not (2 <= len(grp) <= 3):
            continue
        gx0 = min(b[0] for b in grp)
        gy0 = min(b[1] for b in grp)
        gx1 = max(b[0] + b[2] for b in grp)
        gy1 = max(b[1] + b[3] for b in grp)
        rect = (pymupdf.Rect(gx0 / zoom, gy0 / zoom, gx1 / zoom, gy1 / zoom) + (-4, -3, 4, 3)) & page.rect
        if rect.is_empty:
            continue
        if any(
            not (rect & er).is_empty and (rect & er).get_area() > 0.35 * min(rect.get_area(), er.get_area())
            for er in occupied
        ):
            continue
        out.append((rect, "MRZ bölgesi (görsel)"))
    return _merge_rects(out)
