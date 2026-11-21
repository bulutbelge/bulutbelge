"""Türk GİB e-Fatura / e-Arşiv (PDF ve imzalı UBL XML) tespiti.

PDF düzeni ile UBL-TR XML ağaç yapısından şu alanları çıkarır:
- Alıcı / satıcı kurum unvanı (`kurum_unvani`)
- Alıcı / satıcı açık adresi (`adres`)
- Tutarlar, birim fiyatlar ve yazıyla ("Yalnız ...") tutarlar (`tutar`)
- VKN, TCKN, Vergi Dairesi (`vergi_dairesi`), MERSİS (`mersis`), Ticaret Sicil (`ticaret_sicil`)
- Banka / şube / hesap bilgisi (`banka_bilgisi`) ve IBAN (`iban`)
- ETTN / XML XAdES dijital imza alanları (`ettn`) ile PDF e-Fatura QR karekodu (`imza`)
"""

from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Callable

import pymupdf
from PIL import Image

from .detect import HIGH, LOW, MEDIUM, Finding
from .extra_types import address_province, find_addresses, find_amounts
from .rules import Rules
from .signatures import SignatureRegion
from .validators import digits_only, iban_valid, tc_kimlik_valid, vkn_valid
from .xmltok import iter_tokens

# ---------- Ortak e-Fatura yardımcıları ----------

_EFATURA_MARKER = re.compile(
    r"(?i)(?:\be-?fatura\b|\bettn\b|senaryo\s*:|fatura\s+tipi\s*:|özelleştirme\s+no|ozellestirme\s+no)"
)
_UUID_RE = re.compile(
    r"(?<![A-Za-z0-9\-])[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?![A-Za-z0-9\-])",
    re.IGNORECASE,
)

# Kurum unvanı sonekleri (hem noktalı/kısaltmalı hem açık yazılışlar).
_CORP_SUFFIX = re.compile(
    r"(?i)(?<![\w.])(?:"
    r"A\.?\s*Ş\.?"
    r"|ANON[İI]M\s+[ŞS][İI]RKET[İI]"
    r"|L[İI]M[İI]TED\s+[ŞS][İI]RKET[İI]"
    r"|LTD\.?\s*(?:[ŞS]T[İI]|STI)\.?"
    r"|KOLL\.?\s*[ŞS]T[İI]\.?"
    r"|HOLD[İI]NG"
    r"|KOOPERAT[İI]F[İI]|KOOP\.?"
    r")(?![\w])"
)
_CORP_PARTIAL_END = re.compile(r"(?i)\b(?:LTD\.?|SAN\.?|T[İI]C\.?|VE)$")
_CORP_CONT_LINE = re.compile(r"^\s*(?:[ŞS]T[İI]|STI|A\.?[ŞS]\.?|[ŞS][İI]RKET[İI])\.?\s*$")

_ADDR_HINT = re.compile(
    r"(?i)\b(?:MAH(?:ALLE(?:S[İI])?)?\.?|CAD(?:DE(?:S[İI])?)?\.?|SOK(?:AK|AĞ[İI])?\.?|SK\.?"
    r"|BULV(?:ARI)?\.?|BLV\.?|OSB|SANAY[İI]|S[İI]TE(?:S[İI])?|B[ÖO]LGE(?:S[İI])?"
    r"|PLAZA|BLOK|APT\.?|NO\s*:|PK\b|\d{5})\b|[^\s/]\s*/\s*[^\s/]"
)
_LABEL_LINE = re.compile(
    r"(?i)^\s*(?:SAYIN|VERG[İI]\s+DA[İI]RES[İI]|V\.?D\.?|VKN|TCKN|MERS[İI]S|T[İI]CARET\s+S[İI]C[İI]L"
    r"|TEL(?:EFON)?|FAKS|FAX|WEB|E-?POSTA|SENARYO|FATURA\s+(?:NO|T[İI]P[İI]|TAR[İI]H[İI])"
    r"|ETTN|BANKA\s+HESAP|ÖDEME|IBAN|E-?FATURA|[ÖO]ZELLE[ŞS]T[İI]RME|MAL\s*/?\s*H[İI]ZMET)\b\s*:?"
)
_HEADER_STOP = re.compile(
    r"(?i)^\s*(?:VERG[İI]\s+DA[İI]RES[İI]|V\.?D\.?|VKN|TCKN|TEL(?:EFON)?|FAKS|FAX|WEB|E-?POSTA"
    r"|MERS[İI]S|T[İI]CARET\s+S[İI]C[İI]L|SENARYO|FATURA|ETTN|BANKA|IBAN|SAYIN)\b"
)

