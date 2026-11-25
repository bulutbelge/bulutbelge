"""PDF ve görsel tarama, gerçek silmeyle maskeleme.

Görseller (fotoğraf, taranmış belge) bellekte tek sayfalık PDF'e çevrilip aynı
yoldan işlenir (bkz. image.py). Metin katmanı olmayan sayfalar, dil dosyaları
kuruluysa OCR ile okunur (bkz. ocr.py).

Maskeleme görsel örtü değildir: bulgunun altındaki metin içerik akışından
silinir (PyMuPDF redaction), ardından meta veri, yorumlar, form alanları, ekli
dosyalar, JavaScript ve gizli metin temizlenir. Sonuç dosyası yeniden
taranır; işaretli bir değer hâlâ okunabiliyorsa dosya yazılmaz (kaçak tespiti).
"""

from __future__ import annotations

import os
import tempfile
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from .detect import HIGH, MEDIUM, Finding, detect
from .blur import blur_png
from .image import ImageError, image_to_doc, is_image, metadata_warnings, save_doc_as_image
from .faces import face_remains, find_faces
from .names import name_hints
from .visual_pii import find_barcodes_qr, find_visual_mrz, find_visual_plates, find_visual_stamps
from .ocr import SCAN_DPI, ocr_available, ocr_textpage
from .rules import BLACKOUT, BLUR, LABEL, Rules, kacak_iletisi
from .signatures import (
    _KALAN_ORAN,
    _fold,
    find_ocr_signatures,
    find_scanned_stamps,
    find_signatures,
    find_unlabeled_signatures,
    has_digital_signature,
    ink_remaining,
    ink_snapshot,
    is_stroke_drawing,
    preview_png,
)

# İmza bölgesine eklenen pay (pt). MuPDF bir çizimi, eğrinin kontrol noktaları ve çizgi
# kalınlığıyla birlikte tamamen örtülürse siler; çizim imzada bu yüzden pay geniş.
# ("Dokunanı sil" modu, imzaya değen tablo çizgilerini de bütünüyle silerdi.)
_SIGNATURE_PAD = {"gorsel": 3, "cizim": 12}

# Ligatürler ayrı harflere açılsın ("fi" → "f","i"), sayfa dışındaki metin de taransın.
_TEXT_FLAGS = pymupdf.TEXT_PRESERVE_WHITESPACE

# Yazı tipleri tireyi farklı kod noktalarına eşleyebiliyor (Arial'de U+00AD gibi).
_DASHES = {c: "-" for c in "­‐‑‒–−"}


class PdfError(Exception):
    """Kullanıcıya gösterilecek PDF hatası."""


class OcrUnavailable(PdfError):
    """Metin katmanı olmayan sayfa ya da görsel var ama OCR yapılamıyor: maskeleme reddedilir (K3).

    OCR normalde pakettedir; yoksa kurulum bozuktur. Sayfa maskesiz kalırdı, bu yüzden dosya yazılmaz.
    """


def ocr_refusal(where: str) -> str:
    return (
        f"OCR kullanılamıyor (kurulum bozuk olabilir): {where} metin katmanı yok ve OCR yapılamadığı için "
        "içindeki kişisel veri bulunamıyor. Maskeleme yapılmadı, dosya yazılmadı. BulutBelge'yi yeniden kurun."
    )


@dataclass
class PdfFinding:
    id: str
    page: int  # 1'den başlar
    finding: Finding
    rects: list[pymupdf.Rect]
    replacement: str
    kind: str = "metin"  # "metin" | "gorsel" | "cizim"
    preview: bytes | None = None  # imza önizlemesi (PNG), yalnızca bellekte
    image_digest: bytes | None = None
    image_xref: int = 0
    reason: str = ""  # elle seçilen alanın gerekçesi ("[Ticari Sir]" etiketi olarak yazılır)

    @property
    def locatable(self) -> bool:
        return bool(self.rects)


@dataclass
class ScanResult:
    pages: int
    findings: list[PdfFinding]
    warnings: list[str] = field(default_factory=list)
    # OCR ile okunan sayfalar (1'den başlar). Bu sayfalarda kaçak kontrolü de OCR ile yapılır.
    ocr_pages: list[int] = field(default_factory=list)
    # Metin katmanı olmayan (ya da taranmış görsel bölgesi olan) ve OCR yapılamayan sayfalar (1'den).
    no_ocr_pages: list[int] = field(default_factory=list)


@dataclass
class MaskResult:
    target: str
    masked: int
    warnings: list[str]
    dropped: int = 0  # kopyadan çıkarılan sayfa sayısı
    encrypted: bool = False  # kopya parolayla korundu
    flattened: int = 0  # görüntüye düzleştirilen sayfa sayısı


def parse_page_spec(spec: str | list[int] | tuple[int, ...] | None, page_count: int) -> list[int]:
    """'1, 4-6, tek, cift, 2-15:tek' gibi sayfa aralığını veya tam sayı listesini sıralı 1'den sayfa numaralarına çevirir."""
    if not spec:
        return []
    pages: set[int] = set()
    if isinstance(spec, (list, tuple, set)):
        for item in spec:
            if isinstance(item, bool) or not isinstance(item, int):
                raise PdfError("Sayfa numarası tam sayı olmalı")
            if not 1 <= item <= page_count:
                raise PdfError(f"Sayfa {item} belgede yok (toplam {page_count} sayfa)")
            pages.add(item)
        return sorted(pages)
    if not isinstance(spec, str):
        raise PdfError("Sayfa aralığı metin ya da sayı listesi olmalı")
    for raw_part in spec.split(","):
        part = raw_part.strip()
        if not part:
            continue
        low = part.lower().translate(str.maketrans("çğıöşü", "cgiosu"))
        if low in ("tumu", "hepsi", "all", "*"):
            pages.update(range(1, page_count + 1))
            continue
        if low in ("tek", "odd"):
            pages.update(p for p in range(1, page_count + 1) if p % 2 == 1)
            continue
        if low in ("cift", "even"):
            pages.update(p for p in range(1, page_count + 1) if p % 2 == 0)
            continue
        parity: int | None = None
        if ":" in low:
            rng_part, mod = low.rsplit(":", 1)
            mod = mod.strip()
            if mod in ("tek", "odd"):
                parity = 1
            elif mod in ("cift", "even"):
                parity = 0
            else:
                raise PdfError(f"Geçersiz sayfa filtresi: {part}")
            part = rng_part.strip()
        if "-" in part:
            halves = [h.strip() for h in part.split("-")]
            if len(halves) != 2 or not halves[0].isdigit() or not halves[1].isdigit():
                raise PdfError(f"Geçersiz sayfa aralığı: {part}")
            start, end = int(halves[0]), int(halves[1])
            if start < 1 or end > page_count or start > end:
                raise PdfError(f"Sayfa aralığı belge sınırları dışında: {part} (1–{page_count})")
            for p in range(start, end + 1):
                if parity is None or p % 2 == parity:
                    pages.add(p)
        else:
            if not part.isdigit():
                raise PdfError(f"Geçersiz sayfa numarası: {part}")
            p = int(part)
            if not 1 <= p <= page_count:
                raise PdfError(f"Sayfa {p} belgede yok (toplam {page_count} sayfa)")
            pages.add(p)
    return sorted(pages)


def _open(path: str | os.PathLike) -> pymupdf.Document:
    p = Path(path)
    if not p.is_file():
        raise PdfError("Dosya bulunamadı")
    if is_image(p):
        try:
            return image_to_doc(p)
        except ImageError as exc:
            raise PdfError(str(exc)) from None
    try:
        doc = pymupdf.open(p)
    except Exception:
        raise PdfError("Dosya PDF olarak açılamadı") from None
    if not doc.is_pdf:
        doc.close()
        raise PdfError("Dosya PDF değil")
    if doc.needs_pass:
        doc.close()
        raise PdfError("Parolalı PDF'ler henüz desteklenmiyor")
    return doc


