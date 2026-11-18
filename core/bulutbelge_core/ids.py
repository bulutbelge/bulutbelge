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

# Etiket ile değer arası: "No", "Numarası", ":", "-", "#" ve boşluklar.
_SEP = r"(?:\s*(?:no\.?|numaras[ıi]|nr\.?|#)?\s*[:#\-]?\s*)"


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
    r"\s*(?:no\.?|numaras[ıi]|nr\.?|#|kodu)\s*[:#\-]?\s*"
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