_VD_RE = re.compile(
    r"(?i)(?<![\w])(?:Vergi\s+Dairesi|V\.?D\.?)(?!\s*(?:No|Numaras[ıi]))\s*[:.\-]?\s*"
    r"([^\r\n:;|]{2,55}?)(?=\s+(?:VKN|TCKN|Vergi\s*(?:No|Kimlik|Numaras[ıi])|Tel|Faks|Fax|E-?Posta|Web|Mersis|Ticaret)\b|[;\r\n]|$)"
)
_TS_RE = re.compile(
    r"(?i)(?<![\w])Ticaret\s+Sicil(?:\s*(?:No\.?|Numaras[ıi]))?\s*[:.#\-]?\s*"
    r"((?=[A-Z0-9\-/]*\d)[A-Z0-9][A-Z0-9\-/]{1,24})(?![\w])"
)
_BANK_SLASH_RE = re.compile(
    r"(?i)([^\r\n;:/]{2,48}?\bBANK(?:ASI|A)?(?:\s*A\.?\s*Ş\.?)?[^\S\r\n]*/"
    r"[^\S\r\n]*[^\r\n/]{2,48}?(?:ŞB\.?|ŞUBES[İI]|SUBE\w*))(?=\s*(?:/\s*IBAN|\bIBAN|\bTR\s*\d{2}|[\r\n;]|$))"
)
_BANK_LABEL_RE = re.compile(
    r"(?i)(?<![\w])(?:Banka\s*(?:Ad[ıi]|Hesap\s*(?:Ad[ıi]|Bilgileri))|Şube\s*(?:Ad[ıi]|Kodu)|Hesap\s*(?:No\.?|Numaras[ıi]))"
    r"\s*[:.\-]?\s*([^\r\n;]{2,60}?)(?=\s+(?:IBAN|Hesap|Şube|Banka)\b|[\r\n;]|$)"
)
_WEB_LABEL_RE = re.compile(
    r"(?i)(?<![\w])Web\s*(?:Adresi|Sitesi)?\s*[:.]\s*"
    r"((?:https?://)?(?:www\.)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S*)?)"
)
_YALNIZ_RE = re.compile(
    r"(?i)(?<![\w])(?:Yaln[ıi]z|Yanl[ıi]z)\s*:?\s*([^\r\n]{4,140})"
)
_WRITTEN_CURRENCY_ONLY = re.compile(
    r"(?i)(?:\b(?:TL|TRY|EUR|Euro|USD|Dolar|Kuru[şs]|Kr[şs]?|Cent|Türk\s+Liras[ıi])\b|€)"
)
_WRITTEN_NUM_WORD = re.compile(
    r"(?i)(?:Sıfır|Bir|İki|Üç|Dört|Beş|Altı|Yedi|Sekiz|Dokuz|On|Yirmi|Otuz|Kırk|Elli|Altmış|Yetmiş|Seksen|Doksan|Yüz|Bin|Milyon)"
)
_WRITTEN_PURE_TOKEN = re.compile(
    r"^(?:yalnız|yanlız|sıfır|bir|iki|üç|dört|beş|altı|yedi|sekiz|dokuz|"
    r"on|yirmi|otuz|kırk|elli|altmış|yetmiş|seksen|doksan|yüz|bin|milyon|milyar|"
    r"tl|try|türk|lirası|lira|kuruş|krş|kr|eur|euro|cent|usd|dolar|ve|€|\$)+$"
)
_WRITTEN_AMT_HINT = re.compile(
    r"(?i)(?:\b(?:TL|TRY|EUR|Euro|USD|Dolar|Kuru[şs]|Kr[şs]?|Türk\s+Liras[ıi])\b"
    r"|(?:Sıfır|Bir|İki|Üç|Dört|Beş|Altı|Yedi|Sekiz|Dokuz|On|Yirmi|Otuz|Kırk|Elli|Altmış|Yetmiş|Seksen|Doksan|Yüz|Bin|Milyon))"
)
_SAYIN_RE = re.compile(r"(?im)^[^\S\r\n]*SAYIN\b\s*:?[^\S\r\n]*(.*)$")
_BANK_TABLE_HDR = re.compile(r"(?i)\bBANKA(?:\s+ADI)?\b")
_CUR_ONLY = re.compile(r"^\s*(?:TL|TRY|EUR|USD|GBP|CHF)\s*$", re.IGNORECASE)
_IBAN_LINE = re.compile(r"^\s*TR\s*\d", re.IGNORECASE)


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _line_spans(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    pos = 0
    for raw in text.splitlines(keepends=True):
        s, e = _trim_span(text, pos, pos + len(raw))
        out.append((s, e, text[s:e]))
        pos += len(raw)
    return out


# ---------- Metin / PDF e-Fatura çıkarımı ----------


def find_efatura_text_findings(text: str, enabled: Callable[[str], bool]) -> list[Finding]:
    """PDF ve düz metin e-Faturalardaki kurum/fatura alanlarını bulur."""
    out: list[Finding] = []
    is_invoice = bool(_EFATURA_MARKER.search(text))

    if enabled("ettn"):
        for m in _UUID_RE.finditer(text):
            out.append(Finding("ettn", m.start(), m.end(), m.group(), HIGH))

    if enabled("ticaret_sicil"):
        for m in _TS_RE.finditer(text):
            s, e = _trim_span(text, m.start(1), m.end(1))
            if e > s:
                out.append(Finding("ticaret_sicil", s, e, text[s:e], HIGH))

    if enabled("vergi_dairesi"):
        for m in _VD_RE.finditer(text):
            s, e = _trim_span(text, m.start(1), m.end(1))
            val = text[s:e].strip(" .:-")
            if e > s and re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü]{2}", val) and not _HEADER_STOP.match(val):
                e = s + len(val)
                out.append(Finding("vergi_dairesi", s, e, val, HIGH))

    if enabled("banka_bilgisi"):
        out.extend(_find_bank_text(text, is_invoice))

    if enabled("tutar"):
        for m in _YALNIZ_RE.finditer(text):
            s, e = _trim_span(text, m.start(1), m.end(1))
            val = text[s:e]
            if e > s and _WRITTEN_AMT_HINT.search(val):
                out.append(Finding("tutar", s, e, val, HIGH))
        if is_invoice:
            for ls, le, ln in _line_spans(text):
                if le <= ls or not _WRITTEN_CURRENCY_ONLY.search(ln) or not _WRITTEN_NUM_WORD.search(ln):
                    continue
                tokens = [re.sub(r"[.,:;()]", "", w).replace("İ", "i").replace("I", "ı").lower() for w in ln.split()]
                tokens = [tok for tok in tokens if tok]
                if len(tokens) >= 2 and all(_WRITTEN_PURE_TOKEN.match(tok) for tok in tokens):
                    out.append(Finding("tutar", ls, le, ln, HIGH))

    if enabled("kurum_unvani"):
        out.extend(_find_unvan_text(text, is_invoice))

    if enabled("adres") and is_invoice:
        out.extend(_find_invoice_addresses(text))

    return out


