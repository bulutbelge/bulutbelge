"""Öğrenilen istisnalar: kullanıcının "Bunu bir daha hiç gizleme" dediği değerler.

Örnek: şirketin genel telefonu ya da her belgede geçen bir kurum adı her seferinde
bulunup kullanıcı her seferinde işaretini kaldırıyorsa, değer bir kez listeye
eklenir ve sonraki belgelerde bulgu olarak gelmez.

Değerin kendisi diske yazılmaz: kuruluma özel rastgele tuzla PBKDF2 özeti
saklanır. Taramada bulunan her değerin özeti hesaplanıp listeyle karşılaştırılır.
Not: kısa sayısal değerlerin (telefon gibi) özeti deneme yanılmayla bulunabilir;
özet, dosyaya bakan birinin değeri doğrudan okumasını engeller, şifreleme değildir.
Bkz. docs/kararlar/2026-11-05-belirsiz-istisna-sayfa-metin.md
"""

from __future__ import annotations

import hashlib
import re

ITERATIONS = 20_000
_NUMERIC = re.compile(r"[\d\s\-+().]+")


def normalize(value: str) -> str:
    """Aynı değerin farklı yazılışları aynı anahtara düşsün: "0212 555 12 34" = "+90 (212) 5551234"."""
    v = value.strip()
    if _NUMERIC.fullmatch(v) and any(c.isdigit() for c in v):
        digits = "".join(c for c in v if c.isdigit())
        if len(digits) == 12 and digits.startswith("90"):
            digits = digits[2:]
        elif len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        return digits
    return " ".join(v.split()).casefold()


def value_hash(value: str, salt: bytes) -> str:
    return hashlib.pbkdf2_hmac("sha256", normalize(value).encode("utf-8"), salt, ITERATIONS).hex()


class AllowMatcher:
    """Taramada kullanılır; aynı değerin özetini bir kez hesaplar."""

    def __init__(self, hashes: set[str] | frozenset[str], salt: bytes) -> None:
        self.hashes = frozenset(hashes)
        self.salt = salt
        self._cache: dict[str, bool] = {}

    def __contains__(self, value: str) -> bool:
        key = normalize(value)
        if key not in self._cache:
            self._cache[key] = value_hash(value, self.salt) in self.hashes
        return self._cache[key]
