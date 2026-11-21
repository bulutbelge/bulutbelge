"""PDF'te imza ve kaşe bölgelerini bulma.

İmza çoğunlukla "İmza", "İmza/Kaşe", "Onaylayan" gibi bir etiketin yanında ya
da altında durur. Etiket olmadan her görsel (logo gibi) imza sanılabileceği için
yalnızca etiketin yakınındaki şunlar aday sayılır:

- görsel (taranıp eklenmiş imza ya da kaşe),
- çok sayıda eğri ya da kısa çizgiden oluşan çizim (kalem/tabletle atılmış imza).

Bulgular orta güvenlidir; kullanıcı listede onaylar. Elektronik imza alanları
ayrıca raporlanır: belge değiştiği için maskeleme sonrası geçersiz olurlar.
"""

from __future__ import annotations

from dataclasses import dataclass

import pymupdf
from PIL import ImageDraw, Image, ImageChops, ImageFilter

# Etikete göre arama alanı (pt): altında ve sağında bu kadar mesafe.
_BELOW = 140
_RIGHT = 260
_SIDE_MARGIN = 120
# Sayfanın büyük kısmını kaplayan görsel (taranmış sayfa, arka plan) imza değildir.
_MAX_PAGE_SHARE = 0.25
# Kalemle atılmış imza: en az bu kadar eğri ve toplamda bu kadar parça. Tablo
# çizgileri ve alt çizgi (____) eğri içermediği için elenir.
_MIN_CURVES = 3
_MIN_STROKES = 5


@dataclass
class SignatureRegion:
    rect: pymupdf.Rect
    kind: str  # "gorsel" | "cizim"
    label: str  # yakınında bulunduğu etiket metni
    image_digest: bytes | None = None
    image_xref: int = 0


def normalize_tr(s: str) -> str:
    """Türkçe büyük/küçük harf duyarsız karşılaştırma için."""
    return s.replace("İ", "i").replace("I", "ı").lower()


def _fold(s: str) -> str:
    # Belgeler Türkçe karakter olmadan da yazılır ("Imza", "Kase"): etiket eşleşmesinde
    # ı/i, ş/s gibi farkları yok say.
    return normalize_tr(s).translate(str.maketrans("ışğüöç", "isguoc"))


def find_labels(
    page: pymupdf.Page, labels: list[str], textpage: pymupdf.TextPage | None = None
) -> list[tuple[pymupdf.Rect, str]]:
    wanted = [_fold(lbl) for lbl in labels if lbl.strip()]
    found: list[tuple[pymupdf.Rect, str]] = []
    if not wanted:
        return found
    for x0, y0, x1, y1, word, *_ in page.get_text("words", textpage=textpage):
        w = _fold(word).strip(":.;,/()[]-")
        # "İmza/Kaşe" tek sözcük olarak gelebilir.
        parts = [p for p in w.replace("/", " ").split() if p]
        if any(any(p.startswith(lbl) for lbl in wanted) for p in parts):
            found.append((pymupdf.Rect(x0, y0, x1, y1), word))
    return found


def _search_zone(label: pymupdf.Rect, page_rect: pymupdf.Rect) -> pymupdf.Rect:
    zone = pymupdf.Rect(
        label.x0 - _SIDE_MARGIN,
        label.y0 - 20,
        max(label.x1 + _RIGHT, label.x0 + _SIDE_MARGIN * 2),
        label.y1 + _BELOW,
    )
    return zone & page_rect


def is_stroke_drawing(d: dict) -> bool:
    items = d.get("items") or []
    curves = sum(1 for it in items if it[0] == "c")
    short_lines = sum(
        1 for it in items if it[0] == "l" and abs(it[1] - it[2]) < 12
    )
    rect = pymupdf.Rect(d["rect"])
    return (
        curves >= _MIN_CURVES
        and len(items) >= _MIN_STROKES
        and rect.width < 320
        and rect.height < 180
        or short_lines >= _MIN_STROKES * 3  # tablette kısa düz parçalarla çizilmiş imza
        and rect.width < 320
        and rect.height < 180
    )