def _find_bank_text(text: str, is_invoice: bool) -> list[Finding]:
    out: list[Finding] = []
    for m in _BANK_SLASH_RE.finditer(text):
        s, e = _trim_span(text, m.start(1), m.end(1))
        if e > s:
            out.append(Finding("banka_bilgisi", s, e, text[s:e], HIGH))
    for m in _BANK_LABEL_RE.finditer(text):
        s, e = _trim_span(text, m.start(1), m.end(1))
        val = text[s:e]
        if e > s and val.upper() not in {"ŞUBE", "HESAP NO", "IBAN", "DÖVİZ CİNSİ", "HESAP NO / DÖVİZ CİNSİ"}:
            if not val.upper().startswith(("ŞUBE", "IBAN", "HESAP NO")):
                out.append(Finding("banka_bilgisi", s, e, val, MEDIUM))
    if not is_invoice:
        return out

    # Tablo düzenindeki banka listesi ("BANKA ADI / ŞUBE / ... / IBAN" sütunları alt alta).
    lines = _line_spans(text)
    i = 0
    while i < len(lines):
        _, _, ln = lines[i]
        if _BANK_TABLE_HDR.search(ln):
            # Sonraki 10 satır içinde "IBAN" başlığı varsa tablo gövdesine gir.
            iban_hdr = next(
                (j for j in range(i + 1, min(i + 12, len(lines))) if lines[j][2].strip().upper() == "IBAN"),
                None,
            )
            if iban_hdr is not None:
                j = iban_hdr + 1
                pending: list[tuple[int, int, str]] = []
                while j < min(iban_hdr + 60, len(lines)):
                    ls, le, row = lines[j]
                    if not row:
                        if pending and _HEADER_STOP.match(row):
                            break
                        j += 1
                        continue
                    if _IBAN_LINE.match(row):
                        for ps, pe, pval in pending:
                            out.append(Finding("banka_bilgisi", ps, pe, pval, MEDIUM))
                        pending.clear()
                    elif _CUR_ONLY.match(row):
                        pass
                    elif _HEADER_STOP.match(row) or len(pending) >= 4:
                        break
                    else:
                        pending.append((ls, le, row))
                    j += 1
                i = j
                continue
        i += 1
    return out


_PROSE_NOISE = re.compile(
    r"(?i)(?:@|\b\d{6,}\b|\b(?:TC\s*K[İI]ML[İI]K|TCKN|VKN|IBAN|TEL(?:EFON)?|E-?POSTA)\b)"
)