def _flatten_doc(doc: pymupdf.Document) -> pymupdf.Document:
    """Her sayfayı görüntüye çevirip yalnızca görüntü içeren yeni bir belge döndürür.

    Metin katmanı, gizli metin, yorum, form alanı, ek ve meta veri yeni belgeye geçmez; sayfada
    görünenler pikseldir. Maskeleme bu görüntüler OCR ile okunarak yapılır. Açıklamalar
    (görünür yorumlar) görüntüye dahil edilir ki OCR'a girsin. Yeni belge bellektedir.
    """
    if not ocr_available():
        raise PdfError(
            "Düzleştirme için OCR dil dosyaları gerekli ama kurulu değil. "
            "Dosya yazılmadı (şüphede reddet)."
        )
    flat = pymupdf.open()
    zoom = SCAN_DPI / 72
    for page in doc:
        pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=True, alpha=False)
        new = flat.new_page(width=page.rect.width, height=page.rect.height)
        new.insert_image(new.rect, stream=pix.tobytes("png"))
    return flat


def _page_text(
    page: pymupdf.Page,
    textpage: pymupdf.TextPage | None = None,
    only_inside: list[pymupdf.Rect] | None = None,
    skip_rects: list[pymupdf.Rect] | None = None,
) -> tuple[str, list[pymupdf.Rect | None]]:
    """Sayfa metni ve her karakterin kutusu (satır/blok ayraçları için None).

    `only_inside` ve `skip_rects`: karma (hem dijital metin hem gömülü tarama görseli içeren) sayfalarda
    yalnız dijital metnin örtemediği görsel bölgelerdeki OCR bloklarını seçmek içindir.
    """
    chars: list[str] = []
    boxes: list[pymupdf.Rect | None] = []
    raw = page.get_text("rawdict", flags=_TEXT_FLAGS, textpage=textpage)
    for block in raw["blocks"]:
        if block.get("type") != 0:
            continue
        if only_inside is not None:
            b_rect = pymupdf.Rect(block["bbox"])
            if not any(
                b_rect.intersects(ir) and (b_rect & ir).get_area() > 0.35 * max(b_rect.get_area(), 1.0)
                for ir in only_inside
            ):
                continue
            if skip_rects and any(
                b_rect.intersects(sr) and (b_rect & sr).get_area() > 0.4 * max(b_rect.get_area(), 1.0)
                for sr in skip_rects
            ):
                continue
        for line in block["lines"]:
            for span in line["spans"]:
                for ch in span["chars"]:
                    # Bölünemez/ince boşluklar ve tire türevleri kalıplarda düz karakter gibi eşleşsin.
                    c = ch["c"]
                    chars.append(" " if c.isspace() else _DASHES.get(c, c))
                    boxes.append(pymupdf.Rect(ch["bbox"]))
            chars.append("\n")
            boxes.append(None)
        chars.append("\n")
        boxes.append(None)
    return "".join(chars), boxes


def _uncovered_image_rects(page: pymupdf.Page, vector_boxes: list[pymupdf.Rect | None]) -> list[pymupdf.Rect]:
    """Metin katmanı olsa bile üzerinde yeterli vektör karakteri bulunmayan büyük görselleri bulur (karma PDF)."""
    page_area = max(page.rect.get_area(), 1.0)
    rects: list[pymupdf.Rect] = []
    char_rects = [b for b in vector_boxes if b is not None]
    for info in page.get_image_info():
        bbox = pymupdf.Rect(info["bbox"]) & page.rect
        if bbox.is_empty or bbox.get_area() < max(6000.0, 0.10 * page_area):
            continue
        covered_chars = sum(1 for cb in char_rects if bbox.intersects(cb))
        if covered_chars < 12:
            rects.append(bbox)
    return rects


def _span_rects(boxes: list[pymupdf.Rect | None], start: int, end: int) -> list[pymupdf.Rect]:
    """Bulgunun karakter kutularını satır bazında birleştirir."""
    rects: list[pymupdf.Rect] = []
    current: pymupdf.Rect | None = None
    for box in boxes[start:end]:
        if box is None:
            if current is not None:
                rects.append(current)
                current = None
            continue
        current = pymupdf.Rect(box) if current is None else current | box
    if current is not None:
        rects.append(current)
    return [r for r in rects if not r.is_empty]


def _gercek_yazi_kutulari(page: pymupdf.Page, tp: pymupdf.TextPage) -> list[pymupdf.Rect]:
    """OCR kelime kutuları; imza çizgisini "SI" gibi okuyan gürültü (karakter başına aşırı geniş) elenir."""
    out = []
    for w in page.get_text("words", textpage=tp):
        r = pymupdf.Rect(w[:4])
        if r.width / max(len(w[4]), 1) > 1.2 * r.height:
            continue
        out.append(r)
    return out


def _add_stamps(
    findings: list[PdfFinding],
    page: pymupdf.Page,
    index: int,
    stamps: list,
    known: list[pymupdf.Rect],
    rules: Rules,
    previews: bool,
) -> None:
    """Etiketsiz renkli kaşe/imza lekelerini önerilen bulgu olarak ekler."""
    for i, region in enumerate(stamps):
        if any((region.rect & k).get_area() > 0.3 * region.rect.get_area() for k in known):
            continue
        f = Finding("imza", -1, -1, "", MEDIUM, "görsel")
        findings.append(
            PdfFinding(
                id=f"p{index + 1}:imza:etiketsiz:{i}",
                page=index + 1,
                finding=f,
                rects=[region.rect],
                replacement=rules.replacement_for(f),
                kind="gorsel",
                preview=preview_png(page, region.rect) if previews else None,
            )
        )


# Vektör çizimle üretilmiş QR/barkod yüzlerce küçük çizim parçasıdır; bu aralık dışındaki sayfalar (düz metin, çok ağır çizim)
# renderlanıp taranmaz (hız).
_KOD_CIZIM_ARALIGI = (40, 6000)


def _gorsel_bulgular(
    findings: list[PdfFinding],
    page: pymupdf.Page,
    index: int,
    rules: Rules,
    previews: bool,
    image: bool,
    codes_on: bool,
    plates_on: bool,
    mrz_on: bool,
    stamps_on: bool = False,
) -> None:
    """QR kod/barkod, fotoğraftaki plaka ve kimlik MRZ bölgesi: görüntüden (OpenCV) bulunur, OCR gerekmez.

    Metin katmanından gelen aynı türdeki bulgularla çakışanlar `_gorsel_tekrarlarini_ele` ile elenir.
    """
    has_images = image or bool(page.get_images())

    def ekle(tur: str, rect: pymupdf.Rect, aciklama: str, anahtar: str, sira: int) -> None:
        f = Finding(tur, -1, -1, "", MEDIUM if tur != "barkod_qr" else HIGH, aciklama)
        findings.append(
            PdfFinding(
                id=f"p{index + 1}:{anahtar}:{sira}",
                page=index + 1,
                finding=f,
                rects=[rect],
                replacement=rules.replacement_for(f),
                kind="gorsel_kod",
                preview=preview_png(page, rect) if previews else None,
            )
        )

    if codes_on:
        vektor = False
        if not has_images:
            n = len(page.get_cdrawings())
            vektor = _KOD_CIZIM_ARALIGI[0] <= n <= _KOD_CIZIM_ARALIGI[1]
        if has_images or vektor:
            for i, (rect, desc) in enumerate(find_barcodes_qr(page)):
                ekle("barkod_qr", rect, desc, "kod", i)
    if plates_on:
        for i, prect in enumerate(find_visual_plates(page)):
            ekle("plaka", prect, "görsel plaka", "plaka:gorsel", i)
    if mrz_on and has_images:
        for k, (mrect, mdesc) in enumerate(find_visual_mrz(page)):
            ekle("mrz", mrect, mdesc, "mrz:gorsel", k)
    if stamps_on:
        for j, (srect, sdesc) in enumerate(find_visual_stamps(page)):
            ekle("imza", srect, sdesc, "imza:kase", j)


def _yazi_plakalarini_ele(findings: list[PdfFinding], index: int, words: list) -> list[PdfFinding]:
    """Görüntüden bulunan "plaka" bölgesinde OCR rakamsız bir yazı okuyorsa (ör. renkli zemin üstündeki
    kalın başlık "ÖRNEK BİLİŞİM") bu bir plaka değildir; Türk plakasında her zaman rakam vardır.
    OCR bölgede hiçbir şey okuyamadıysa (bulanık fotoğraf plakası) bulgu korunur."""
    out = []
    for f in findings:
        if f.kind == "gorsel_kod" and f.finding.type == "plaka" and f.page == index + 1 and f.rects:
            r = f.rects[0]
            icerde = [
                w[4] for w in words
                if (r & pymupdf.Rect(w[:4])).get_area() >= 0.5 * max(pymupdf.Rect(w[:4]).get_area(), 1e-6)
            ]
            yazi = "".join(icerde)
            if sum(c.isalpha() for c in yazi) >= 4 and not any(c.isdigit() for c in yazi):
                continue
        out.append(f)
    return out


