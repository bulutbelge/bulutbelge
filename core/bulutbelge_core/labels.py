"""Bir değerin önündeki etiketi okuma ("TC Kimlik No: …", "Referans No: …").

Doğrulanamayan adaylarda (kontrol hanesi tutmayan TC, IBAN, kart) etiket kararı verir:

- Etiket aynı türü söylüyorsa ("TC Kimlik No: 1234…" ama kontrol hanesi tutmuyor) değer büyük
  olasılıkla yanlış yazılmış bir kişisel bilgidir; şüphede gizlenir.
- Etiket başka bir numara türünü söylüyorsa ("Referans No", "Fatura No", "Vergi Kimlik No")
  aday o tür değildir; "Emin olamadıklarımız"da boşuna gösterilmez.
- Etiket yoksa ya da bir şey söylemiyorsa aday belirsiz kalır, etiket gerekçeye yazılır.

Etiket aynı satırda değerin hemen önündeki birkaç sözcüktür; aynı satırda bir şey yoksa ve
önceki satır ":" ile bitiyorsa (form düzeni) önceki satır kullanılır.
"""

from __future__ import annotations

import re

REFERENCE = "referans"

_MAX_CHARS = 48
_MAX_WORDS = 5
# Etiketle değer arasındaki ayraçlar.
_TRAIL = re.compile(r"[\s:#=\-–—]+$")
# Etiketi önceki cümle parçasından ayıran işaretler ("(Tel: …", "…, Ref: …").
_CUT = re.compile(r".*(?:[(\[,;|]|\.\s)")
_WORD = re.compile(r"[a-zçğıöşü0-9.'’]+")

# Sıra önemli: "Vergi Kimlik No" vergi, "Kimlik Kartı" TC sayılır.
_KINDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("vkn", ("vergi", "vkn")),
    ("tc_kimlik", ("tc", "tckn", "kimlik", "vatandaşlık", "vatandaslik")),
    ("iban", ("iban",)),
    ("kredi_karti", ("kart", "kartı", "kartın", "card")),
    ("telefon", ("tel", "telefon", "gsm", "cep", "faks", "fax")),
    (
        REFERENCE,
        (
            "referans", "ref", "kayıt", "kayit", "kaydı", "sipariş", "siparis", "fatura", "takip", "işlem",
            "islem", "evrak", "belge", "seri", "barkod", "sıra", "sira", "kargo", "talep", "ticket", "fiş",
            "fis", "makbuz", "dekont", "sevk", "irsaliye", "rapor", "ürün", "urun", "stok", "model",
            "versiyon", "sürüm", "surum", "proje", "dosya", "protokol", "sözleşme", "sozlesme", "poliçe",
            "police", "abone", "müşteri", "musteri", "üye", "uye", "başvuru", "basvuru",
        ),
    ),
)


def _fold(s: str) -> str:
    # Büyük harfli kısaltmalar ("IBAN", "TCKN") Türkçe kurala göre "ı" olur; ı ile i aynı sayılır.
    return s.replace("İ", "i").lower().replace("ı", "i")


def label_before(text: str, start: int) -> str:
    """Değerin önündeki etiketi döndürür (yoksa boş)."""
    line_start = text.rfind("\n", 0, start) + 1
    prefix = _TRAIL.sub("", text[max(line_start, start - _MAX_CHARS):start])
    if not prefix.strip() and line_start > 0:
        prev_start = text.rfind("\n", 0, line_start - 1) + 1
        prev = text[prev_start:line_start - 1].rstrip()
        if prev.endswith(":"):
            prefix = _TRAIL.sub("", prev[-_MAX_CHARS:])
    prefix = _CUT.sub("", prefix).strip()
    words = prefix.split()
    return " ".join(words[-_MAX_WORDS:])


def label_kind(label: str) -> str | None:
    """Etiketin söylediği tür: bir veri türü anahtarı, REFERENCE ya da None."""
    tokens = []
    for w in _WORD.findall(_fold(label)):
        w = re.split(r"['’]", w)[0].replace(".", "")
        if w:
            tokens.append(w)
    if not tokens:
        return None
    for kind, words in _KINDS:
        if any(t in {_fold(w) for w in words} for t in tokens):
            return kind
    return None