def _find_unvan_text(text: str, is_invoice: bool) -> list[Finding]:
    out: list[Finding] = []
    lines = _line_spans(text)

    # 1. SAYIN bloğu (alıcı unvanı — fatura başlığı dışındaki "Sayın Kişi, ..." cümlelerini yakalama)
    for idx, (ls, le, ln) in enumerate(lines):
        m = _SAYIN_RE.match(ln)
        if not m:
            continue
        first_rest = m.group(1).strip()
        if first_rest and not _HEADER_STOP.match(first_rest) and not _ADDR_HINT.search(first_rest):
            has_corp = bool(_CORP_SUFFIX.search(first_rest))
            if (is_invoice and not _PROSE_NOISE.search(first_rest)) or has_corp:
                s = ls + ln.index(first_rest)
                e = s + len(first_rest)
                out.append(Finding("kurum_unvani", s, e, text[s:e], HIGH))
            continue
        start_s = end_e = None
        for k in range(idx + 1, min(idx + 4, len(lines))):
            cs, ce, cln = lines[k]
            if not cln or _HEADER_STOP.match(cln) or _ADDR_HINT.search(cln):
                break
            if start_s is None:
                start_s = cs
            end_e = ce
            if not _CORP_PARTIAL_END.search(cln):
                # İkinci satır sadece ŞTİ./A.Ş. devamıysa aşağıda dahil edilecek; değilse sonraki satıra bak.
                if k + 1 < len(lines) and _CORP_CONT_LINE.match(lines[k + 1][2]):
                    continue
                break
        if start_s is not None and end_e is not None and end_e > start_s:
            cand_unvan = text[start_s:end_e]
            if is_invoice or _CORP_SUFFIX.search(cand_unvan):
                out.append(Finding("kurum_unvani", start_s, end_e, cand_unvan, HIGH))

    # 2. Kurumsal unvan sonekleri (A.Ş., LTD. ŞTİ., ANONİM ŞİRKETİ...)
    for idx, (ls, le, ln) in enumerate(lines):
        if not ln or _HEADER_STOP.match(ln):
            continue
        if _CORP_SUFFIX.search(ln) or (_CORP_PARTIAL_END.search(ln) and idx + 1 < len(lines) and _CORP_CONT_LINE.match(lines[idx + 1][2])):
            # Başlangıçta etiket ("Ünvan:") varsa etiket kısmını atla.
            head = ln.split(":", 1)[1] if ":" in ln and len(ln.split(":", 1)[0]) < 25 else ln
            s = ls + ln.index(head.lstrip())
            e = le
            if _CORP_PARTIAL_END.search(ln) and idx + 1 < len(lines) and _CORP_CONT_LINE.match(lines[idx + 1][2]):
                e = lines[idx + 1][1]
            out.append(Finding("kurum_unvani", s, e, text[s:e], HIGH))

    if not is_invoice:
        return out

    # 3. Satıcı başlık bloğu: adres / Vergi Dairesi satırlarının üstündeki unvan satırı
    for idx, (ls, le, ln) in enumerate(lines):
        if not re.match(r"(?i)^\s*Vergi\s+Dairesi\s*:", ln):
            continue
        # Yukarıdaki adres satırlarının üstüne çık
        k = idx - 1
        while k >= max(0, idx - 8):
            _, _, prev = lines[k]
            if not prev or prev.casefold().strip() in ("türkiye", "turkiye", "turkey"):
                k -= 1
                continue
            if (
                _ADDR_HINT.search(prev)
                or (address_province(prev) is not None and len(prev) <= 45)
                or re.match(r"(?i)^\s*(?:Tel|Faks|Fax|Web|E-?Posta|No|Bina|Kapı)\b", prev)
            ):
                k -= 1
                continue
            break
        if 0 <= k < idx - 1:
            cs, ce, cand = lines[k]
            if (
                cand
                and not _LABEL_LINE.match(cand)
                and not _HEADER_STOP.match(cand)
                and not _IBAN_LINE.match(cand)
                and "IBAN" not in cand.upper()
                and len(cand.split()) >= 2
                and sum(c.isalpha() for c in cand) >= 5
            ):
                out.append(Finding("kurum_unvani", cs, ce, cand, MEDIUM))

    # 4. Şirket web adresi (GİB / e-Fatura hariç)
    for m in _WEB_LABEL_RE.finditer(text):
        s, e = _trim_span(text, m.start(1), m.end(1))
        val = text[s:e]
        if e > s and "gib.gov.tr" not in val.casefold() and "efatura.gov.tr" not in val.casefold():
            out.append(Finding("kurum_unvani", s, e, val, MEDIUM))

    return out


def _find_invoice_addresses(text: str) -> list[Finding]:
    """e-Fatura'da Vergi Dairesi üstündeki çok satırlı açık adres bloklarını yakalar."""
    out: list[Finding] = []
    lines = _line_spans(text)
    for idx, (_ls, _le, ln) in enumerate(lines):
        if not re.match(r"(?i)^\s*Vergi\s+Dairesi\s*:", ln):
            continue
        addr_indices: list[int] = []
        for k in range(idx - 1, max(-1, idx - 9), -1):
            _, _, cur = lines[k]
            if not cur:
                continue
            if cur.casefold().strip() in ("türkiye", "turkiye", "turkey"):
                continue
            if _HEADER_STOP.match(cur) or _CORP_SUFFIX.search(cur):
                if re.match(r"(?i)^\s*SAYIN\b", cur):
                    break
                if re.match(r"(?i)^\s*(?:E-?Posta|Web|Tel|Fax|Faks|Bina|Kapı)\b", cur):
                    if addr_indices:
                        continue
                    continue
                break
            if re.match(r"(?i)^\s*(?:Bina\s*No|Kapı\s*No)\s*:?", cur):
                if addr_indices:
                    addr_indices.append(k)
                continue
            is_city_tail = not addr_indices and address_province(cur) is not None and len(cur) <= 45
            if _ADDR_HINT.search(cur) or is_city_tail or (
                addr_indices and re.match(r"^\s*(?:NO:|Kat|Daire|\d{5}\b|[\wÇĞİÖŞÜçğıöşü]+/?$)", cur, re.I)
            ):
                addr_indices.append(k)
            elif addr_indices:
                break
        if addr_indices:
            addr_indices.reverse()
            s = lines[addr_indices[0]][0]
            e = lines[addr_indices[-1]][1]
            if e > s:
                out.append(Finding("adres", s, e, text[s:e], HIGH))
    return out