def _gorsel_tekrarlarini_ele(findings: list[PdfFinding]) -> list[PdfFinding]:
    """Görüntüden bulunan plaka/MRZ, metin katmanı ya da OCR'dan aynı yerde zaten bulunduysa tekrar sayılmaz."""
    metinden = [f for f in findings if f.kind != "gorsel_kod" and f.finding.type in ("plaka", "mrz", "imza") and f.rects]
    out = []
    for f in findings:
        if f.kind == "gorsel_kod" and f.finding.type in ("plaka", "mrz", "imza") and f.rects:
            r = f.rects[0]
            if any(
                m.page == f.page
                and m.finding.type == f.finding.type
                and any(not (r & mr).is_empty and (r & mr).get_area() > 0.35 * min(r.get_area(), mr.get_area()) for mr in m.rects)
                for m in metinden
            ):
                continue
        out.append(f)
    return out


def _scan_doc(doc: pymupdf.Document, rules: Rules, previews: bool = False, image: bool = False) -> ScanResult:
    findings: list[PdfFinding] = []
    warnings: list[str] = []
    ocr_pages: list[int] = []
    no_ocr_pages: list[int] = []
    ocr_signature_pages: list[int] = []
    # Görselde imza etiketi metin katmanında olmadığından imza otomatik aranmaz.
    signatures_on = rules.types["imza"].enabled and not image
    faces_on = rules.types["yuz"].enabled
    codes_on = "barkod_qr" in rules.types and rules.types["barkod_qr"].enabled
    plates_on = image and "plaka" in rules.types and rules.types["plaka"].enabled
    mrz_on = "mrz" in rules.types and rules.types["mrz"].enabled
    stamps_on = image and rules.types["imza"].enabled
    if has_digital_signature(doc):
        warnings.append(
            "Belgede elektronik imza var. Maskelenen kopyada e-imza kaldırılır; "
            "imzanın geçerliliği orijinal belgede kalır."
        )
    # Belge düzeyi ad ipuçları (e-posta adreslerinden): sayfa sayfa taranırken diğer sayfalardaki adres de bilinir.
    hints = (
        name_hints([pg.get_text("text", flags=_TEXT_FLAGS) for pg in doc])
        if rules.types["kisi_adi"].enabled
        else frozenset()
    )
    for index, page in enumerate(doc):
        text, boxes = _page_text(page)
        if text.strip() and page.get_images():
            # Karma PDF: metin katmanı var ama içinde vektör metin bulunmayan taranmış görsel blokları da var.
            uncovered = _uncovered_image_rects(page, boxes)
            if uncovered:
                if not ocr_available():
                    no_ocr_pages.append(index + 1)
                else:
                    vector_char_rects = [b for b in boxes if b is not None]
                    ocr_text, ocr_boxes = _page_text(
                        page, ocr_textpage(page, image), only_inside=uncovered, skip_rects=vector_char_rects
                    )
                    if ocr_text.strip():
                        text = text + "\n\n" + ocr_text
                        boxes = boxes + [None, None] + ocr_boxes
                        ocr_pages.append(index + 1)
        _gorsel_bulgular(findings, page, index, rules, previews, image, codes_on, plates_on, mrz_on, stamps_on)
        seen_xrefs: set[int] = set()
        if signatures_on:
            labeled = find_signatures(page, rules.signature_labels)
            unlabeled_on = any(lbl.strip() for lbl in rules.signature_labels)  # etiket listesi boşsa imza aranmaz
            # Etiketsiz imza: temkinli sezgi; etiketli bulgular önceliklidir.
            if unlabeled_on:
                labeled += find_unlabeled_signatures(
                    page, [r.rect for r in labeled], [pymupdf.Rect(w[:4]) for w in page.get_text("words")]
                )
            for i, region in enumerate(labeled):
                pad = _SIGNATURE_PAD[region.kind]
                rect = region.rect + (-pad, -pad, pad, pad)
                if region.image_xref:
                    seen_xrefs.add(region.image_xref)
                f = Finding("imza", -1, -1, "", MEDIUM, "görsel" if region.kind == "gorsel" else "çizim")
                findings.append(
                    PdfFinding(
                        id=f"p{index + 1}:imza:{i}",
                        page=index + 1,
                        finding=f,
                        rects=[rect & page.rect],
                        replacement=rules.replacement_for(f),
                        kind=region.kind,
                        preview=preview_png(page, region.rect) if previews else None,
                        image_digest=region.image_digest,
                        image_xref=region.image_xref,
                    )
                )

        if not image and page.get_images() and (signatures_on or rules.types["kurum_unvani"].enabled):
            from .efatura import find_efatura_visuals

            # QR/barkod olarak zaten bulunan görsel ikinci kez "imza" (e-Fatura QR) sayılmaz; aynı görsel
            # tek bulgudur. ETTN türü açıkken e-Fatura olmayan belgede de bu arama çalışır (deneme 6 D1).
            kod_rects = [r for f in findings if f.kind == "gorsel_kod" and f.page == index + 1 for r in f.rects]
            for i, (ftype, region) in enumerate(find_efatura_visuals(page, rules, text)):
                if region.image_xref and region.image_xref in seen_xrefs:
                    continue
                if ftype == "imza" and any(
                    (pymupdf.Rect(r) & region.rect).get_area() >= 0.5 * pymupdf.Rect(r).get_area() for r in kod_rects
                ):
                    continue
                if region.image_xref:
                    seen_xrefs.add(region.image_xref)
                f = Finding(ftype, -1, -1, "", MEDIUM, region.label)
                findings.append(
                    PdfFinding(
                        id=f"p{index + 1}:efatura:{i}",
                        page=index + 1,
                        finding=f,
                        rects=[region.rect],
                        replacement=rules.replacement_for(f),
                        kind=region.kind,
                        preview=preview_png(page, region.rect) if previews else None,
                        image_digest=region.image_digest,
                        image_xref=region.image_xref,
                    )
                )

        # Fotoğraf ve taranmış sayfalarda yüzler (görsel içermeyen sayfada aranmaz).
        if faces_on and (image or page.get_images()):
            for i, rect in enumerate(find_faces(page)):
                f = Finding("yuz", -1, -1, "", MEDIUM, "fotoğraf")
                findings.append(
                    PdfFinding(
                        id=f"p{index + 1}:yuz:{i}",
                        page=index + 1,
                        finding=f,
                        rects=[rect],
                        replacement=rules.replacement_for(f),
                        kind="yuz",
                    )
                )

        if not text.strip():
            if not page.get_images():
                continue
            # Metin katmanı yok, görsel var: fotoğraf ya da taranmış sayfa.
            if not ocr_available():
                no_ocr_pages.append(index + 1)
                # OCR yokken de renkli kaşe/imza lekesi aranır (yazı konumu bilinmez; yalnızca renk).
                if rules.types["imza"].enabled and any(lbl.strip() for lbl in rules.signature_labels):
                    _add_stamps(findings, page, index, find_scanned_stamps(page, [], []), [], rules, previews)
                continue
            tp = ocr_textpage(page, image)
            findings[:] = _yazi_plakalarini_ele(findings, index, page.get_text("words", textpage=tp))
            text, boxes = _page_text(page, tp)
            ocr_pages.append(index + 1)
            # Etiketsiz renkli kaşe/imza lekesi; etiketli arama aşağıda yine çalışır.
            stamps = []
            if rules.types["imza"].enabled and any(lbl.strip() for lbl in rules.signature_labels):
                stamps = find_scanned_stamps(page, [], _gercek_yazi_kutulari(page, tp))
            if not text.strip() and not stamps:
                continue
            # Görseldeki imza pikseldir, çizim değil; otomatik bulunamaz. Etiketi görünüyorsa uyar.
            folded = _fold(text)
            ocr_sigs = []
            if rules.types["imza"].enabled and any(_fold(lbl) in folded for lbl in rules.signature_labels if lbl.strip()):
                ocr_sigs = find_ocr_signatures(page, tp, rules.signature_labels)
                for i, region in enumerate(ocr_sigs):
                    f = Finding("imza", -1, -1, "", MEDIUM, "görsel")
                    findings.append(
                        PdfFinding(
                            id=f"p{index + 1}:imza:ocr:{i}",
                            page=index + 1,
                            finding=f,
                            rects=[region.rect],
                            replacement=rules.replacement_for(f),
                            kind="gorsel",
                            preview=preview_png(page, region.rect) if previews else None,
                        )
                    )
                if not ocr_sigs:
                    ocr_signature_pages.append(index + 1)
            _add_stamps(findings, page, index, stamps, [r.rect for r in ocr_sigs], rules, previews)
            if not text.strip():
                continue
        for f in detect(text, rules, hints, lead=index == 0):
            findings.append(
                PdfFinding(
                    id=f"p{index + 1}:{f.start}:{f.end}",
                    page=index + 1,
                    finding=f,
                    rects=_span_rects(boxes, f.start, f.end),
                    replacement=rules.replacement_for(f),
                )
            )
    if ocr_pages:
        warnings.append(
            ("Görseldeki yazı" if image else f"Taranmış {len(ocr_pages)} sayfa")
            + " OCR ile okundu. OCR hata yapabilir; sonucu önizlemede kontrol edin, "
            "kaçanları “Alan seç” ile ekleyin."
        )
    if ocr_signature_pages:
        where = "Görselde" if image else f"Sayfa {', '.join(map(str, ocr_signature_pages))}:"
        warnings.append(
            f"{where} imza ya da kaşe etiketi var. Etiketin yakınında imza önerisi çıkmadı (siyah imza yazıdan ayrılamaz); "
            "önizlemede kontrol edin; bulunamayan imzayı “Alan seç” ile işaretleyin."
        )
    if no_ocr_pages:
        where = "Görselde" if image else f"Sayfa {', '.join(map(str, no_ocr_pages))}:"
        warnings.append(
            f"{where} metin katmanı yok ve OCR dil dosyaları kurulu değil (kurulum bozuk olabilir). "
            "Otomatik tespit yapılamadı; bu sayfalar maskelenecekse maskeli kopya yazılmaz. BulutBelge'yi yeniden kurun."
        )
    findings = _gorsel_tekrarlarini_ele(findings)
    return ScanResult(
        pages=doc.page_count, findings=findings, warnings=warnings, ocr_pages=ocr_pages,
        no_ocr_pages=sorted(set(no_ocr_pages)),
    )


