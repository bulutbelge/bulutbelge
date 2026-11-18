"""Tablo verisi (CSV/Excel) için yapısal gizleme: üstten kodlama, tarih kaydırma, k-anonimlik uyarısı.

Başlığa göre sütun kurallarına (`Rules.column_actions`) bağlıdır. Hepsi saf işlevlerdir; belge
okuma/yazma textdoc.py ve office.py'dedir. Uyarılar özgün değer içermez, yalnızca sayı verir.
Tarih kaydırma ve üstten kodlama anonimleştirme değildir; yeniden tanımlama riskini azaltır.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime, timedelta

# Sütun eylemleri (column_rules öğesinde "action")
ACTION_QUASI = "dolayli"  # k-anonimlik uyarısında yarı-tanımlayıcı sütun
ACTION_AGE = "yas"  # üstten kodlama: eşik ve üstü "90+"
ACTION_DATE = "tarih"  # belge/iş başına sabit gün kayması
ACTIONS = (ACTION_QUASI, ACTION_AGE, ACTION_DATE)

DEFAULT_K = 5
DEFAULT_AGE_LIMIT = 90
MAX_SHIFT_DAYS = 180

_DATE = re.compile(r"(\d{1,4})([./-])(\d{1,2})\2(\d{1,4})")


def top_code_age(value: str, limit: int = DEFAULT_AGE_LIMIT) -> str | None:
    """Yaş `limit` ve üstündeyse "limit+" döner; değişmeyecekse (ya da yaş değilse) None."""
    s = value.strip()
    if not s.isdigit() or len(s) > 3 or int(s) < limit:
        return None
    return f"{limit}+"


def parse_date(value: str) -> tuple[date, str, str] | None:
    """gg.aa.yyyy, gg/aa/yyyy, gg-aa-yyyy ve yyyy-aa-gg biçimlerini okur: (tarih, ayraç, sıra)."""
    m = _DATE.fullmatch(value.strip())
    if not m:
        return None
    a, sep, b, c = m.group(1), m.group(2), m.group(3), m.group(4)
    try:
        if len(a) == 4:
            return date(int(a), int(b), int(c)), sep, "ymd"
        if len(c) == 4:
            return date(int(c), int(b), int(a)), sep, "dmy"
    except ValueError:
        return None
    return None


def shift_date(value: str, days: int) -> str | None:
    """Tarihi `days` gün kaydırır, biçimi korur; tarih değilse None."""
    parsed = parse_date(value)
    if parsed is None:
        return None
    d, sep, order = parsed
    n = d + timedelta(days=days)
    if order == "ymd":
        return f"{n.year:04d}{sep}{n.month:02d}{sep}{n.day:02d}"
    return f"{n.day:02d}{sep}{n.month:02d}{sep}{n.year:04d}"


def shift_serial(value: str, days: int) -> str | None:
    """Excel tarih seri numarasını (tam sayı) kaydırır; sayı değilse None."""
    s = value.strip()
    if not re.fullmatch(r"\d{1,6}(\.0+)?", s):
        return None
    return str(int(float(s)) + days)


def new_shift_days() -> int:
    """İş başına sabit kayma: ±1..180 gün (0 olmaz), rastgele."""
    import secrets

    n = secrets.randbelow(MAX_SHIFT_DAYS) + 1
    return n if secrets.randbelow(2) else -n


def k_anonymity_warning(rows: list[list[str]], columns: list[int], k: int, names: list[str] | None = None) -> str | None:
    """Seçilen dolaylı sütunların birleşimi `k`'dan az satırda görünüyorsa uyarı metni döner.

    Boş değerli satırlar da bir grup değeridir. Uyarı değer içermez: yalnızca sütun başlıkları,
    en küçük grup ve etkilenen satır sayısı yazılır.
    """
    if not columns or not rows or k < 2:
        return None
    groups = Counter(tuple((r[c].strip().casefold() if c < len(r) else "") for c in columns) for r in rows)
    small = {g: n for g, n in groups.items() if n < k}
    if not small:
        return None
    affected = sum(small.values())
    label = ", ".join(names) if names else f"{len(columns)} sütun"
    return (
        f"k-anonimlik uyarısı: {label} birleşiminde {affected} satır, {k}'dan az kişilik bir grupta "
        f"(en küçük grup: {min(small.values())}). Bu satırlar dolaylı bilgiyle tek tek tanınabilir; "
        "sütunları genelleştirmeyi ya da satırları çıkarmayı düşünün."
    )