# ---------- PDF QR / karekod ve şirket logosu ----------


def _image_bw_saturation(doc: pymupdf.Document, xref: int) -> tuple[float, float] | None:
    """Görselin siyah/beyaz kontrast oranını ve renk doygunluğu payını hesaplar."""
    try:
        info = doc.extract_image(xref)
        if not info or not info.get("image"):
            return None
        with Image.open(io.BytesIO(info["image"])) as im:
            gray = im.convert("L")
            gpx = list(gray.get_flattened_data() if hasattr(gray, "get_flattened_data") else gray.getdata())
            if not gpx:
                return None
            bw = sum(1 for v in gpx if v < 50 or v > 205) / len(gpx)
            rgb = im.convert("RGB")
            rpx = list(rgb.get_flattened_data() if hasattr(rgb, "get_flattened_data") else rgb.getdata())
            sat = sum(1 for r, g, b in rpx if max(r, g, b) - min(r, g, b) > 25) / len(rpx)
            return bw, sat
    except Exception:
        return None


def find_efatura_visuals(page: pymupdf.Page, rules: Rules, page_text: str) -> list[tuple[str, SignatureRegion]]:
    """e-Fatura PDF sayfasındaki QR karekodu (`imza`) ve üstteki firma logosunu (`kurum_unvani`) bulur."""
    if not _EFATURA_MARKER.search(page_text) and not rules.types["ettn"].enabled:
        return []
    images = page.get_image_info(hashes=True, xrefs=True)
    if not images:
        return []
    page_area = abs(page.rect) or 1.0
    out: list[tuple[str, SignatureRegion]] = []
    qr_xrefs: set[int] = set()

    for info in images:
        xref = int(info.get("xref") or 0)
        w, h = float(info.get("width") or 0), float(info.get("height") or 0)
        rect = pymupdf.Rect(info["bbox"]) & page.rect
        if not xref or w <= 0 or h <= 0 or rect.is_empty:
            continue
        if abs(rect) / page_area > 0.15:
            continue
        px_ratio = w / h
        box_ratio = rect.width / (rect.height or 1.0)
        is_square = 0.88 <= px_ratio <= 1.14 and 0.88 <= box_ratio <= 1.14
        stats = _image_bw_saturation(page.parent, xref)

        if rules.types["imza"].enabled and is_square and w >= 50 and 30 <= rect.width <= 220:
            if stats and stats[0] >= 0.85 and stats[1] <= 0.08:
                qr_xrefs.add(xref)
                out.append(
                    ("imza", SignatureRegion(rect, "gorsel", "e-Fatura QR", info.get("digest"), xref))
                )
                continue

        # İlk sayfada üst bölümdeki firma logosunu gizle (renkli GİB amblemini koru).
        if rules.types["kurum_unvani"].enabled and page.number == 0 and rect.y1 <= page.rect.height * 0.30:
            is_gib_emblem = is_square and w <= 160 and (stats is not None and stats[1] > 0.18)
            if not is_gib_emblem and xref not in qr_xrefs:
                out.append(
                    ("kurum_unvani", SignatureRegion(rect, "gorsel", "Firma logosu", info.get("digest"), xref))
                )
    return out


# ---------- UBL-TR XML Anlamsal Tarama ----------

# Öznitelik: boşluklardan sonra boşluk olmayan bir karakterle başlar; böylece boşluk dizisi tek biçimde
# bölünür (eski `\s+[^<>"']*` kapanmayan etikette üstel geri izliyordu, güvenlik taraması F1/F2).
# Yorum, CDATA ve işleme talimatı `xmltok.iter_tokens` ile doğrusal taranır.
_TOKEN = re.compile(
    r"<!--(?P<comment>.*?)-->"
    r"|<!\[CDATA\[(?P<cdata>.*?)\]\]>"
    r"|<\?.*?\?>"
    r"|(?P<tag><(?P<close>/)?(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)(?P<attrs>(?:\s+[^<>\"'\s][^<>\"']*(?:\"[^\"]*\"|'[^']*'))*)\s*(?P<self>/)?>)",
    re.DOTALL,
)
_ATTR = re.compile(r"([A-Za-z_][A-Za-z0-9_.:-]*)\s*=\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)')")
_HEX_B64 = re.compile(r"^[A-Za-z0-9+/=\s]{80,}$")