def scan_pdf(path: str | os.PathLike, rules: Rules, previews: bool = False, flatten: bool = False) -> ScanResult:
    """PDF ya da görsel dosyayı tarar. `flatten`: sayfalar önce görüntüye çevrilir (bkz. mask_pdf)."""
    doc = _open(path)
    try:
        if flatten and not is_image(path):
            result_warnings = _flatten_warnings(doc)
            doc = _swap_flat(doc)
        else:
            result_warnings = []
        result = _scan_doc(doc, rules, previews, image=is_image(path))
        result.warnings = result_warnings + result.warnings
    finally:
        doc.close()
    if is_image(path):
        result.warnings = metadata_warnings(path) + result.warnings
    return result


def _flatten_warnings(doc: pymupdf.Document) -> list[str]:
    """Düzleştirmeden önce kaynakta görülen, düzleştirmeyle değişen durumlar."""
    warnings = [
        "Düzleştirme açık: sayfalar görüntüye çevrilip OCR ile okunur. Metin seçilemez ve aranamaz "
        "hale gelir, dosya büyür; OCR hata yapabilir, sonucu önizlemede kontrol edin."
    ]
    if has_digital_signature(doc):
        warnings.append(
            "Belgede elektronik imza var. Düzleştirilen kopyada e-imza kalmaz; "
            "imzanın geçerliliği orijinal belgede kalır."
        )
    return warnings


def _swap_flat(doc: pymupdf.Document) -> pymupdf.Document:
    """Belgeyi düzleştirilmişiyle değiştirir; asıl belge kapatılır."""
    flat = _flatten_doc(doc)  # hata verirse asıl belgeyi çağıran kapatır
    doc.close()
    return flat


def _manual_findings(doc: pymupdf.Document, rules: Rules, areas: list[tuple]) -> list[PdfFinding]:
    """`areas`: (sayfa, (x0, y0, x1, y1)) ya da (sayfa, (x0, y0, x1, y1), gerekçe)."""
    out = []
    for i, area in enumerate(areas):
        page_no, coords = area[0], area[1]
        reason = (area[2] or "").strip()[:40] if len(area) > 2 else ""
        if not 1 <= page_no <= doc.page_count:
            raise PdfError(f"Elle seçilen alan geçersiz sayfada: {page_no}")
        rect = pymupdf.Rect(coords) & doc[page_no - 1].rect
        if rect.is_empty or rect.width < 2 or rect.height < 2:
            raise PdfError("Elle seçilen alan çok küçük ya da sayfanın dışında")
        f = Finding("elle", -1, -1, "", HIGH, "alan")
        if reason:
            from .extra_types import ascii_tr

            replacement = ascii_tr("[" + reason.strip("[] ") + "]")
        else:
            replacement = rules.replacement_for(f)
        out.append(
            PdfFinding(
                id=f"elle:{i}",
                page=page_no,
                finding=f,
                rects=[rect],
                replacement=replacement,
                kind="alan",
                reason=reason,
            )
        )
    return out


def render_page(path: str | os.PathLike, page_no: int, width_px: int = 900) -> tuple[bytes, float, float, int]:
    """Sayfanın PNG görüntüsü ve pt cinsinden boyutu. `page_no` 1'den başlar."""
    doc = _open(path)
    try:
        if not 1 <= page_no <= doc.page_count:
            raise PdfError("Sayfa yok")
        page = doc[page_no - 1]
        rect = page.rect
        zoom = max(0.05, min(3.0, min(width_px, 1800) / rect.width))
        png = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), annots=False).tobytes("png")
        return png, rect.width, rect.height, doc.page_count
    finally:
        doc.close()


def default_target(source: str | os.PathLike) -> str:
    """Kaynağın yanında `_maskeli` sonekli, var olan bir dosyanın üzerine yazmayan yol."""
    src = Path(source)
    return str(unique_path(src.with_name(f"{src.stem}_maskeli{src.suffix}")))


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    n = 2
    while True:
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def count_types(counts: dict[str, int], types) -> None:
    """Tür bazında bulgu sayısı (değer değil); işlem günlüğüne girer."""
    for t in types:
        counts[t] = counts.get(t, 0) + 1


def _normalize(s: str) -> str:
    """Kaçak denetimi anahtarı (bütün biçimler bunu kullanır): boşluk ve noktalama atılır, büyük/küçük harf
    Türkçeye uygun eşlenir (bağımsız inceleme bulgu 20). "YILMAZ", "Yılmaz" ve "yilmaz" aynı anahtara iner
    ("I".casefold() = "i" ama "ı".casefold() = "ı"; "İ".casefold() = "i" + birleşik nokta). Telefon ya da kimlik
    numarası noktalı, tireli, parantezli yazılsa da eşleşir. Eşleşme fazlalaşırsa yazma reddedilir (şüphede reddet).
    """
    t = "".join(c for c in s if not c.isspace()).casefold().replace("\u0307", "").replace("ı", "i")
    return "".join(c for c in t if not unicodedata.category(c).startswith("P"))


_HELV_SPAN = 1.378  # helv için arama kutusu yüksekliği / yazı boyutu


def _label_metrics(page: pymupdf.Page, rect: pymupdf.Rect, max_font: float) -> tuple[float, float]:
    """Kutudaki yazının boyutu ve taban çizgisi; çevre yazı yoksa kutu yüksekliğinden kestirilir."""
    best = None
    for block in page.get_text("dict", clip=rect, flags=_TEXT_FLAGS).get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("size", 0) > 0 and (best is None or span["size"] > best["size"]):
                    best = span
    if best is not None and best["origin"][1] >= rect.y0 and best["origin"][1] <= rect.y1 + 1:
        return float(best["size"]), float(best["origin"][1])
    size = max(4.0, min(max_font, rect.height / _HELV_SPAN))
    return size, rect.y1 - size * 0.28


def _fit_font_size(text: str, size: float, width: float) -> float:
    """Yazı kutu genişliğine sığmıyorsa küçültür (en az 4 pt)."""
    natural = pymupdf.get_text_length(text, fontname="helv", fontsize=size)
    if width > 0 and natural > width:
        size = size * width / natural
    return max(4.0, size)


_BOSLUK_ORANI = 0.6  # etiket, değerin kapladığı genişliğin en az bu kadarını doldurmalı


