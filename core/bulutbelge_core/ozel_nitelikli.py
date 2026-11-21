"""Özel nitelikli kişisel veri uyarısı (KVKK m.6).

Sözcük tabanlı ve yaklaşıktır: sağlık, din, etnik köken, sendika, ceza vb. konulara ait
sözcükler metinde geçiyorsa kategori başına geçiş sayısı döner. Bu bir bulgu değildir;
maskelenmez, kişiye ait olduğu da doğrulanmaz, yalnızca "bu belgede özel nitelikli veri
olabilir, elle bakın" uyarısıdır. Eşleşen sözcük ve çevresi hiçbir yere yazılmaz,
yalnızca kategori adı ve sayı döner.
"""

from __future__ import annotations

import re
from pathlib import Path

from .documents import kind_of

_L = "a-zçğıöşü"

# Kategori → köklerin listesi. Ek alabilirler (3 harfli köklerde ek yok, 4 harflilerde en çok 2, diğerlerinde 6 harf);
# boşluk, birden çok boşluğu karşılar.
CATEGORIES: dict[str, tuple[str, ...]] = {
    "Sağlık": (
        "hastalık", "hastalığ", "teşhis", "tedavi", "ameliyat", "diyabet", "şeker hastası", "kanser",
        "epilepsi", "hiv", "aids", "depresyon", "psikiyatri", "engelli", "sağlık raporu", "kemoterapi",
        "hamilelik", "gebelik", "covid", "reçete",
    ),
    "Din ve inanç": (
        "din", "dini", "dinî", "islam", "müslüman", "hristiyan", "yahudi", "budist", "alevi", "sünni",
        "mezhep", "ateist", "namaz", "cemaat",
    ),
    "Irk ve etnik köken": ("etnik", "ırk", "kürt", "ermeni", "çingene", "azınlık"),
    "Siyasi düşünce": ("siyasi parti", "siyasi görüş", "parti üyeliği", "parti üyesi"),
    "Dernek, vakıf ve sendika üyeliği": ("sendika", "sendikal", "dernek üyeliği", "dernek üyesi", "vakıf üyeliği"),
    "Ceza mahkûmiyeti ve güvenlik tedbirleri": (
        "sabıka", "mahkumiyet", "mahkûmiyet", "hükümlü", "adli sicil", "cezaevi", "tutuklu", "tutuklama",
        "hapis cezası", "güvenlik tedbiri", "gözaltı",
    ),
    "Cinsel hayat": ("cinsel yönelim", "cinsel hayat", "eşcinsel", "transseksüel"),
    "Biyometrik ve genetik veri": ("parmak izi", "genetik", "dna", "retina", "biyometrik", "yüz tanıma"),
}


def _compile(stems: tuple[str, ...]) -> re.Pattern[str]:
    alts = []
    for s in stems:
        cap = 0 if len(s) <= 3 else 2 if len(s) <= 4 else 6
        alts.append(re.escape(s).replace(r"\ ", r"\s+") + f"[{_L}]{{0,{cap}}}")
    return re.compile(rf"(?<![{_L}0-9])(?:{'|'.join(alts)})(?![{_L}0-9])")


_PATTERNS = {name: _compile(stems) for name, stems in CATEGORIES.items()}


def _lower(text: str) -> str:
    return text.replace("İ", "i").replace("I", "ı").lower()


def scan_special(text: str) -> dict[str, int]:
    """Kategori adı → geçiş sayısı (yalnızca sıfırdan büyükler)."""
    low = _lower(text)
    out = {}
    for name, pat in _PATTERNS.items():
        n = len(pat.findall(low))
        if n:
            out[name] = n
    return out


def special_warnings(counts: dict[str, int]) -> list[str]:
    """Değer taşımayan uyarı satırları; kategori başına bir tane."""
    return [
        f"Özel nitelikli veri olabilir (KVKK m.6): {name} ile ilgili sözcükler geçiyor ({n} yerde). "
        "Bu bir bulgu değildir, maskelenmez; belgeyi paylaşmadan önce elle kontrol edin."
        for name, n in counts.items()
    ]


def document_text(path: str | Path) -> str:
    """Belgenin düz metni (yalnızca bellekte); okunamayan ya da taranmış belgede boş."""
    from . import office
    from .readout import _office_text, _pdf_text
    from .textdoc import read_text_doc

    p = Path(path)
    kind = kind_of(p)
    if kind == "metin":
        return read_text_doc(p)
    if kind == "eposta":
        from .eposta import preview_text

        return preview_text(p)
    if kind == "udf":
        from .udf import preview_text as udf_preview

        return udf_preview(p)
    if kind in ("word", "sunum", "tablo"):
        fmt = office.format_of(p)
        return _office_text(p, fmt) if fmt else ""
    if kind == "gorsel":
        return ""
    return _pdf_text(p, False)[0]


def scan_document(path: str | Path) -> dict[str, int]:
    """Belgeyi tarar; belge açılamazsa uyarı üretmez (asıl işlem kendi hatasını verir)."""
    try:
        return scan_special(document_text(path))
    except Exception:
        return {}