_PARTY_CONTAINERS = frozenset(
    {
        "AccountingSupplierParty",
        "AccountingCustomerParty",
        "BuyerCustomerParty",
        "SellerSupplierParty",
        "AgentParty",
        "SignatoryParty",
        "AccountingPayeeParty",
    }
)
_ADDR_LEAF_TAGS = frozenset(
    {
        "StreetName",
        "AdditionalStreetName",
        "BuildingName",
        "BuildingNumber",
        "BlockName",
        "Floor",
        "Room",
        "PlotIdentification",
        "Postbox",
        "District",
        "Region",
        "CitySubdivisionName",
        "CityName",
        "PostalZone",
    }
)
_SIGNATURE_LEAF_TAGS = frozenset(
    {
        "SignatureValue",
        "DigestValue",
        "X509IssuerName",
        "X509SubjectName",
        "X509SerialNumber",
        "SigningTime",
        "SigningTimeStamp",
    }
)
_ADR_AMOUNT_TYPES = frozenset(
    {
        "LINEEXTENSIONAMOUNT",
        "TAXINCLUSIVEAMOUNT",
        "TAXEXCLUSIVEAMOUNT",
        "ALLOWANCETOTALAMOUNT",
        "PAYABLEAMOUNT",
    }
)
_FREE_TEXT_TAGS = frozenset({"Note", "Description", "InstructionNote", "AllowanceChargeReason", "Name", "Line", "ID"})
_TECH_CODE_PARENTS = frozenset(
    {
        "SellersItemIdentification",
        "BuyersItemIdentification",
        "ManufacturersItemIdentification",
        "StandardItemIdentification",
        "TaxCategory",
        "TaxScheme",
        "Country",
        "Signature",
        "Reference",
        "SignedInfo",
        "SignedProperties",
        "QualifyingProperties",
        "DigitalSignatureAttachment",
        "ExternalReference",
    }
)
_TECH_EXACT_TAGS = frozenset(
    {
        "UBLVersionID",
        "CustomizationID",
        "ProfileID",
        "CopyIndicator",
        "InvoiceTypeCode",
        "DocumentCurrencyCode",
        "TaxCurrencyCode",
        "PricingCurrencyCode",
        "PaymentCurrencyCode",
        "CalculationRate",
        "SourceCurrencyCode",
        "TargetCurrencyCode",
        "LineCountNumeric",
        "TaxTypeCode",
        "Percent",
        "InvoicedQuantity",
        "CalculationSequenceNumeric",
        "ChargeIndicator",
        "MultiplierFactorNumeric",
        "IssueDate",
        "IssueTime",
        "PaymentDueDate",
        "DocumentType",
        "DocumentTypeCode",
        "MimeType",
        "Encoding",
        "IdentificationCode",
    }
)


_TECH_ATTRS = frozenset(
    {
        "Id",
        "Target",
        "URI",
        "Algorithm",
        "mimeCode",
        "encodingCode",
        "characterSetCode",
        "unitCode",
        "currencyID",
        "schemeID",
        "listID",
        "listName",
        "listAgencyName",
        "listVersionID",
        "ObjectReference",
        "schemaLocation",
    }
)


def _local(name: str) -> str:
    return name.rsplit(":", 1)[-1]


def is_ubl_xml(text: str) -> bool:
    return bool(re.search(r"<(?:\w+:)?(?:Invoice|CreditNote|DespatchAdvice|ApplicationResponse)\b", text[:4000]))


@dataclass
class _XmlNode:
    tag: str
    path: tuple[str, ...]
    attrs: dict[str, str]
    text_spans: list[tuple[int, int]]
    attr_spans: list[tuple[str, int, int]]
    adr_group: int