def _bosluk_sizar(deger_genisligi: float, etiket_genisligi: float) -> bool:
    """Etiket değerden çok kısaysa yanındaki yazılar arasında kalan boşluk değerin uzunluğunu gösterir (1.58)."""
    return deger_genisligi > 0 and etiket_genisligi < deger_genisligi * _BOSLUK_ORANI


def _boslukluk_uyarilari(etiketli: int, kutulu: int) -> list[str]:
    """PDF'te yazı yerinde kalır: silinen değerin yeri boş ya da tam genişlikte kutu olarak görünür (PoPETs 2023).
    Değer yazılmaz; yalnızca kaç yerde uzunluğun anlaşılabileceği söylenir."""
    out: list[str] = []
    if etiketli:
        out.append(
            f"{etiketli} yerde yerine konan etiket silinen değerden çok kısa; aradaki boşluk değerin uzunluğunu "
            "gösterebilir. Karartma yöntemini düşünün."
        )
    if kutulu:
        out.append(
            f"{kutulu} karartma kutusu değerin gerçek genişliğinde; uzunluk anlaşılabilir. "
            "Uzunluk önemliyse çıktıyı gözle kontrol edin."
        )
    return out


def mask_pdf(
    source: str | os.PathLike,
    target: str | os.PathLike,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    manual_areas: list[tuple[int, tuple[float, float, float, float]]] | None = None,
    make_dirs: bool = False,
    drop_pages: list[int] | None = None,
    password: str | None = None,
    counts: dict[str, int] | None = None,
    watermark: bool = False,
    flatten: bool = False,
    mask_pages: str | list[int] | None = None,
    exclude_pages: str | list[int] | None = None,
    strip_bookmarks: bool = True,
    require_ocr: bool = True,
) -> MaskResult:
    """Kaynağı tarar, dışlananlar dışındaki bulguları siler, sonucu hedefe yazar.

    `drop_pages`: paylaşılacak kopyadan tamamen çıkarılacak sayfalar (1'den). Önce belge her
    zamanki gibi maskelenip denetlenir, sonra sayfalar silinir ve sahipsiz kalan nesneler
    (yalnızca o sayfalardaki görseller, yazı akışları) dosyadan atılır.
    `password`: kopya bu parolayla AES-256 şifrelenir (yalnızca PDF). Şifreleme en son adımdır:
    kaçak denetimi şifresiz ara dosyada yapılır, sonra şifreli dosyanın parolayla açıldığı ve
    sayfa sayısının aynı kaldığı denetlenir. Parola diske ya da günlüğe yazılmaz.

    `manual_areas`: kullanıcının önizlemede çizdiği alanlar, (sayfa (1'den), (x0, y0, x1, y1) pt).
    Alandaki metin, görsel pikselleri ve tamamen içinde kalan çizimler silinir.
    `make_dirs`: hedef klasör yoksa oluştur (klasörle toplu işlemde alt klasörler için).

    `counts`: verilirse maskelenen bulgular tür bazında sayılıp buraya yazılır (işlem günlüğü için).
    `watermark`: her sayfaya soluk, köşegen "MASKELİ KOPYA" yazısı eklenir (isteğe bağlı).

    `mask_pages`: yalnız bu sayfalar maskelenir ("4-6", "1, 4-5, 7", "tek", "cift"; ya da sayı listesi); diğer
    sayfalar olduğu gibi kalır. `exclude_pages`: bu sayfalar maskelenmez (önce `mask_pages` uygulanır).
    `strip_bookmarks`: yer imleri (başlıklar kişisel veri taşıyabilir) kopyadan silinir; False ile korunur.

    `require_ocr`: metin katmanı olmayan ve OCR yapılamayan bir sayfa (ya da görsel) maskelenecekse
    OcrUnavailable (dosya yazılmaz). Yalnızca maskeli okuma (readout) False verir: orada kopya diske kalmaz
    ve okunamayan sayfanın içeriği çıktıya zaten girmez.

    `flatten`: yüksek riskli belge için; her sayfa görüntüye çevrilip yeniden OCR ile okunur ve
    maskelenir. Metin katmanı, gizli metin, açıklama ve ekler kopyaya hiç geçmez.
    OCR dil dosyaları yoksa dosya yazılmaz. Yalnızca PDF'te; görselde yok sayılır (zaten görüntü).

    Orijinal dosyaya dokunulmaz. Hedef var olan bir dosyaysa yeni bir ad seçilir.
    """
    excluded_ids = excluded_ids or set()
    src = Path(source).resolve()
    dst = Path(target).resolve()
    if src == dst:
        raise PdfError("Hedef, kaynak dosyanın kendisi olamaz")
    image = is_image(src)
    # Çıktı kaynakla aynı biçimde olur (PDF → PDF, JPG → JPG).
    if dst.suffix.lower() != src.suffix.lower():
        dst = dst.with_suffix(src.suffix)
    if make_dirs:
        dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.parent.is_dir():
        raise PdfError("Hedef klasör bulunamadı")
    dst = unique_path(dst)

    if password is not None:
        if image:
            raise PdfError("Görsel parolayla korunamaz; yalnızca PDF")
        if len(password) < MIN_PASSWORD:
            raise PdfError(f"Parola en az {MIN_PASSWORD} karakter olmalı")
    doc = _open(src)
    drop = sorted({int(p) for p in drop_pages or []})
    if drop:
        if image:
            doc.close()
            raise PdfError("Görselden sayfa çıkarılamaz")
        if any(p < 1 or p > doc.page_count for p in drop):
            doc.close()
            raise PdfError("Çıkarılacak sayfa belgede yok")
        if len(drop) >= doc.page_count:
            doc.close()
            raise PdfError("Bütün sayfalar çıkarılamaz; en az bir sayfa kalmalı")
    flatten_warnings: list[str] = []
    try:
        if flatten and not image:
            flatten_warnings = _flatten_warnings(doc)
            doc = _swap_flat(doc)
        scan = _scan_doc(doc, rules, image=image)
        scan.warnings = flatten_warnings + scan.warnings
        n_pages = doc.page_count
        active = set(range(1, n_pages + 1))
        if mask_pages or exclude_pages:
            active = set(parse_page_spec(mask_pages, n_pages)) if mask_pages else active
            active -= set(parse_page_spec(exclude_pages, n_pages))
            excluded_ids = excluded_ids | {f.id for f in scan.findings if f.page not in active}
        # K3: OCR yapılamayan sayfa sessizce maskesiz yazılmaz. Kullanıcının maskelenmesin dediği ya da
        # kopyadan çıkardığı sayfa hariç.
        unreadable = sorted(set(scan.no_ocr_pages) & active - set(drop))
        if unreadable and require_ocr:
            raise OcrUnavailable(ocr_refusal("Görselin" if image else f"Sayfa {', '.join(map(str, unreadable))}:"))
        scan.findings.extend(_manual_findings(doc, rules, manual_areas or []))
        included = [f for f in scan.findings if f.id not in excluded_ids]
        unlocated = [f for f in included if not f.locatable]
        if unlocated:
            # Şüphede reddet: konumu bulunamayan bir bulguyu sessizce geçme.
            raise PdfError(
                f"{len(unlocated)} bulgunun belgedeki yeri bulunamadı. "
                "Bunları listeden çıkarıp elle kontrol edin."
            )

        # Girdideki imza mürekkebi, silmeden önce bellekte saklanır; çıktıyla karşılaştırılacak.
        sig_before = [
            (f, snap)
            for f in included
            if f.finding.type == "imza" and f.kind in ("gorsel", "cizim") and f.rects
            for snap in [ink_snapshot(doc[f.page - 1], f.rects[0])]
            if snap is not None
        ]

        # İmza görselini tamamen sil (yalnızca piksellerini değil). Aynı görsel kullanıcının
        # dışarıda bıraktığı başka bir bulguda da kullanılıyorsa yalnızca bölgesi silinir.
        kept_xrefs = {f.image_xref for f in scan.findings if f.id in excluded_ids and f.image_xref}
        for f in included:
            if f.kind == "gorsel" and f.image_xref and f.image_xref not in kept_xrefs:
                doc[f.page - 1].delete_image(f.image_xref)

        _remove_signature_strokes(doc, [f for f in included if f.kind == "cizim"])

        # Görselde 1 pt = 1 px; büyük fotoğrafta etiket yazısı da büyümeli.
        max_font = 11.0 if not image else max(11.0, doc[0].rect.width / 60)
        blurs: list[tuple[int, pymupdf.Rect, str]] = []
        labels: list[tuple[int, pymupdf.Rect, str, float, float]] = []
        boxes: list[tuple[int, pymupdf.Rect]] = []  # etiketsiz silinen kutular (glif denetimi)
        tails: dict[int, list[_TailWord]] = {}  # silinen metnin sağındaki sözcükler (kayma onarımı)
        for f in included:
            page = doc[f.page - 1]
            method = rules.method_for(f.finding.type, f.finding.source)
            if f.reason:
                method = LABEL  # gerekçeli elle alan: kutu yerine "[gerekçe]" etiketi
            blackout = method == BLACKOUT
            if method == BLUR:
                blurs.extend((f.page - 1, r, f.kind) for r in f.rects)
            for i, rect in enumerate(f.rects):
                if i == 0 and f.replacement and not blackout:
                    # Etiket redaction'a değil, silmeden sonra çevre yazının boyut ve taban çizgisiyle yazılır.
                    labels.append((f.page - 1, rect, f.replacement, *_label_metrics(page, rect, max_font)))
                if f.kind == "metin" and not image:
                    tails.setdefault(f.page - 1, []).extend(_tail_words(page, rect))
                if f.kind == "metin" and not (i == 0 and f.replacement and not blackout):
                    boxes.append((f.page - 1, rect))
                if image and f.kind == "metin":
                    # OCR sözcük kutusu harfin üst/alt ucunu tam kapsamayabilir (büyük harf ve noktalı harf izi kalırdı); biraz genişletilir.
                    pay = max(1.0, rect.height * 0.15)
                    rect = pymupdf.Rect(rect.x0, rect.y0 - pay, rect.x1, rect.y1 + pay)
                page.add_redact_annot(rect, fill=(0, 0, 0) if blackout else (1, 1, 1), cross_out=False)

        for page in doc:
            # Redaction dışındaki açıklamalar (yorum, not) kişisel veri taşıyabilir.
            for annot in list(page.annots() or []):
                if annot.type[0] != pymupdf.PDF_ANNOT_REDACT:
                    page.delete_annot(annot)
            # Form alanı değerleri (ve görünüm akışı) sayfa metni değildir; alan silinir.
            for widget in list(page.widgets() or []):
                page.delete_widget(widget)
            page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_PIXELS)
            if tails.get(page.number):
                scan.warnings.extend(_restore_shifted(page, tails[page.number]))

        bosluk_etiket = 0
        for page_index, rect, text, size, baseline in labels:
            size = _fit_font_size(text, size, rect.width)
            doc[page_index].insert_text((rect.x0, baseline), text, fontname="helv", fontsize=size, color=(0, 0, 0))
            if _bosluk_sizar(rect.width, pymupdf.get_text_length(text, fontname="helv", fontsize=size)):
                bosluk_etiket += 1
        scan.warnings.extend(
            _boslukluk_uyarilari(
                bosluk_etiket,
                sum(
                    1
                    for f in included
                    if f.kind == "metin" and rules.method_for(f.finding.type, f.finding.source) == BLACKOUT
                )
                if not image
                else 0,
            )
        )

        # Bulanık yöntem: içerik yukarıda silindi; boşluğa bilgi taşımayan dolgu konur.
        for page_index, rect, kind in blurs:
            doc[page_index].insert_image(rect, stream=blur_png(rect.width, rect.height, kind), keep_proportion=False)

        # Meta veri, XML meta veri, ekler, JavaScript, form alanları, bağlantılar, gizli metin.
        doc.scrub()
        _betikleri_temizle(doc)  # scrub katalogdaki OpenAction/AA betiklerini silmez
        doc.set_metadata({})
        if strip_bookmarks:
            doc.set_toc([])  # yer imi başlıkları kişisel veri taşıyabilir
        if watermark:
            _add_watermark(doc)

        tmp_fd, tmp_name = tempfile.mkstemp(suffix=dst.suffix, dir=dst.parent)
        os.close(tmp_fd)
        try:
            if image:
                save_doc_as_image(doc, Path(tmp_name))
            else:
                doc.save(tmp_name, garbage=4, deflate=True, clean=True)
            _verify_no_leak(tmp_name, included, scan.findings, scan.ocr_pages, image)
            if not image:
                scan.warnings.extend(
                    _verify_glyph_gaps(
                        tmp_name, boxes, {_normalize(f.finding.value) for f in included if f.kind == "metin"}
                    )
                )
                # Aynı konuyu söyleyen yer bazlı uyarı (etiket kısa / kutu tam genişlikte) zaten varsa genel uyarı tekrarlanmaz.
                if not any(("yerde yerine konan etiket" in w or "karartma kutusu değerin" in w) for w in scan.warnings):
                    scan.warnings.extend(_gap_width_warnings(included))
            scan.warnings.extend(_signature_leftover_warnings(tmp_name, sig_before))
            if drop:
                _drop_pages(tmp_name, drop, included, scan.findings)
            if password:
                _encrypt(tmp_name, password)
            os.replace(tmp_name, dst)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    finally:
        doc.close()

    if counts is not None:
        count_types(counts, (f.finding.type for f in included))
    return MaskResult(
        target=str(dst),
        masked=len(included),
        warnings=scan.warnings,
        dropped=len(drop),
        encrypted=bool(password),
        flattened=n_pages if flatten and not image else 0,
    )