def find_signatures(page: pymupdf.Page, labels: list[str]) -> list[SignatureRegion]:
    label_rects = find_labels(page, labels)
    if not label_rects:
        return []

    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    regions: list[SignatureRegion] = []

    images = [
        info
        for info in page.get_image_info(hashes=True, xrefs=True)
        if pymupdf.Rect(info["bbox"]).get_area() < page_area * _MAX_PAGE_SHARE
    ]
    drawings = [d for d in page.get_drawings() if is_stroke_drawing(d)]

    for label_rect, label_text in label_rects:
        zone = _search_zone(label_rect, page_rect)

        for info in images:
            bbox = pymupdf.Rect(info["bbox"])
            if zone.contains(bbox.tl + (bbox.br - bbox.tl) * 0.5):
                regions.append(
                    SignatureRegion(bbox, "gorsel", label_text, info.get("digest"), info.get("xref", 0))
                )

        strokes = [pymupdf.Rect(d["rect"]) for d in drawings if zone.intersects(pymupdf.Rect(d["rect"]))]
        if strokes:
            union = pymupdf.Rect(strokes[0])
            for r in strokes[1:]:
                union |= r
            # Etiketin kendisini kapatma.
            if not union.intersects(label_rect):
                regions.append(SignatureRegion(union, "cizim", label_text))

    return _dedupe(regions)


def _dedupe(regions: list[SignatureRegion]) -> list[SignatureRegion]:
    kept: list[SignatureRegion] = []
    for r in sorted(regions, key=lambda r: -r.rect.get_area()):
        if any((r.rect & k.rect).get_area() > 0.6 * r.rect.get_area() for k in kept):
            continue
        kept.append(r)
    return sorted(kept, key=lambda r: (r.rect.y0, r.rect.x0))


def has_digital_signature(doc: pymupdf.Document) -> bool:
    for page in doc:
        for w in page.widgets() or []:
            if w.field_type == pymupdf.PDF_WIDGET_TYPE_SIGNATURE:
                return True
    return False


def _ink_rect_in_zone(
    page: pymupdf.Page, zone: pymupdf.Rect, label_h: float, exclude: pymupdf.Rect | None = None, pad: bool = True
) -> pymupdf.Rect | None:
    """Etiketin yanındaki/altındaki bölgede mürekkep izlerini yerel kontrastla bulur.

    `exclude`: sayılmayacak bölge (etiketin kendi yazısı). `pad`: bulunan kutuya pay eklensin mi.
    """
    if zone.is_empty or zone.width < 12 or zone.height < 8:
        return None
    scale = min(2.0, max(1.0, 420.0 / max(zone.width, 1.0)))
    pix = page.get_pixmap(clip=zone, matrix=pymupdf.Matrix(scale, scale), alpha=False)
    if pix.width < 8 or pix.height < 6:
        return None
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    radius = max(4, int(label_h * scale * 0.45))
    diff = ImageChops.subtract(im.filter(ImageFilter.BoxBlur(radius)), im)
    bw = diff.point(lambda p: 255 if p > 20 else 0)
    if exclude is not None:
        ex = (exclude + (-2, -2, 2, 2)) & zone
        if not ex.is_empty:
            ImageDraw.Draw(bw).rectangle(
                [(ex.x0 - zone.x0) * scale, (ex.y0 - zone.y0) * scale, (ex.x1 - zone.x0) * scale, (ex.y1 - zone.y0) * scale],
                fill=0,
            )
    bbox = bw.getbbox()
    if not bbox:
        return None
    bx0, by0, bx1, by1 = bbox
    if (bx1 - bx0) < 8 or (by1 - by0) < 4:
        return None
    pad_x = max(8.0, label_h * 0.45) if pad else 0.0
    pad_y = max(8.0, label_h * 0.45) if pad else 0.0
    rect = pymupdf.Rect(
        zone.x0 + bx0 / scale - pad_x,
        zone.y0 + by0 / scale - pad_y,
        zone.x0 + bx1 / scale + pad_x,
        zone.y0 + by1 / scale + pad_y,
    )
    return rect & page.rect