def scan_ubl_xml(text: str, rules: Rules, hints: frozenset[str], lead: bool) -> tuple[list[Finding], list[tuple[int, int]]]:
    """UBL e-Fatura XML içeriğini anlamsal etiket + nitelik bazında tarar.

    Dönüş: `(findings, embedded_spans)`.
    """
    from .detect import detect

    def enabled(key: str) -> bool:
        return rules.types[key].enabled

    stack: list[tuple[str, dict[str, str], int]] = []
    nodes: list[_XmlNode] = []
    adr_meta: dict[int, dict[str, str]] = {}
    adr_seq = 0
    pos = 0
    embedded: list[tuple[int, int]] = []
    free_findings: list[Finding] = []
    semantic: list[Finding] = []

    for m in iter_tokens(_TOKEN, text):
        if m.start() > pos and stack:
            seg = text[pos:m.start()]
            if seg.strip():
                top_tag, top_attrs, top_adr = stack[-1]
                cur_path = tuple(t for t, _, _ in stack)
                nodes.append(_XmlNode(top_tag, cur_path, top_attrs, [(pos, m.start())], [], top_adr))
                if top_adr and top_tag in ("DocumentType", "DocumentTypeCode"):
                    adr_meta.setdefault(top_adr, {})[top_tag] = seg.strip()
        if m.group("comment") is not None:
            cs, ce = m.span("comment")
            if text[cs:ce].strip():
                free_findings.extend(_run_shifted(text[cs:ce], cs, rules, hints, lead))
        elif m.group("cdata") is not None:
            cs, ce = m.span("cdata")
            if text[cs:ce].strip():
                free_findings.extend(_run_shifted(text[cs:ce], cs, rules, hints, lead))
        elif m.group("tag") is not None:
            local_tag = _local(m.group("name"))
            is_close = bool(m.group("close"))
            is_self = bool(m.group("self"))
            if is_close:
                while stack:
                    popped_tag, _, _ = stack.pop()
                    if popped_tag == local_tag:
                        break
            else:
                attrs: dict[str, str] = {}
                attr_spans: list[tuple[str, int, int]] = []
                base = m.start("attrs")
                for a in _ATTR.finditer(m.group("attrs") or ""):
                    ak = _local(a.group(1))
                    grp = "dq" if a.group("dq") is not None else "sq"
                    av_s, av_e = base + a.start(grp), base + a.end(grp)
                    attrs[ak] = a.group(grp)
                    attr_spans.append((ak, av_s, av_e))
                if local_tag == "AdditionalDocumentReference":
                    adr_seq += 1
                    cur_adr = adr_seq
                else:
                    cur_adr = stack[-1][2] if stack else 0
                cur_path = tuple(t for t, _, _ in stack) + (local_tag,)
                if attr_spans:
                    nodes.append(_XmlNode(local_tag, cur_path, attrs, [], attr_spans, cur_adr))
                if not is_self:
                    stack.append((local_tag, attrs, cur_adr))
        pos = m.end()

    for node in nodes:
        for ak, av_s, av_e in node.attr_spans:
            val = text[av_s:av_e]
            if not val.strip():
                continue
            if node.tag == "EmbeddedDocumentBinaryObject" and ak == "filename" and enabled("ettn"):
                # Gömülü XSLT dosya adı fatura/ETTN izi taşıyabilir.
                for u in _UUID_RE.finditer(val):
                    semantic.append(Finding("ettn", av_s + u.start(), av_s + u.end(), u.group(), HIGH))
                continue
            if ak not in _TECH_ATTRS and not ak.startswith("xmlns"):
                free_findings.extend(_run_shifted(val, av_s, rules, hints, lead))

        for ts, te in node.text_spans:
            s, e = _trim_span(text, ts, te)
            if e <= s:
                continue
            val = text[s:e]
            path_set = set(node.path)
            parent = node.path[-2] if len(node.path) >= 2 else ""

            if (
                node.tag in ("EmbeddedDocumentBinaryObject", "X509Certificate") and _HEX_B64.fullmatch(val)
            ) or (len(val) >= 1000 and _HEX_B64.fullmatch(val)):
                embedded.append((s, e))
                continue

            # İmza sertifika/özet alanları
            if "Signature" in path_set and node.tag in _SIGNATURE_LEAF_TAGS:
                if enabled("ettn"):
                    semantic.append(Finding("ettn", s, e, val, HIGH))
                continue

            if node.tag == "Note" and enabled("tutar") and _WRITTEN_CURRENCY_ONLY.search(val) and _WRITTEN_NUM_WORD.search(val):
                # Yazıyla tutar notu (ör. "Yalnız ... TL ..." veya "... € ... cent")
                m_y = _YALNIZ_RE.search(val)
                if m_y:
                    ys, ye = _trim_span(val, m_y.start(1), m_y.end(1))
                    if ye > ys:
                        semantic.append(Finding("tutar", s + ys, s + ye, val[ys:ye], HIGH))
                        continue
                semantic.append(Finding("tutar", s, e, val, HIGH))
                continue

            # UUID / ETTN
            if node.tag == "UUID":
                if enabled("ettn"):
                    semantic.append(Finding("ettn", s, e, val, HIGH))
                continue

            # Taraf kimlik/unvan/adres/vergi dairesi
            in_party = bool(path_set & _PARTY_CONTAINERS)
            if in_party:
                if node.tag in ("Name", "RegistrationName") and parent in ("PartyName", "PartyLegalEntity"):
                    if enabled("kurum_unvani"):
                        semantic.append(Finding("kurum_unvani", s, e, val, HIGH))
                    continue
                if node.tag == "WebsiteURI":
                    if enabled("kurum_unvani") and "gib.gov.tr" not in val.casefold() and "efatura.gov.tr" not in val.casefold():
                        semantic.append(Finding("kurum_unvani", s, e, val, MEDIUM))
                    continue
                if node.tag in ("FirstName", "FamilyName", "MiddleName") and parent == "Person":
                    if enabled("kisi_adi"):
                        semantic.append(Finding("kisi_adi", s, e, val, HIGH))
                    continue
                if node.tag == "Name" and parent == "TaxScheme" and "PartyTaxScheme" in path_set:
                    if enabled("vergi_dairesi"):
                        semantic.append(Finding("vergi_dairesi", s, e, val, HIGH))
                    continue
                if node.tag == "ID" and parent == "PartyIdentification":
                    scheme = node.attrs.get("schemeID", "").upper()
                    _emit_scheme_id(semantic, scheme, s, e, val, enabled)
                    continue
                if "PostalAddress" in path_set and parent != "Country":
                    if node.tag in _ADDR_LEAF_TAGS:
                        if node.tag == "PostalZone" and set(val) <= {"0"}:
                            continue
                        if enabled("adres"):
                            semantic.append(Finding("adres", s, e, val, HIGH))
                    continue
                if node.tag in ("Telephone", "Telefax") and parent == "Contact":
                    if enabled("telefon"):
                        semantic.append(Finding("telefon", s, e, val, HIGH))
                    continue
                if node.tag == "ElectronicMail" and parent == "Contact":
                    if enabled("eposta"):
                        semantic.append(Finding("eposta", s, e, val, HIGH))
                    continue

            if node.tag == "ID" and node.attrs.get("schemeID", "").upper() in (
                "MERSISNO",
                "TICARETSICILNO",
                "VKN",
                "TCKN",
                "VKN_TCKN",
                "MUSTERINO",
                "BAYINO",
                "SUBENO",
                "ABONENO",
                "DOSYANO",
            ):
                _emit_scheme_id(semantic, node.attrs.get("schemeID", "").upper(), s, e, val, enabled)
                continue

            # Parasal tutar elemanları (*Amount)
            if node.tag.endswith("Amount"):
                if enabled("tutar") and not _is_zero_number(val):
                    cur = node.attrs.get("currencyID", "")
                    semantic.append(Finding("tutar", s, e, val, HIGH, cur if cur in ("TRY", "USD", "EUR", "GBP", "TL") else ""))
                continue

            # Ödeme / Banka bilgileri
            if node.tag in ("ID", "Name") and ("PayeeFinancialAccount" in path_set or "PayerFinancialAccount" in path_set):
                if node.tag == "ID" and iban_valid(val):
                    if enabled("iban"):
                        semantic.append(Finding("iban", s, e, val, HIGH))
                elif enabled("banka_bilgisi"):
                    semantic.append(Finding("banka_bilgisi", s, e, val, HIGH))
                continue
            if node.tag in ("Name", "ID") and ("FinancialInstitution" in path_set or "FinancialInstitutionBranch" in path_set):
                if enabled("banka_bilgisi"):
                    semantic.append(Finding("banka_bilgisi", s, e, val, HIGH))
                continue

            # AdditionalDocumentReference
            if node.adr_group and node.tag == "ID":
                meta = adr_meta.get(node.adr_group, {})
                dt = meta.get("DocumentType", "").upper()
                if dt in ("TR_NET_STR", "TOTAL_NET_STR"):
                    if enabled("tutar"):
                        semantic.append(Finding("tutar", s, e, val, HIGH))
                    continue
                if dt in _ADR_AMOUNT_TYPES:
                    if enabled("tutar") and not _is_zero_number(val):
                        semantic.append(Finding("tutar", s, e, val, HIGH))
                    continue
                if enabled("ettn") and _UUID_RE.fullmatch(val):
                    semantic.append(Finding("ettn", s, e, val, HIGH))
                    continue
                if dt == "XSLT":
                    continue

            # Teknik kod alanlarında sahte kart/plaka eşleşmelerini engelle
            if node.tag in _TECH_EXACT_TAGS or parent in _TECH_CODE_PARENTS or node.tag == "ID":
                continue

            # Serbest metin (Note, Description, Item/Name vb.) üzerinde standart tespit
            if node.tag in _FREE_TEXT_TAGS or node.tag not in _TECH_EXACT_TAGS:
                if node.tag == "InstructionNote" and len(val) <= 3:
                    continue
                for f in detect(val, rules, hints, lead=lead):
                    free_findings.append(Finding(f.type, s + f.start, s + f.end, f.value, f.confidence, f.source))

    whitelist = {w.casefold() for w in rules.whitelist}
    all_findings = [
        f
        for f in semantic + free_findings
        if f.value.strip().casefold() not in whitelist and (rules.allow is None or f.value not in rules.allow)
    ]
    from .detect import _resolve_overlaps

    return _resolve_overlaps(all_findings), embedded