def _betikleri_temizle(doc: pymupdf.Document) -> None:
    """Katalogdaki ve sayfalardaki JavaScript eylemlerini (OpenAction, AA, Names/JavaScript) siler.

    `Document.scrub()` yalnızca bağlantı ve form eylemlerini temizler; açılışta çalışan betik katalogda
    kalabilir ve içindeki değer çıktı dosyasında okunur. Silinen nesneler `garbage=4` ile dosyadan atılır.
    """
    cat = doc.pdf_catalog()
    for key in ("OpenAction", "AA"):
        if doc.xref_get_key(cat, key)[0] != "null":
            doc.xref_set_key(cat, key, "null")
    if doc.xref_get_key(cat, "Names")[0] != "null":
        names_type, names_val = doc.xref_get_key(cat, "Names")
        if names_type == "xref":
            names_xref = int(names_val.split()[0])
            if doc.xref_get_key(names_xref, "JavaScript")[0] != "null":
                doc.xref_set_key(names_xref, "JavaScript", "null")
        elif doc.xref_get_key(cat, "Names/JavaScript")[0] != "null":
            doc.xref_set_key(cat, "Names/JavaScript", "null")
    if doc.xref_get_key(cat, "AcroForm/XFA")[0] != "null":
        doc.xref_set_key(cat, "AcroForm/XFA", "null")  # XFA formları betik ve gönderme eylemi taşıyabilir
    for key in ("Names/EmbeddedFiles", "AF", "Collection"):
        if doc.xref_get_key(cat, key)[0] != "null":
            doc.xref_set_key(cat, key, "null")
    _tehlikeli_eylemleri_temizle(doc)


_TEHLIKELI_EYLEMLER = frozenset(
    {"Launch", "JavaScript", "SubmitForm", "ImportData", "ResetForm", "GoToR", "GoToE", "Rendition", "Movie", "Sound"}
)
_TEHLIKELI_ANAHTARLAR = ("AA", "JS", "EF", "RichMediaContent", "RichMediaSettings", "AF")


def _tehlikeli_eylemleri_temizle(doc: pymupdf.Document) -> None:
    """Tüm nesnelerde dış program/dosya çalıştıran eylemleri, gönderme eylemlerini ve gömülü dosyaları siler.

    Bağlantı (URI) ve belge içi gitme (GoTo) eylemleri kalır. Yetim kalan eylem nesneleri `garbage=4` ile atılır.
    """
    for xref in range(1, doc.xref_length()):
        try:
            keys = doc.xref_get_keys(xref)
            if "A" in keys and doc.xref_get_key(xref, "A/S")[1].lstrip("/") in _TEHLIKELI_EYLEMLER:
                doc.xref_set_key(xref, "A", "null")
            for key in _TEHLIKELI_ANAHTARLAR:
                if key in keys:
                    doc.xref_set_key(xref, key, "null")
            if doc.xref_get_key(xref, "S")[1].lstrip("/") in _TEHLIKELI_EYLEMLER:
                doc.update_object(xref, "<</Type/Action>>")
        except Exception:
            continue  # akış/özel nesne; eylem taşımaz


MIN_PASSWORD = 6

