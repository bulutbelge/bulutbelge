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
)


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