def _run_shifted(seg: str, offset: int, rules: Rules, hints: frozenset[str], lead: bool) -> list[Finding]:
    from .detect import detect

    return [Finding(f.type, offset + f.start, offset + f.end, f.value, f.confidence, f.source) for f in detect(seg, rules, hints, lead=lead)]


def _is_zero_number(val: str) -> bool:
    try:
        return float(val.replace(",", ".")) == 0.0
    except ValueError:
        return False


def _emit_scheme_id(
    out: list[Finding], scheme: str, s: int, e: int, val: str, enabled: Callable[[str], bool]
) -> None:
    if scheme == "MERSISNO":
        if enabled("mersis"):
            out.append(Finding("mersis", s, e, val, HIGH))
    elif scheme == "TICARETSICILNO":
        if enabled("ticaret_sicil"):
            out.append(Finding("ticaret_sicil", s, e, val, HIGH))
    elif scheme == "VKN":
        if enabled("vkn"):
            out.append(Finding("vkn", s, e, val, HIGH if vkn_valid(val) else MEDIUM))
    elif scheme == "TCKN":
        if enabled("tc_kimlik"):
            out.append(Finding("tc_kimlik", s, e, val, HIGH if tc_kimlik_valid(val) else MEDIUM))
    elif scheme == "VKN_TCKN":
        d = digits_only(val)
        if len(d) == 11:
            if enabled("tc_kimlik"):
                out.append(Finding("tc_kimlik", s, e, val, HIGH if tc_kimlik_valid(d) else MEDIUM))
        elif enabled("vkn"):
            out.append(Finding("vkn", s, e, val, HIGH if vkn_valid(d) else MEDIUM))
    elif scheme in ("MUSTERINO", "BAYINO", "SUBENO", "ABONENO", "DOSYANO"):
        if enabled("musteri_no"):
            out.append(Finding("musteri_no", s, e, val, HIGH))