WATERMARK_TEXT = "MASKELİ KOPYA"
_WATERMARK_GRAY = (0.75, 0.75, 0.75)


def _add_watermark(doc: pymupdf.Document) -> None:
    """Her sayfanın ortasına köşegen, açık gri yazı koyar (okunabilirliği bozmasın diye soluk).

    Yerleşik Helvetica "İ" harfini çizmez: "I" yazılır, noktası ayrıca çizilir.
    """
    font = pymupdf.Font("helv")
    for page in doc:
        rect = page.rect
        size = max(12.0, min(rect.width, rect.height) / 9)
        width = font.text_length(WATERMARK_TEXT.replace("İ", "I"), fontsize=size)
        centre = pymupdf.Point(rect.width / 2, rect.height / 2)
        base_y = centre.y + size / 3
        morph = (centre, pymupdf.Matrix(-35))
        shape = page.new_shape()
        x = centre.x - width / 2
        for ch in WATERMARK_TEXT:
            plain = "I" if ch == "İ" else ch
            shape.insert_text(
                (x, base_y), plain, fontname="helv", fontsize=size, color=_WATERMARK_GRAY, morph=morph
            )
            w = font.text_length(plain, fontsize=size)
            if ch == "İ":
                dot = pymupdf.Point(x + w / 2, base_y - size * 0.82)
                shape.draw_circle(dot, size * 0.055)
                shape.finish(fill=_WATERMARK_GRAY, color=None, morph=morph)
            x += w
        shape.commit()



def _encrypt(path: str, password: str) -> None:
    """Denetlenmiş dosyayı parolayla şifreler (AES-256); açılıp açılmadığını denetler."""
    with _open(path) as doc:
        pages = doc.page_count
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=Path(path).parent)
        os.close(fd)
        try:
            doc.save(
                tmp,
                garbage=4,
                deflate=True,
                encryption=pymupdf.PDF_ENCRYPT_AES_256,
                owner_pw=password,
                user_pw=password,
                permissions=pymupdf.PDF_PERM_PRINT | pymupdf.PDF_PERM_ACCESSIBILITY,
            )
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    try:
        check = pymupdf.open(tmp)
        try:
            if not check.needs_pass or not check.authenticate(password) or check.page_count != pages:
                raise PdfError("Parolalı kopya doğrulanamadı. Dosya yazılmadı.")
        finally:
            check.close()
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _drop_pages(path: str, drop: list[int], included: list[PdfFinding], all_findings: list[PdfFinding]) -> None:
    """Maskelenip denetlenmiş dosyadan sayfaları siler ve yeniden denetler.

    Silinen sayfalardaki, kullanıcının açık bıraktığı değerler de artık kopyada olmamalı;
    başka sayfada da geçmiyorlarsa okunabiliyor olmaları kaçaktır.
    """
    keep_pages = {f.page for f in all_findings} - set(drop)
    with _open(path) as doc:
        doc.delete_pages([p - 1 for p in drop])
        fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=Path(path).parent)
        os.close(fd)
        try:
            doc.save(tmp, garbage=4, deflate=True, clean=True)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise
    try:
        kept_pages_values = {_normalize(f.finding.value) for f in all_findings if f.kind == "metin" and f.page in keep_pages}
        must_be_gone: dict[str, str] = {}
        for f in all_findings:
            v = _normalize(f.finding.value)
            if f.kind == "metin" and f.page in drop and v not in kept_pages_values:
                must_be_gone.setdefault(v, f.finding.type)
        for f in included:
            v = _normalize(f.finding.value)
            if f.kind == "metin" and v not in _normalize(f.replacement):
                must_be_gone.setdefault(v, f.finding.type)
        included_ids = {i.id for i in included}
        for f in all_findings:
            if f.id not in included_ids and f.page in keep_pages:
                must_be_gone.pop(_normalize(f.finding.value), None)
        with _open(tmp) as out:
            text = _normalize("".join(page.get_text("text", flags=_TEXT_FLAGS) for page in out))
        leaked = [tur for v, tur in must_be_gone.items() if v and v in text]
        if leaked:
            raise PdfError(kacak_iletisi(leaked, "kopyada"))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _remove_signature_strokes(doc: pymupdf.Document, strokes: list[PdfFinding]) -> None:
    """Kalemle atılmış imzanın çizgilerini siler.

    Normal redaction yalnızca bölgenin tamamen örttüğü çizimleri siler. MuPDF bunu
    sayfanın koordinat dönüşümünden önceki koordinatlarla ölçtüğü için, dönüşümlü
    sayfalarda içeride kalan imza bile "örtülmemiş" sayılabiliyor. Bölgeye yalnızca
    imza çizgileri dokunuyorsa "dokunanı sil" kipi güvenlidir: tablo çizgisi gibi
    başka bir çizim etkilenmez. Başka çizim dokunuyorsa normal yol izlenir; çizgi
    kalırsa kaçak denetimi dosyayı yazdırmaz.
    """
    by_page: dict[int, list[pymupdf.Rect]] = {}
    for f in strokes:
        page = doc[f.page - 1]
        region = f.rects[0]
        touching = [d for d in page.get_drawings() if pymupdf.Rect(d["rect"]).intersects(region)]
        if touching and all(is_stroke_drawing(d) and region.contains(pymupdf.Rect(d["rect"])) for d in touching):
            by_page.setdefault(f.page - 1, []).append(region)
    for index, regions in by_page.items():
        page = doc[index]
        for region in regions:
            page.add_redact_annot(region, fill=False, cross_out=False)
        # Bu geçişte yalnızca çizimler silinir; metin ve görseller asıl geçişte ele alınır.
        page.apply_redactions(
            images=pymupdf.PDF_REDACT_IMAGE_NONE,
            graphics=pymupdf.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
            text=pymupdf.PDF_REDACT_TEXT_NONE,
        )


def _signature_leftover_warnings(path: str, before: list) -> list[str]:
    """Girdideki imza bölgesi ile çıktıdaki aynı bölgeyi mürekkep pikseliyle karşılaştırır.

    Kalan iz kaçak sayılıp dosya durdurulmaz (OCR ve görsel imzada yanlış alarm olabilir); sonuca
    uyarı olarak yazılır, arayüz "iz kalmadı" demeden önce bunu gösterir. Karartma kutusu düz dolgu
    olduğu için mürekkep sayılmaz.
    """
    if not before:
        return []
    out = _open(path)
    try:
        pages = sorted(
            {
                f.page
                for f, snap in before
                if f.page <= out.page_count
                and (a := ink_snapshot(out[f.page - 1], f.rects[0])) is not None
                and ink_remaining(snap, a) > _KALAN_ORAN
            }
        )
    finally:
        out.close()
    if not pages:
        return []
    return [
        f"Sayfa {', '.join(map(str, pages))}: imza bölgesinde girdideki imza izleri çıktıda hâlâ görünüyor olabilir. "
        "Çıktıyı açıp imzanın silindiğini gözle kontrol edin."
    ]


# Uzunluğu zaten herkesçe bilinen türler; kutu genişliği bunlarda yeni bilgi vermez.
_FIXED_LENGTH_TYPES = frozenset({"tc_kimlik", "iban", "kredi_karti"})


@dataclass(frozen=True)
class _TailWord:
    text: str
    x0: float
    y_mid: float
    baseline: float
    size: float


def _tail_words(page: pymupdf.Page, rect: pymupdf.Rect) -> list[_TailWord]:
    """Silinecek kutunun aynı satırda sağında kalan sözcükleri, özgün konumlarıyla kaydeder."""
    clip = pymupdf.Rect(rect.x1 - 0.5, rect.y0, page.rect.x1, rect.y1)
    raw = page.get_text("rawdict", clip=clip, flags=_TEXT_FLAGS)
    out: list[_TailWord] = []
    for block in raw.get("blocks", []):
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                word: list[dict] = []
                for ch in [*span.get("chars", []), {"c": " ", "bbox": (0, 0, 0, 0)}]:
                    # Değere bitişik noktalama ("(TC),"): kutunun içindeki karakterler sağdaki parçaya katılmaz,
                    # yoksa parça kutunun içinden başlıyor sayılır ve kayınca geri konmazdı (yanlış "kayma" uyarısı).
                    if ch["c"].strip() and (ch["bbox"][0] + ch["bbox"][2]) / 2 < rect.x1 - 0.5:
                        word = []
                        continue
                    if ch["c"].strip():
                        word.append(ch)
                        continue
                    if word:
                        x0, y0, _, y1 = word[0]["bbox"]
                        if x0 >= rect.x1 - 0.5 and rect.y0 <= (y0 + y1) / 2 <= rect.y1:
                            out.append(
                                _TailWord(
                                    "".join(c["c"] for c in word), x0, (y0 + y1) / 2, span["origin"][1], span["size"]
                                )
                            )
                        word = []
    return out