def _grow_ink(
    page: pymupdf.Page, ink: pymupdf.Rect, label: pymupdf.Rect, h: float, yazilar: list[pymupdf.Rect] | None = None
) -> pymupdf.Rect:
    """Etiketin yanındaki/altındaki imzayı bütün çizgileriyle kapsayan kutu.

    Etiket çevresindeki geniş bölgede (en çok ~14 x 6 satır) mürekkep izleri çıkarılır, küçük
    boşluklar kapatılır ve bağlı bileşenlere ayrılır. Etikete yakın başlayan (en çok ~2,5 satır)
    bileşenler imzadır; kâğıt kenarı gibi uzakta duran çizgiler alınmaz. Etiketin yazısı sayılmaz,
    kutu etiketin üstüne taşmaz. Hiç bileşen bulunmazsa ilk bulunan iz (`ink`) kullanılır.
    """
    # Sola da geniş bakılır: OCR çoğu zaman etiketin yalnızca son kelimesini ("imza:") verir, imza
    # ise "Teslim alan imza:" yazısının başından başlayabilir.
    limit = pymupdf.Rect(label.x0 - h * 8, label.y0 - h * 1.5, label.x1 + h * 14, label.y1 + h * 6) & page.rect
    pad = max(8.0, h * 0.45)
    yedek = (ink + (-pad, -pad, pad, pad)) & page.rect
    if limit.is_empty or limit.width < 12 or limit.height < 8:
        return yedek
    scale = min(2.0, max(0.5, 700.0 / max(limit.width, 1.0)))
    pix = page.get_pixmap(clip=limit, matrix=pymupdf.Matrix(scale, scale), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    radius = max(4, int(h * scale * 0.45))
    bw = ImageChops.subtract(im.filter(ImageFilter.BoxBlur(radius)), im).point(lambda p: 255 if p > 20 else 0)

    def px(r: pymupdf.Rect) -> tuple[int, int, int, int]:
        return (
            max(0, int((r.x0 - limit.x0) * scale)),
            max(0, int((r.y0 - limit.y0) * scale)),
            min(pix.width, int((r.x1 - limit.x0) * scale) + 1),
            min(pix.height, int((r.y1 - limit.y0) * scale) + 1),
        )

    # Etiket ve aynı satırdaki kelimeler ("Teslim alan imza:") imza sayılmaz, karartılmaz.
    ciz = ImageDraw.Draw(bw)
    for r in [label, *(yazilar or [])]:
        if r.intersects(limit):
            ciz.rectangle(px(r), fill=0)
    # Çizgideki kopukluklar (ve etiket kutusunun kestiği yerler) birleşsin diye izler kalınlaştırılır.
    kal = max(3, int(h * scale * 0.5)) | 1
    bag = bw.filter(ImageFilter.MaxFilter(kal))
    w, hh = bag.size
    veri = bag.tobytes()
    gorulen = bytearray(w * hh)
    yakin = label + (-h * 2.5, -h * 2.5, h * 2.5, h * 2.5)
    en_kucuk = max(4, int((h * scale * 0.6) ** 2))  # yazı kırıntısı ve gürültü sayılmasın
    secilen: pymupdf.Rect | None = None
    k = kal / 2
    for bas_i in range(w * hh):
        if not veri[bas_i] or gorulen[bas_i]:
            continue
        gorulen[bas_i] = 1
        kuyruk = [bas_i]
        bx0, by0, bx1, by1, adet = w, hh, -1, -1, 0
        while kuyruk:
            i = kuyruk.pop()
            adet += 1
            y, x = divmod(i, w)
            if x < bx0:
                bx0 = x
            if x > bx1:
                bx1 = x
            if y < by0:
                by0 = y
            if y > by1:
                by1 = y
            for j in (i - w - 1, i - w, i - w + 1, i - 1, i + 1, i + w - 1, i + w, i + w + 1):
                if 0 <= j < w * hh and veri[j] and not gorulen[j] and abs(j % w - x) <= 1:
                    gorulen[j] = 1
                    kuyruk.append(j)
        if adet < en_kucuk:
            continue
        # Arama bölgesini baştan sona kesen çizgi (kâğıt kenarı, tablo çizgisi) imza değildir.
        if (by0 <= 1 and by1 >= hh - 2) or (bx0 <= 1 and bx1 >= w - 2):
            continue
        r = pymupdf.Rect(
            limit.x0 + (bx0 + k) / scale, limit.y0 + (by0 + k) / scale, limit.x0 + (bx1 - k) / scale, limit.y0 + (by1 - k) / scale
        )
        if r.intersects(yakin) and r.intersects(ink + (-h, -h, h, h)):
            secilen = r if secilen is None else secilen | r
    if secilen is None:
        return yedek
    rect = (secilen + (-pad, -pad, pad, pad)) & page.rect
    satir = pymupdf.Rect(label)
    for r in yazilar or []:
        satir |= r
    if rect.intersects(satir):
        label = satir
        # Kutu etiketin yazısını örtmesin: imza etiketin altındaysa üstten, sağındaysa soldan kırp.
        if secilen.y0 >= label.y1 - h * 0.6:
            rect.y0 = max(rect.y0, label.y1 + 1)
        elif secilen.x0 >= label.x1 - h * 0.6:
            rect.x0 = max(rect.x0, label.x1 + 1)
    return rect


def _satir_kelimeleri(page: pymupdf.Page, textpage: pymupdf.TextPage, label: pymupdf.Rect, h: float) -> list[pymupdf.Rect]:
    """Etiketle aynı satırda, etiketin solunda kalan OCR kelimelerinin ("Teslim alan") ve etiketin kutuları."""
    out = []
    for w in page.get_text("words", textpage=textpage):
        r = pymupdf.Rect(w[:4])
        ortak = min(r.y1, label.y1) - max(r.y0, label.y0)
        # Yalnızca etiketin solundaki ve kendisi: sağdaki "kelime" çoğu zaman OCR'ın imzayı okuma denemesidir.
        if ortak > 0.5 * min(r.height, label.height) and r.x1 >= label.x0 - h * 10 and r.x1 <= label.x1 + h * 0.5:
            out.append(r)
    return out


def find_ocr_signatures(
    page: pymupdf.Page, textpage: pymupdf.TextPage, labels: list[str]
) -> list[SignatureRegion]:
    """Fotoğraf ve taranmış sayfalarda OCR ile bulunan imza etiketinin yanındaki/altındaki imzayı bulur."""
    label_rects = find_labels(page, labels, textpage=textpage)
    if not label_rects:
        return []
    regions: list[SignatureRegion] = []
    for lr, label_text in label_rects:
        # Eğik fotoğrafta OCR kutusu yazıdan çok daha yüksek çıkar; satır yüksekliği harf genişliğinden
        # de tahmin edilir ve küçüğü alınır (bölgeler gereksiz büyüyüp kâğıt kenarını yakalamasın).
        harf = len(label_text.strip()) or 1
        h = max(min(lr.height, 1.6 * lr.width / harf), 12.0)
        right_zone = (
            pymupdf.Rect(lr.x1 + h * 0.12, lr.y0 - h * 0.75, lr.x1 + h * 4.8, lr.y1 + h * 1.9) & page.rect
        )
        below_zone = (
            pymupdf.Rect(lr.x0 - h * 0.5, lr.y1 + h * 0.12, lr.x0 + h * 4.8, lr.y1 + h * 2.8) & page.rect
        )
        # İmza etiketin sağında, altında ya da ikisine taşan biçimde olabilir: ikisi de aranır, sonra
        # bulunan iz bütün imzayı kapsayana dek büyütülür (yalnızca bölgeye düşen parça karartılmasın).
        found = [r for r in (_ink_rect_in_zone(page, z, h, exclude=lr, pad=False) for z in (right_zone, below_zone)) if r]
        sig_rect = None
        if found:
            ink = pymupdf.Rect(found[0])
            for r in found[1:]:
                ink |= r
            sig_rect = _grow_ink(page, ink, lr, h, _satir_kelimeleri(page, textpage, lr, h))
        if sig_rect is not None and not sig_rect.is_empty:
            regions.append(SignatureRegion(sig_rect, "gorsel", label_text))
    return _dedupe(regions)


# --- Etiketsiz imza ve kaşe: mürekkep rengi ve şekil sezgisi, temkinli eşikler ---
_ETIKETSIZ_EN_AZ_EGRI = 6  # etiketli aramadan (3) sıkı: yanlış pozitif pahalı
_MURUKKEP_DOLULUK = (0.02, 0.40)  # mürekkep pikselinin kutuya oranı: düz dolgu (logo) ve boş görsel elenir
_MURUKKEP_RENK_PAYI = 0.8  # mürekkep piksellerinin bu kadarı kalem/kaşe rengi (mavi, mor, kırmızı, koyu) olmalı
_TARAMA_RENK_FARKI = 70  # kaşe mürekkebi: kanallar arası fark bu eşikten büyük (soluk renk sayılmaz)
_TARAMA_EN_BOYUT = (24.0, 220.0)  # kaşe/imza lekesinin pt cinsinden kenar sınırı
_TARAMA_EN_FAZLA_RENK = 0.04  # sayfanın bundan fazlası renkliyse (fotoğraf, renkli belge) aranmaz
_YAZI_ORTUSME = 0.15  # leke yazının bu kadarından fazlasını örtüyorsa yazıdır, imza değil


def _kalem_rengi(r: int, g: int, b: int) -> bool:
    """Mavi/mor (tükenmez kalem), kırmızı (kaşe) ya da koyu (siyah kalem) mürekkep mi?"""
    if max(r, g, b) < 90:
        return True
    return (b > r + 25 and b > g + 25) or (r > g + 60 and r > b + 40) or (r > g + 40 and b > g + 40)


def image_looks_like_ink(png_or_pix: pymupdf.Pixmap) -> bool:
    """Görsel el imzası/kaşe gibi mi: seyrek, kalem renginde izler; düz dolgu logo değil."""
    pix = png_or_pix
    if pix.width < 8 or pix.height < 8:
        return False
    if pix.alpha:
        rgba = Image.frombytes("RGBA", (pix.width, pix.height), pix.samples)
        alpha = rgba.getchannel("A")
        rgb = rgba.convert("RGB")
    else:
        rgb = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        alpha = None
    rgb.thumbnail((160, 160))
    if alpha is not None:
        alpha = alpha.resize(rgb.size)
    px = rgb.load()
    ap = alpha.load() if alpha is not None else None
    ink = pen = 0
    for y in range(rgb.height):
        for x in range(rgb.width):
            r, g, b = px[x, y]
            if ap is not None and ap[x, y] < 64:
                continue
            if min(r, g, b) > 200:  # kâğıt/boşluk
                continue
            ink += 1
            pen += _kalem_rengi(r, g, b)
    total = rgb.width * rgb.height
    if not ink or not (_MURUKKEP_DOLULUK[0] <= ink / total <= _MURUKKEP_DOLULUK[1]):
        return False
    return pen / ink >= _MURUKKEP_RENK_PAYI


def find_unlabeled_signatures(
    page: pymupdf.Page, known: list[pymupdf.Rect], text_rects: list[pymupdf.Rect]
) -> list[SignatureRegion]:
    """Etiketi olmayan imza: sayfanın alt kısmındaki seyrek mürekkepli görsel ve yoğun kalem çizimi.

    Logo (düz dolgu ya da üst bölge), tablo çizgisi ve yazıyla örtüşen çizimler aday olmaz.
    `known`: etiket yakınında zaten bulunan bölgeler (yinelenmez).
    """
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    regions: list[SignatureRegion] = []

    def aday_mi(r: pymupdf.Rect) -> bool:
        if r.width < 30 or r.height < 12 or r.get_area() >= page_area * _MAX_PAGE_SHARE:
            return False
        if r.y0 + r.height / 2 < page_rect.y0 + page_rect.height * 0.4:
            return False  # sayfa başı: antet, logo
        if any((r & k).get_area() > 0.3 * r.get_area() for k in known):
            return False
        return not any((r & t).get_area() > _YAZI_ORTUSME * r.get_area() for t in text_rects)

    for info in page.get_image_info(hashes=True, xrefs=True):
        bbox = pymupdf.Rect(info["bbox"])
        xref = info.get("xref", 0)
        if not xref or not aday_mi(bbox):
            continue
        try:
            pix = pymupdf.Pixmap(page.parent, xref)
            if pix.alpha:
                pix = pymupdf.Pixmap(pix, 0)  # gömülü alfa atılır; saydamlık smask'tan gelir
            if pix.colorspace is None or pix.colorspace.n != 3:
                pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
            smask = page.parent.extract_image(xref).get("smask")
            if smask:
                pix = pymupdf.Pixmap(pix, pymupdf.Pixmap(page.parent, smask))
        except (RuntimeError, ValueError):
            continue
        if image_looks_like_ink(pix):
            regions.append(SignatureRegion(bbox, "gorsel", "", info.get("digest"), xref))

    # Yoğun eğri kümeleri: yakın çizimler tek imza sayılır.
    parcalar: list[tuple[pymupdf.Rect, int]] = []
    for d in page.get_drawings():
        egri = sum(1 for it in d.get("items") or [] if it[0] == "c")
        r = pymupdf.Rect(d["rect"])
        if egri and r.width < 320 and r.height < 180:
            parcalar.append((r, egri))
    kumeler: list[list] = []
    for r, egri in parcalar:
        for k in kumeler:
            if (k[0] + (-10, -10, 10, 10)).intersects(r):
                k[0] |= r
                k[1] += egri
                break
        else:
            kumeler.append([pymupdf.Rect(r), egri])
    for r, egri in kumeler:
        if egri >= _ETIKETSIZ_EN_AZ_EGRI and aday_mi(r):
            regions.append(SignatureRegion(r, "cizim", ""))
    return _dedupe(regions)


def find_scanned_stamps(
    page: pymupdf.Page, known: list[pymupdf.Rect], text_rects: list[pymupdf.Rect]
) -> list[SignatureRegion]:
    """Taranmış sayfa ya da fotoğraftaki renkli (mavi/mor/kırmızı) kaşe ve imza lekeleri.

    Yalnızca belirgin renkli mürekkep aranır; siyah imza ile yazı ayırt edilemediği için etiketsiz
    aranmaz. Renkli bölgesi geniş sayfalar (fotoğraf, renkli belge) ve yazıyla örtüşen lekeler elenir.
    """
    page_rect = page.rect
    scale = min(1.5, 700.0 / max(page_rect.width, 1.0))
    pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    r, g, b = im.split()
    farki = ImageChops.subtract(ImageChops.lighter(ImageChops.lighter(r, g), b), ImageChops.darker(ImageChops.darker(r, g), b))
    renkli = farki.point(lambda v: 255 if v > _TARAMA_RENK_FARKI else 0)
    if not renkli.getbbox():
        return []
    if sum(1 for v in renkli.getdata() if v) > _TARAMA_EN_FAZLA_RENK * pix.width * pix.height:
        return []
    # Kaşenin halkası ve harfleri tek leke olsun diye kapat; kâğıt kenarı gibi ince şeritler budansın.
    k = max(5, int(10 * scale))
    kapali = renkli.filter(ImageFilter.MaxFilter(k | 1))
    # Bağlı bileşenler: küçük bir akış doldurma (piksel sayısı sınırlı, görüntü küçük).
    w, h = kapali.size
    data = kapali.load()
    gorulen = bytearray(w * h)
    lekeler: list[pymupdf.Rect] = []
    for sy in range(h):
        for sx in range(w):
            if not data[sx, sy] or gorulen[sy * w + sx]:
                continue
            yigin = [(sx, sy)]
            gorulen[sy * w + sx] = 1
            x0 = x1 = sx
            y0 = y1 = sy
            while yigin:
                x, y = yigin.pop()
                x0, x1, y0, y1 = min(x0, x), max(x1, x), min(y0, y), max(y1, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and data[nx, ny] and not gorulen[ny * w + nx]:
                        gorulen[ny * w + nx] = 1
                        yigin.append((nx, ny))
            pad = k / 2
            lekeler.append(
                pymupdf.Rect(
                    page_rect.x0 + (x0 + pad) / scale,
                    page_rect.y0 + (y0 + pad) / scale,
                    page_rect.x0 + (x1 - pad) / scale,
                    page_rect.y0 + (y1 - pad) / scale,
                )
            )
    out: list[SignatureRegion] = []
    # Fotoğrafta 1 piksel = 1 pt olduğundan sınırlar A4'ten (595 pt) geniş sayfalarda büyütülür.
    olcek = max(1.0, page_rect.width / 595.0)
    lo, hi = _TARAMA_EN_BOYUT[0] * olcek, _TARAMA_EN_BOYUT[1] * olcek
    for r in lekeler:
        if not (lo <= r.width <= hi and lo <= r.height <= hi):
            continue
        if any((r & kn).get_area() > 0.3 * r.get_area() for kn in known):
            continue
        if any((r & t).get_area() > _YAZI_ORTUSME * r.get_area() for t in text_rects):
            continue
        out.append(SignatureRegion(r + (-4, -4, 4, 4) & page_rect, "gorsel", ""))
    return _dedupe(out)


_KALAN_ORAN = 0.2  # girdi mürekkebinin bu kadarı çıktıda aynı yerde duruyorsa imza kalmış sayılır
_KALAN_EN_AZ = 30  # bundan az mürekkep pikseli olan bölge karşılaştırılmaz (gürültü)


def ink_snapshot(page: pymupdf.Page, rect: pymupdf.Rect) -> tuple[Image.Image, int] | None:
    """Bölgedeki mürekkep piksellerinin ikili görüntüsü (yalnızca bellekte) ve kenar payı.

    Yerel kontrastla bulunur: düz dolgu (karartma kutusu, beyaz boşluk) mürekkep sayılmaz. Kutunun
    kenarı komşu beyazlıkla kontrast verdiği için kenardan bir bulanıklık yarıçapı kadar şerit atılır.
    """
    clip = pymupdf.Rect(rect) & page.rect
    if clip.is_empty or clip.width < 6 or clip.height < 6:
        return None
    scale = min(2.0, max(0.5, 600.0 / max(clip.width, 1.0)))
    pix = page.get_pixmap(clip=clip, matrix=pymupdf.Matrix(scale, scale), alpha=False)
    im = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
    radius = max(3, int(min(clip.height, 40.0) * scale * 0.3))
    bw = ImageChops.subtract(im.filter(ImageFilter.BoxBlur(radius)), im).point(lambda p: 255 if p > 20 else 0)
    band = radius + 1
    ImageDraw.Draw(bw).rectangle([(0, 0), (bw.width - 1, bw.height - 1)], outline=0, width=band)
    return bw, band


def ink_remaining(before: tuple[Image.Image, int], after: tuple[Image.Image, int]) -> float:
    """Girdideki imza mürekkebinin çıktıda aynı yerde kalan oranı (0-1).

    Girdide yeterli mürekkep yoksa ya da iki görüntünün boyutu uyuşmazsa 0 döner.
    """
    b, a = before[0], after[0]
    total = sum(1 for v in b.getdata() if v)
    if total < _KALAN_EN_AZ or b.size != a.size:
        return 0.0
    # Sayfa piksel kaymasına karşı çıktıdaki iz biraz kalınlaştırılır.
    near = a.filter(ImageFilter.MaxFilter(5))
    same = ImageChops.multiply(b, near)
    return sum(1 for v in same.getdata() if v) / total


def preview_png(page: pymupdf.Page, rect: pymupdf.Rect) -> bytes:
    """Bulgu listesinde göz düğmesiyle gösterilecek küçük önizleme (yalnızca bellekte)."""
    clip = pymupdf.Rect(rect) + (-4, -4, 4, 4)
    return page.get_pixmap(clip=clip & page.rect, dpi=110).tobytes("png")
