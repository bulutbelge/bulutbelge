"""Kuruma özgü kimlik ve belge numaraları.

Bu numaraların çoğunun kontrol hanesi yoktur ve tek başına bakınca sıradan bir
sayıdan ayırt edilemez. Bu yüzden yalnızca bir etiketin hemen ardından gelince
bulunurlar ("Pasaport No: U12345678", "SGK sicil no 1234567890123"). Etiket ile
değer arasında en fazla birkaç karakter (":", "-", "no", boşluk) olabilir.

| Tür        | Etiket örnekleri                          | Değer                              |
|------------|-------------------------------------------|------------------------------------|
| pasaport   | pasaport no, passport no                  | 1-2 harf + 6-8 rakam (U12345678)   |
| ehliyet    | ehliyet no, sürücü belgesi no             | 5-10 rakam ya da harf+rakam        |
| sgk        | SGK no, sicil no, SSK no, işyeri sicil    | 8-26 rakam (boşluk/tire olabilir)  |
| mersis     | MERSİS no                                 | 16 rakam, 0 ile başlar             |
| musteri_no | müşteri/abone/poliçe/sözleşme/hasta/dosya no | 4-20 harf, rakam, tire          |
"""

from __future__ import annotations

import re
from collections.abc import Iterator

# Etiket ile değer arası: "No", "Numarası", ":", "-", "#" ve boşluklar. Dil eski
# `\s*(?:no...)?\s*[:#\-]?\s*` ile aynı; bitişik üç `\s*` boşluk dizisini kübik sayıda biçimde bölüyordu
# (güvenlik taraması F4). Burada her boşluk dizisi tek bir niceleyiciye düşer.
_SEP = r"(?:\s*(?:(?:no\.?|numaras[ıi]|nr\.?|#)\s*)?(?:[:#\-]\s*)?)"


def _labeled(labels: str, value: str) -> re.Pattern[str]:
    return re.compile(r"(?i)(?<![\w])(?:" + labels + r")" + _SEP + r"(" + value + r")(?![\w])")


_PASSPORT = _labeled(r"pasaport|passport", r"[A-Z]{1,2}\d{6,8}")
_LICENCE = _labeled(r"ehliyet|sürücü\s+belgesi|surucu\s+belgesi|driver'?s?\s+licen[cs]e", r"[A-Z]?\d{5,10}")
_SGK = _labeled(
    r"sgk(?:\s+sicil)?|ssk|sicil|işyeri\s+sicil|isyeri\s+sicil|sosyal\s+güvenlik", r"\d[\d \-]{6,30}\d"
)
_MERSIS = _labeled(r"mers[iİı]s", r"0\d{3}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}")
# Müşteri, poliçe gibi genel sözcüklerden sonra "no", "numarası", "kodu" ya da "#" şart
# ("müşteri · 2019'dan beri" bir numara değildir).
_CUSTOMER = re.compile(
    r"(?i)(?<![\w])(?:müşteri|musteri|abone|abonelik|poliçe|police|sözleşme|sozlesme|hasta|protokol|dosya|"
    r"başvuru|basvuru|üye|uye|sipariş|siparis|kart\s+sahibi)"
    r"\s*(?:no\.?|numaras[ıi]|nr\.?|#|kodu)\s*(?:[:#\-]\s*)?"
    r"((?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{3,19})(?![\w])"
)


def _find(rx: re.Pattern[str], text: str) -> Iterator[tuple[int, int]]:
    for m in rx.finditer(text):
        yield m.start(1), m.end(1)


def find_passports(text: str) -> Iterator[tuple[int, int]]:
    return _find(_PASSPORT, text)


def find_licences(text: str) -> Iterator[tuple[int, int]]:
    return _find(_LICENCE, text)


def find_sgk(text: str) -> Iterator[tuple[int, int]]:
    for s, e in _find(_SGK, text):
        if sum(c.isdigit() for c in text[s:e]) >= 8:
            yield s, e


def find_mersis(text: str) -> Iterator[tuple[int, int]]:
    return _find(_MERSIS, text)


def find_customer_numbers(text: str) -> Iterator[tuple[int, int]]:
    return _find(_CUSTOMER, text)


# Kimlik / pasaport makinece okunabilir alan (MRZ): TD1 (3x30), TD2 (2x36), TD3 (2x44).
# Satır satır ve doğrusal çalışır: iç içe niceleyicili tek bir düzenli ifade, rakamdan oluşan uzun bir satırda
# karesel sürer (60 bin karakter 28 sn) ve sunucu işçisini kilitler (TAKIP E.11 ile aynı sorun).
_MRZ_CHARS = re.compile(r"[A-Z0-9<]+")


def _mrz_line_ok(line: str) -> bool:
    n = len(line)
    if n < 22 or n > 120 or not _MRZ_CHARS.fullmatch(line) or line.count("<") < 2:
        return False
    if line[0] in "IPACV" and n <= 47:  # TD1/TD2/TD3 satırı: tür harfi ("P<UTO..."), en çok 44 karakter, en az iki "<"
        return True
    if line[0] == "<" or line[1] == "<":
        return False
    i = line.find("<<", 2)
    return i != -1 and n - (i + 2) >= 2


def find_mrz(text: str) -> Iterator[tuple[int, int]]:
    """Pasaport ve kimlik belgelerindeki alt MRZ (<<<) satır bloklarını bulur."""
    lines: list[tuple[int, int]] = []
    pos = 0
    for line in text.split("\n"):
        start = pos
        pos += len(line) + 1
        if len(line) > 200:
            continue  # MRZ satırı en çok 44 karakterdir; uzun satırlar hiç taranmaz
        val = line.strip(" \t")
        if _mrz_line_ok(val):
            s = start + (len(line) - len(line.lstrip(" \t")))
            lines.append((s, s + len(val)))
    if not lines:
        return
    # Ardışık MRZ satırlarını tek blok hâlinde birleştir (yalnız satır sonu / boşluk ayracı varsa).
    cur_s, cur_e = lines[0]
    for s, e in lines[1:]:
        gap = text[cur_e:s]
        if len(gap) <= 6 and not gap.strip():
            cur_e = e
        else:
            yield cur_s, cur_e
            cur_s, cur_e = s, e
    yield cur_s, cur_e