def _restore_shifted(page: pymupdf.Page, tail: list[_TailWord]) -> list[str]:
    """Silme sonrası sola kayan sözcükleri özgün konumlarına geri koyar.

    MuPDF silinen glifin genişliği kadar sağdaki metni kaydırabilir. Kayan sözcükler silinip aynı
    yerde (yerleşik yazı tipiyle) yeniden yazılır; yazı tipi karakteri çizemiyorsa sözcük kayık kalır
    ve uyarı döner. Hiç kayma yoksa sayfaya dokunulmaz.
    """
    now = [(w[4], w[0], w[1], w[2], w[3]) for w in page.get_text("words")]
    used: set[int] = set()
    moved: list[tuple[_TailWord, pymupdf.Rect]] = []
    for word in tail:
        cands = [
            i
            for i, (text, _, y0, _, y1) in enumerate(now)
            if i not in used and text == word.text and y0 <= word.y_mid <= y1
        ]
        if not cands:
            continue  # silinmiş (başka bir bulgunun içinde)
        best = min(cands, key=lambda i: abs(now[i][1] - word.x0))
        used.add(best)
        if abs(now[best][1] - word.x0) > 0.5:
            moved.append((word, pymupdf.Rect(now[best][1:])))
    if not moved:
        return []
    font = pymupdf.Font("helv")
    fixable = [(w, r) for w, r in moved if all(font.has_glyph(ord(c)) for c in w.text)]
    if fixable:
        for _, rect in fixable:
            page.add_redact_annot(rect + (0.3, 0.3, -0.3, -0.3), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)
        for word, _ in fixable:
            page.insert_text((word.x0, word.baseline), word.text, fontname="helv", fontsize=word.size, color=(0, 0, 0))
    if len(fixable) < len(moved):
        return [
            f"Sayfa {page.number + 1}: silme sonrası kayan {len(moved) - len(fixable)} sözcük özgün konumuna "
            "geri konamadı (yazı tipi desteklemiyor). Kutu çevresindeki yazıyı gözle kontrol edin."
        ]
    return []


def _verify_glyph_gaps(path: str, boxes: list[tuple[int, pymupdf.Rect]], values: set[str] | None = None) -> list[str]:
    """Silinen kutuların içinde kalan glifleri denetler.

    Metin eşleştirmesi harf harf yerleştirilmiş ya da aralıklı yazılmış değerin artığını kaçırabilir.
    Kutuda kalan karakterler (normalleştirilmiş) maskelenen değerlerden birinin parçasıysa (en az 3
    karakter) dosya durdurulur. Aksi halde kalan glif komşu metindir: MuPDF silmeden sonra sağdaki
    metni kaydırabilir, bu kayma uyarı olarak döner.
    """
    if not boxes:
        return []
    out = _open(path)
    try:
        left = ""
        for page_index, rect in boxes:
            if page_index >= out.page_count:
                continue
            inner = rect + (0.5, 0.5, -0.5, -0.5)
            if inner.is_empty:
                continue
            raw = out[page_index].get_text("rawdict", clip=inner, flags=_TEXT_FLAGS)
            for block in raw.get("blocks", []):
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        for ch in span.get("chars", []):
                            cx = (ch["bbox"][0] + ch["bbox"][2]) / 2
                            cy = (ch["bbox"][1] + ch["bbox"][3]) / 2
                            if ch["c"].strip() and inner.x0 <= cx <= inner.x1 and inner.y0 <= cy <= inner.y1:
                                left += ch["c"]
    finally:
        out.close()
    if not left:
        return []
    norm = _normalize(left)
    if len(norm) >= 3 and any(norm in v for v in values or ()):
        raise PdfError(
            f"Kaçak tespiti: silinen kutuların içinde değerden {len(norm)} karakter (glif) kaldı. Dosya yazılmadı."
        )
    return [
        "Silinen kutunun içine komşu metinden glifler kaydı (silme sonrası metin kayması). "
        "Kutu çevresindeki yazıyı gözle kontrol edin."
    ]


def _gap_width_warnings(included: list[PdfFinding]) -> list[str]:
    """Kutu ve boşluk genişliği, sonraki metnin kayması değerin uzunluğunu ele verebilir.

    Değerin yerine kutu konduğunda sonraki metin yerinde kalır; kutu/boşluk genişliği değer
    uzunluğuyla orantılıdır. Uzunluğu değişken türlerde uyarı verilir.
    """
    pages = sorted(
        {
            f.page
            for f in included
            if f.kind == "metin" and f.rects and f.finding.type not in _FIXED_LENGTH_TYPES
        }
    )
    if not pages:
        return []
    return [
        f"Sayfa {', '.join(map(str, pages))}: kutu ve boşluk genişliği maskelenen değerin uzunluğunu "
        "ele verebilir. Uzunluk önemliyse çıktıyı gözle kontrol edin."
    ]


def _verify_no_leak(
    path: str,
    included: list[PdfFinding],
    all_findings: list[PdfFinding],
    ocr_pages: list[int] | None = None,
    image: bool = False,
) -> None:
    """Maskeli dosyada işaretli değerlerden biri hâlâ okunuyorsa durdurur.

    Kullanıcının bilerek dışarıda bıraktığı değerlerle aynı olanlar kontrol edilmez.
    OCR ile okunan sayfalar, kaydedilen dosyadan yeniden OCR ile okunarak denetlenir.
    """
    included_ids = {f.id for f in included}
    excluded = [f for f in all_findings if f.id not in included_ids]
    text_included = [f for f in included if f.kind == "metin"]
    kept = {_normalize(f.finding.value) for f in excluded if f.kind == "metin"}
    # Yerine yazılan metin değeri zaten içeriyorsa (ör. genelleştirilmiş "Istanbul" yine "Istanbul")
    # değer çıktıda bilerek bulunur; kaçak sayılmaz.
    must_be_gone: dict[str, str] = {}
    for f in text_included:
        v = _normalize(f.finding.value)
        if v not in _normalize(f.replacement) and v not in kept:
            must_be_gone.setdefault(v, f.finding.type)

    kept_digests = {f.image_digest for f in excluded if f.image_digest}
    gone_digests = {f.image_digest: f.finding.type for f in included if f.image_digest and f.image_digest not in kept_digests}
    strokes = [f for f in included if f.kind == "cizim"]
    areas = [f for f in included if f.kind == "alan"]
    faces = [f for f in included if f.kind == "yuz"]

    out = _open(path)
    try:
        text = _normalize("".join(page.get_text("text", flags=_TEXT_FLAGS) for page in out))
        for page_no in ocr_pages or []:
            page = out[page_no - 1]
            text += _normalize(page.get_text("text", textpage=ocr_textpage(page, image)))
        leaked = [tur for v, tur in must_be_gone.items() if v and v in text]
        if gone_digests:
            for page in out:
                leaked += [gone_digests[d] for info in page.get_image_info(hashes=True) if (d := info.get("digest")) in gone_digests]
        for f in areas:
            # Kenardaki harf parçaları sayılmasın diye alan biraz daraltılır.
            inner = f.rects[0] + (1, 1, -1, -1)
            if not inner.is_empty:
                kalan = out[f.page - 1].get_textbox(inner).strip()
                # Gerekçeli alanda yerine yazılan "[gerekçe]" etiketi kalması beklenir; başka yazı kaçaktır.
                if kalan and not (f.reason and _normalize(kalan) in _normalize(f.replacement)):
                    leaked.append(f.finding.type)
        for f in faces:
            # Yüz bölgesi silindiyse kaydedilen sayfada orada yüz bulunmamalı.
            if face_remains(out[f.page - 1], f.rects[0]):
                leaked.append(f.finding.type)
        for f in strokes:
            region = f.rects[0]
            leaked += [
                f.finding.type
                for d in out[f.page - 1].get_drawings()
                if is_stroke_drawing(d) and region.contains(pymupdf.Rect(d["rect"]))
            ]
    finally:
        out.close()
    if leaked:
        raise PdfError(kacak_iletisi(leaked))
