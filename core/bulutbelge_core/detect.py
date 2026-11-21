"""Metinde kişisel veri tespiti.

Yerleşik türler kalıp + doğrulama ile bulunur. Kullanıcının özel ifadeleri
(sözcük sınırıyla, büyük/küçük harf duyarsız) ve özel kalıpları da eklenir.
Çakışan bulgularda uzun olan, eşitse önceliği yüksek olan kalır.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

import regex

from .rules import PATTERN_TIMEOUT, Rules
from . import extra_types as xt
from . import ids
from .loose import find_mixed, find_mixed_email
from .labels import label_before, label_kind
from .names import find_name_candidates, find_person_names, find_url_names
from .validators import digits_only, iban_valid, luhn_valid, tc_kimlik_valid, vkn_valid

HIGH = "yuksek"
MEDIUM = "orta"
# Kişisel bilgi olabilir ama doğrulanamadı (ör. TC'ye benziyor, kontrol hanesi tutmuyor).
# Arayüzde "Emin olamadıklarımız" kartında, varsayılan olarak açık kalacak şekilde gelir.
LOW = "dusuk"


@dataclass(frozen=True)
class Finding:
    type: str
    start: int
    end: int
    value: str
    confidence: str
    source: str = ""  # özel kalıp adı gibi ek bilgi


# Ayraç olarak yalnızca boşluk ve tire: satır sonu üzerinden eşleşme olmasın.
_TC = re.compile(r"(?<!\d)[1-9]\d{10}(?!\d)")
_VKN = re.compile(r"(?<!\d)\d{10}(?!\d)")
_IBAN = re.compile(r"\bTR(?:[ ]?\d){24}(?!\d)", re.IGNORECASE)
_CARD = re.compile(r"(?<![A-Za-z0-9])\d(?:[ -]?\d){12,18}(?![A-Za-z0-9])")
_PHONE = re.compile(
    r"(?<![\d+])(?:(?:\+90|0090)[ -]?|0)?\(?5\d{2}\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?!\d)"
    r"|(?<![\d+])(?:(?:\+90|0090)[ -]?|0)\(?[2-4]\d{2}\)?[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?!\d)"
)
# Gruplanmış 16 hane: kart numarası gibi yazılmış ama Luhn tutmuyor.
_CARD_GROUPED = re.compile(r"(?<![A-Za-z0-9])\d{4}([ -])\d{4}\1\d{4}\1\d{4}(?![A-Za-z0-9])")
# "TC Kimlik No:" etiketinden sonra 11 hane olmayan sayı (eksik ya da fazla yazılmış).
_DIGITS = re.compile(r"(?<!\d)\d{9,12}(?!\d)")
# Geri bakış: eşleşme yalnızca yerel kısmın başında başlar. Yoksa "@" içermeyen uzun bir dizide her konumdan
# yeniden denenir ve süre karesel büyür (900 KB tek satır metin işçiyi dakikalarca kilitliyordu, E.11 denemesi).
_EMAIL = re.compile(r"(?<![A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Çakışmada öncelik (küçük olan kazanır).
# IMEI kredi kartından önce: eşit uzunlukta Luhn geçerli 15 hanede IMEI kazanır (Amex find_imeis dışında kalır).
_PRIORITY = {
    "ozel_ifade": 0,
    "ozel_kalip": 1,
    "gizli_anahtar": 2,
    "mrz": 2,
    "eposta": 3,
    "iban": 4,
    "imei": 4,
    "kredi_karti": 5,
    "tc_kimlik": 6,
    "telefon": 7,
    "vkn": 8,
    "dogum_tarihi": 9,
    "plaka": 10,
    "ip": 11,
    "mac": 12,
    "sase_no": 13,
    "tutar": 14,
    "ettn": 15,
    "adres": 16,
    "pasaport": 17,
    "ehliyet": 18,
    "mersis": 19,
    "ticaret_sicil": 20,
    "vergi_dairesi": 21,
    "banka_bilgisi": 22,
    "kurum_unvani": 23,
    "sgk": 24,
    "sicil_no": 25,
    "gps": 26,
    "kullanici_adi": 27,
    "unvan_kurum": 28,
    "musteri_no": 29,
    "kisi_adi": 30,
}

# Ek türler: (tür, bulucu, güven)
_EXTRA = (
    ("gizli_anahtar", xt.find_secrets, HIGH),
    ("adres", xt.find_addresses, MEDIUM),
    ("dogum_tarihi", xt.find_birth_dates, HIGH),
    ("plaka", xt.find_plates, HIGH),
    ("ip", xt.find_ips, MEDIUM),
    ("imei", xt.find_imeis, HIGH),
    ("mac", xt.find_macs, MEDIUM),
    ("sase_no", xt.find_vins, HIGH),
    ("tutar", xt.find_amounts, HIGH),
    ("mrz", ids.find_mrz, HIGH),
    ("pasaport", ids.find_passports, HIGH),
    ("ehliyet", ids.find_licences, HIGH),
    ("sgk", ids.find_sgk, HIGH),
    ("sicil_no", xt.find_sicil_numbers, HIGH),
    ("gps", xt.find_gps, HIGH),
    ("kullanici_adi", xt.find_social_handles, MEDIUM),
    ("unvan_kurum", xt.find_title_institution, MEDIUM),
    ("mersis", ids.find_mersis, HIGH),
    ("musteri_no", ids.find_customer_numbers, MEDIUM),
)


def detect(
    text: str, rules: Rules, hints: frozenset[str] = frozenset(), lead: bool = False
) -> list[Finding]:
    """Metindeki kişisel bilgileri bulur.

    `hints`: belgenin tamamından çıkarılan ad ipuçları (bkz. `names.name_hints`; e-posta adreslerinden).
    `lead`: bu metin belgenin başı mı (ilk sayfa/parça); belge başlığındaki ad aday gösterilir.
    """
    candidates: list[Finding] = []
    name_uncertain: list[Finding] = []
    # Doğrulanamayan adaylar; kesin bulgularla çakışmıyorsa eklenir.
    uncertain: list[Finding] = []

    def enabled(key: str) -> bool:
        return rules.types[key].enabled

    if enabled("tc_kimlik"):
        for m in _TC.finditer(text):
            if tc_kimlik_valid(m.group()):
                candidates.append(Finding("tc_kimlik", m.start(), m.end(), m.group(), HIGH))
            else:
                uncertain.append(Finding("tc_kimlik", m.start(), m.end(), m.group(), LOW, "kontrol hanesi tutmuyor"))
        for m in _DIGITS.finditer(text):
            if _TC.fullmatch(m.group()):
                continue
            label = label_before(text, m.start())
            if label_kind(label) == "tc_kimlik":
                candidates.append(
                    Finding("tc_kimlik", m.start(), m.end(), m.group(), MEDIUM, f"“{label}” etiketli; 11 hane değil")
                )

    if enabled("vkn"):
        for m in _VKN.finditer(text):
            if vkn_valid(m.group()):
                candidates.append(Finding("vkn", m.start(), m.end(), m.group(), HIGH))

    if enabled("iban"):
        for m in _IBAN.finditer(text):
            if iban_valid(m.group()):
                candidates.append(Finding("iban", m.start(), m.end(), m.group(), HIGH))
            else:
                uncertain.append(Finding("iban", m.start(), m.end(), m.group(), LOW, "kontrol hanesi tutmuyor"))

    if enabled("kredi_karti"):
        for m in _CARD.finditer(text):
            if luhn_valid(digits_only(m.group())):
                candidates.append(Finding("kredi_karti", m.start(), m.end(), m.group(), HIGH))
        for m in _CARD_GROUPED.finditer(text):
            if not luhn_valid(digits_only(m.group())):
                uncertain.append(Finding("kredi_karti", m.start(), m.end(), m.group(), LOW, "kart numarasına benziyor"))

    if enabled("telefon"):
        for m in _PHONE.finditer(text):
            candidates.append(Finding("telefon", m.start(), m.end(), m.group(), HIGH))

    # Karışık yazımlar (aralıklı/tam genişlikli rakam, OCR harfi, bölünmüş IBAN); doğrulayıcılı.
    for kind, start, end, confidence in find_mixed(
        text, enabled("tc_kimlik"), enabled("iban"), enabled("telefon"), enabled("vkn"), enabled("kredi_karti")
    ):
        note = "karışık yazım" + (" (OCR benzeri harf)" if confidence == MEDIUM else "")
        candidates.append(Finding(kind, start, end, text[start:end], confidence, note))

    if enabled("eposta"):
        for m in _EMAIL.finditer(text):
            candidates.append(Finding("eposta", m.start(), m.end(), m.group(), HIGH))
        for start, end in find_mixed_email(text):
            candidates.append(Finding("eposta", start, end, text[start:end], MEDIUM, "karışık yazım"))

    for key, finder, confidence in _EXTRA:
        if enabled(key):
            for start, end in finder(text):
                value = text[start:end].strip()
                if value:
                    start += text[start:end].index(value)
                    candidates.append(Finding(key, start, start + len(value), value, confidence))

    if any(
        enabled(k)
        for k in ("kurum_unvani", "vergi_dairesi", "ticaret_sicil", "banka_bilgisi", "ettn", "tutar", "adres")
    ):
        from .efatura import find_efatura_text_findings

        candidates.extend(find_efatura_text_findings(text, enabled))

    if enabled("kisi_adi"):
        for start, end, labeled in find_person_names(text):
            candidates.append(Finding("kisi_adi", start, end, text[start:end], HIGH if labeled else MEDIUM))
        for start, end, confidence, reason in [*find_name_candidates(text, hints, lead), *find_url_names(text, hints)]:
            finding = Finding("kisi_adi", start, end, text[start:end], confidence, reason)
            # Orta güvenli (e-posta ipucu) maskelenir; düşük güvenli "emin olamadıklarımız"a gider.
            (candidates if confidence == MEDIUM else name_uncertain).append(finding)

    if enabled("ozel_ifade"):
        for term in rules.terms:
            pattern = regex.compile(r"(?<!\w)" + regex.escape(term) + r"(?!\w)", regex.IGNORECASE)
            for m in pattern.finditer(text):
                candidates.append(Finding("ozel_ifade", m.start(), m.end(), m.group(), HIGH, term))

    if enabled("ozel_kalip"):
        for p in rules.patterns:
            if not getattr(p, "enabled", True):
                continue
            try:
                for m in p.compiled.finditer(text, timeout=PATTERN_TIMEOUT):
                    if m.end() > m.start():
                        candidates.append(Finding("ozel_kalip", m.start(), m.end(), m.group(), MEDIUM, p.name))
            except TimeoutError:
                raise PatternTimeout(p.name) from None

    read = [r for r in (_read_label(text, f) for f in uncertain) if r is not None]
    candidates.extend(f for f in read if f.confidence != LOW)
    uncertain = [f for f in read if f.confidence == LOW] + name_uncertain

    whitelist = {w.casefold() for w in rules.whitelist}

    # Kurum sözlüğü: ifadenin metindeki yerleri; yalnızca kişi adı ve adres bulgusu tamamen
    # bu yerlerin içindeyse atlanır (numara türleri sözlükten etkilenmez, şüphede maskele).
    inst_spans: list[tuple[int, int]] = []
    for term in rules.institutions:
        pat = regex.compile(r"(?<!\w)" + regex.escape(term) + r"(?!\w)", regex.IGNORECASE)
        inst_spans.extend((m.start(), m.end()) for m in pat.finditer(text))

    def wanted(f: Finding) -> bool:
        if f.value.strip().casefold() in whitelist:
            return False
        if f.type in _INSTITUTION_TYPES and any(s <= f.start and f.end <= e for s, e in inst_spans):
            return False
        return rules.allow is None or f.value not in rules.allow

    kept = _resolve_overlaps([f for f in candidates if wanted(f)])
    unsure = _resolve_overlaps([f for f in uncertain if wanted(f)])
    occupied = _Occupancy(kept + unsure)
    for k in kept:
        occupied.add(k)
    extra = [f for f in unsure if not occupied.overlaps(f)]
    return sorted(kept + extra, key=lambda f: f.start)


def _read_label(text: str, f: Finding) -> Finding | None:
    """Doğrulanamayan adayı önündeki etikete göre değerlendirir (bkz. labels.py)."""
    label = label_before(text, f.start)
    kind = label_kind(label)
    if kind == f.type:
        return replace(f, confidence=MEDIUM, source=f"“{label}” etiketli; {f.source}, yazım hatası olabilir")
    if kind is not None:
        # Etiket başka bir numara türünü söylüyor ("Referans No", "Vergi Kimlik No").
        return None
    if label:
        return replace(f, source=f"“{label}” etiketli; {f.source}")
    return f


_INSTITUTION_TYPES = ("kisi_adi", "adres")


class PatternTimeout(Exception):
    def __init__(self, name: str) -> None:
        super().__init__(f"'{name}' kalıbı bu belgede çok uzun sürdü; kalıbı sadeleştirin")
        self.name = name


class _Coverage:
    """0..n-1 birimleri: aralığı işaretle, aralıkta işaretli birim var mı (Fenwick ağacı + sonraki boş birim)."""

    def __init__(self, n: int) -> None:
        self._tree = [0] * (n + 1)
        self._next = list(range(n + 1))  # i'den itibaren ilk işaretlenmemiş birim (yol sıkıştırmalı)

    def _free(self, i: int) -> int:
        root = i
        while self._next[root] != root:
            root = self._next[root]
        while self._next[i] != root:
            self._next[i], i = root, self._next[i]
        return root

    def _prefix(self, i: int) -> int:
        total = 0
        while i > 0:
            total += self._tree[i]
            i -= i & -i
        return total

    def any(self, lo: int, hi: int) -> bool:
        return self._prefix(hi + 1) - self._prefix(lo) > 0

    def mark(self, lo: int, hi: int) -> None:
        i = self._free(lo)
        while i <= hi:
            j = i + 1
            while j < len(self._tree):
                self._tree[j] += 1
                j += j & -j
            self._next[i] = i + 1
            i = self._free(i + 1)


class _Occupancy:
    """Tutulan bulgularla çakışma denetimi, bulgu başına O(log F) (güvenlik taraması F7).

    Çakışma tanımı eskisiyle aynı: `not (f.end <= k.start or f.start >= k.end)`. Konumlar ikiye katlanır:
    boş olmayan [s, e) aralığı 2s+1..2e-1 birimlerini, boş bulgu (s == e) 2s birimini kaplar. Böylece boş
    bulgu yalnızca içine düştüğü aralıkla çakışır; iki boş bulgu (tanım gereği) birbiriyle çakışmaz.
    """

    def __init__(self, findings: list[Finding]) -> None:
        coords = sorted({u for f in findings for u in self._units(f)})
        self._index = {c: i for i, c in enumerate(coords)}
        self._spans = _Coverage(len(coords))
        self._points = _Coverage(len(coords))

    @staticmethod
    def _units(f: Finding) -> tuple[int, int]:
        if f.end <= f.start:
            return 2 * f.start, 2 * f.start
        return 2 * f.start + 1, 2 * f.end - 1

    def overlaps(self, f: Finding) -> bool:
        a, b = self._units(f)
        lo, hi = self._index[a], self._index[b]
        if f.end <= f.start:
            return self._spans.any(lo, hi)
        return self._spans.any(lo, hi) or self._points.any(lo, hi)

    def add(self, f: Finding) -> None:
        a, b = self._units(f)
        (self._points if f.end <= f.start else self._spans).mark(self._index[a], self._index[b])


def _resolve_overlaps(findings: list[Finding]) -> list[Finding]:
    ordered = sorted(findings, key=lambda f: (-(f.end - f.start), _PRIORITY[f.type], f.start))
    occupied = _Occupancy(ordered)
    kept: list[Finding] = []
    for f in ordered:
        if not occupied.overlaps(f):
            occupied.add(f)
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)
