"""Amaç seçimi: "Bu belge ne için hazırlanıyor?" → önerilen kural takımı.

Seçilen amaç denetim kaydına ve gizleme raporuna gerekçe olarak yazılır. Öneri yalnızca öneridir:
kullanıcı başka profil seçebilir, motor profili kendiliğinden değiştirmez.
"""

from __future__ import annotations

from typing import Any

# (kimlik, ad, önerilen profil kimliği). Profil kimlikleri `profiles.py` içindeki hazır takımlardır.
PURPOSES: tuple[tuple[str, str, str], ...] = (
    ("yapay_zeka", "Yapay zekâya gönderme", "musteri"),
    ("dis_paylasim", "Dış paylaşım (müşteri, ortak, üçüncü taraf)", "musteri"),
    ("denetim", "Denetçiye / düzenleyiciye paylaşım", "denetci"),
    ("kurum_ici", "Kurum içi paylaşım", "kurum_ici"),
    ("arsiv", "Arşiv / uzun süreli saklama", "denetci"),
    ("diger", "Diğer (açıklama zorunlu)", "musteri"),
)

OTHER = "diger"
MIN_NOTE = 10  # "diğer" amacında açıklamanın en kısa uzunluğu


def purposes() -> list[dict[str, str]]:
    return [{"id": pid, "name": name, "profile": profile} for pid, name, profile in PURPOSES]


def find(purpose_id: Any) -> dict[str, str] | None:
    """Kimliğe göre amaç; bilinmiyorsa None."""
    for p in purposes():
        if p["id"] == purpose_id:
            return p
    return None


def suggest_profile(purpose_id: str) -> str | None:
    """Amaç için önerilen profil kimliği; bilinmeyen amaçta None (şüphede öneri yok)."""
    p = find(purpose_id)
    return p["profile"] if p else None


def resolve(purpose_id: Any, note: Any = None) -> tuple[str, str]:
    """Sunucuda zorunlu amaç (bağımsız inceleme bulgu 7): (kimlik, günlüğe yazılacak metin).

    Amaç listeden seçilir; serbest metin yalnızca "diğer" amacında ek açıklama olarak ve en az
    `MIN_NOTE` karakter kabul edilir. Eksik ya da geçersiz girdide açıklayıcı `ValueError`.
    """
    pid = purpose_id.strip() if isinstance(purpose_id, str) else ""
    if not pid:
        raise ValueError(f"Amaç (amac) zorunludur; listeden seçin: {', '.join(p for p, _n, _p in PURPOSES)}")
    found = find(pid)
    if found is None:
        raise ValueError(
            f"Bilinmeyen amaç '{pid[:40]}'. Amaç listeden seçilir ({', '.join(p for p, _n, _p in PURPOSES)}); "
            f"serbest açıklama yalnızca '{OTHER}' ile amac_aciklama alanında verilir"
        )
    if note is not None and not isinstance(note, str):
        raise ValueError("amac_aciklama metin olmalı")
    text = " ".join("".join(ch for ch in (note or "") if ch.isprintable()).split())
    if pid == OTHER:
        if len(text) < MIN_NOTE:
            raise ValueError(f"'{OTHER}' amacında en az {MIN_NOTE} karakterlik açıklama (amac_aciklama) zorunludur")
        return pid, f"{found['name'].split(' (')[0]} — {text}"[:200]
    if text:
        raise ValueError(f"Serbest açıklama (amac_aciklama) yalnızca '{OTHER}' amacında verilir")
    return pid, found["name"]
