"""Yeniden tanınabilirlik skoru.

Maskeli kopyada kalan dolaylı tanımlayıcıları (il, yaş, tarih, meslek, unvan+kurum) sayar ve
birleşik etkilerini basit, açıklanabilir bir puana çevirir. Tek başına zararsız görünen
bilgiler birleşince kişiyi ele verebilir; bu yüzden puan toplam sayıya değil, KAÇ FARKLI
türün birlikte bulunduğuna bağlıdır.

Hesap (hepsi rapora yazılır):
- Her tür için ağırlık: unvan+kurum 3, meslek 2, il 2, yaş 1, tarih 1.
- Tür katkısı = ağırlık × min(adet, 3) (tekrar sınırsız artırmaz).
- Birleşim çarpanı = 1 + 0.5 × (bulunan tür sayısı − 1).
- Puan = toplam katkı × çarpan, 0-100 arasına sınırlanır.
- Düzey: 0 → Yok, 1-9 → Düşük, 10-24 → Orta, 25+ → Yüksek.

Bu bir tahmindir, anonimleştirme güvencesi değildir: sözcük/kalıp tabanlıdır, kaçırabilir.
Eşleşen değer hiçbir yere yazılmaz; yalnızca tür adı ve sayı döner.
"""

from __future__ import annotations

import re
from typing import Any

from .extra_types import ILLER, _fold

_L = "a-zçğıöşü"

WEIGHTS = {"unvan_kurum": 3, "meslek": 2, "il": 2, "yas": 1, "tarih": 1}
LABELS = {
    "unvan_kurum": "unvan + kurum",
    "meslek": "meslek",
    "il": "il",
    "yas": "yaş",
    "tarih": "tarih",
}
_REPEAT_CAP = 3

_TITLES = (
    "müdür", "müdürü", "başkan", "başkanı", "genel müdür", "uzman", "şef", "koordinatör", "yönetmen",
    "direktör", "başhekim", "rektör", "dekan", "savcı", "hakim", "hâkim", "komiser", "müfettiş",
)
_OCCUPATIONS = (
    "doktor", "hekim", "avukat", "mühendis", "öğretmen", "hemşire", "muhasebeci", "mimar", "eczacı",
    "diş hekimi", "veteriner", "pilot", "gazeteci", "akademisyen", "profesör", "noter", "polis",
    "asker", "şoför", "berber", "kuaför", "çiftçi", "emekli",
)


def _lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def _alt(words: tuple[str, ...]) -> str:
    return "|".join(re.escape(w).replace(r"\ ", r"\s+") for w in sorted(words, key=len, reverse=True))


_B = rf"(?<![{_L}0-9])"
_E = rf"[{_L}]{{0,6}}(?![{_L}0-9])"
_ORG = "belediyesi|bakanlığı|müdürlüğü|başkanlığı|üniversitesi|hastanesi|bankası|şirketi|kurumu|valiliği|kaymakamlığı"
_TITLE_ORG = re.compile(
    rf"{_B}(?:{_alt(_TITLES)}){_E}[ \t,]+(?:[{_L}']+[ \t]+){{0,4}}?(?:{_ORG})(?![{_L}0-9])"
)
# Aradaki sözcük harfle başlar: kesme işareti dizisi hem ayırıcıya hem sözcüğe bölünebildiği için
# unvan gelmeyince ikinci dereceden geri izliyordu (güvenlik taraması F23/F24). "belediyesi'nin başkanı"
# gibi ekli yazımlar aynı eşleşir.
_ORG_TITLE = re.compile(
    rf"{_B}(?:{_ORG})[ \t,']+(?:[{_L}][{_L}']*[ \t]+){{0,2}}?(?:{_alt(_TITLES)}){_E}"
)
_OCC = re.compile(rf"{_B}(?:{_alt(_OCCUPATIONS)}){_E}")
_AGE = re.compile(rf"(?:\b\d{{1,3}}\s*yaşında|\byaş\s*:\s*\d{{1,3}}\b|\b\d{{1,3}}\s*yaş\b|\b\d{{2}}\+\s*yaş|\b\d{{1,2}}-\d{{1,2}}\s*yaş\b)")
_DATE = re.compile(
    r"(?<!\d)(?:(?:0?[1-9]|[12]\d|3[01])[ \t]*[./-][ \t]*(?:0?[1-9]|1[0-2])[ \t]*[./-][ \t]*(?:19|20)\d{2}"
    r"|(?:0?[1-9]|[12]\d|3[01])\s+(?:ocak|şubat|mart|nisan|mayıs|haziran|temmuz|ağustos|eylül|ekim|kasım|aralık)\s+(?:19|20)\d{2})(?!\d)"
)
_IL_FOLDS = sorted((_fold(i) for i in ILLER), key=len, reverse=True)
_IL = re.compile(rf"(?<![a-z0-9])(?:{'|'.join(map(re.escape, _IL_FOLDS))})(?![a-z0-9])")


def scan(text: str) -> dict[str, int]:
    """Tür → kalan dolaylı tanımlayıcı sayısı (yalnızca sıfırdan büyükler)."""
    low = _lower(text)
    out = {
        "unvan_kurum": len(_TITLE_ORG.findall(low)) + len(_ORG_TITLE.findall(low)),
        "meslek": len(_OCC.findall(low)),
        "il": len(_IL.findall(_fold(text))),
        "yas": len(_AGE.findall(low)),
        "tarih": len(_DATE.findall(low)),
    }
    return {k: n for k, n in out.items() if n}


def _level(score: int) -> str:
    return "Yok" if score <= 0 else "Düşük" if score < 10 else "Orta" if score < 25 else "Yüksek"


def score(counts: dict[str, int]) -> dict[str, Any]:
    """Sayımlardan açıklanabilir skor: puan, düzey, tür katkıları ve çarpan. Değer taşımaz."""
    used = {k: n for k, n in counts.items() if n > 0 and k in WEIGHTS}
    parts = {k: WEIGHTS[k] * min(n, _REPEAT_CAP) for k, n in used.items()}
    multiplier = 1 + 0.5 * max(len(used) - 1, 0)
    points = min(100, round(sum(parts.values()) * multiplier))
    return {"puan": points, "duzey": _level(points), "katkilar": parts, "sayilar": used, "carpan": multiplier}


def scan_document(path: Any) -> dict[str, Any] | None:
    """Maskeli kopyayı tarar ve skorlar; okunamayan belgede None (rapora yazılmaz)."""
    from .ozel_nitelikli import document_text

    try:
        text = document_text(path)
    except Exception:
        return None
    return score(scan(text)) if text.strip() else None
