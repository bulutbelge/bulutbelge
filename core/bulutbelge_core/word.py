"""Word belgeleri (.docx). Ortak Office motorunun Word ayarlarıyla kullanımı.

Ayrıntılar (birim, parça, gizli alan temizliği, kaçak denetimi): `office.py`.
Word'e özgü olanlar: izlenen değişikliklerde silinmiş metin (`w:del`,
`w:moveFrom`) tamamen kaldırılır, yorum ve değişiklik yazarları (`w:author`,
`w:initials`) boşaltılır, alan kodları (`w:instrText`, ör. mailto) da taranır.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import office
from .office import MAX_BYTES, OfficeScan, all_text  # noqa: F401  (dışarıya açılan adlar)
from .rules import Rules

WORD_EXTS = set(office.WORD.exts)


def is_word(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in WORD_EXTS


def scan_word(path: str | os.PathLike, rules: Rules) -> OfficeScan:
    return office.scan(path, office.WORD, rules)


def mask_word(
    source: str | os.PathLike,
    target: str | os.PathLike,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    make_dirs: bool = False,
) -> tuple[str, int, list[str]]:
    return office.mask(source, target, office.WORD, rules, excluded_ids, make_dirs)
