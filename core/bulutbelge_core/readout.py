"""Maskeli okuma: belgenin metnini maskelenmiş olarak döndürür (ajan komutu, TAKIP 1.37).

Metin ayrıca maskelenmez; belge her zamanki maskeleyiciyle (kaçak denetimi dahil)
geçici bir klasöre maskelenir ve metin o maskeli kopyadan çıkarılır. Böylece
okuma çıktısı, kullanıcının kaydedeceği maskeli kopyada olmayan hiçbir şeyi
taşımaz. Geçici klasör işlem bitince silinir; orijinal değer bellekte kalır.

Sınırlar: taranmış sayfa ve fotoğrafın metin katmanı yoktur, çıktıda yalnızca
not olarak geçer (OCR ile okunup maskelenmiş görüntü yeniden okunmaz).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from . import office
from .gecici import klasor_ac
from .documents import kind_of
from .eposta import mask_eml, preview_text
from .udf import mask_udf, preview_text as udf_preview
from .ozel_nitelikli import scan_special, special_warnings
from .pdf import PdfError, mask_pdf
from .rules import Rules
from .textdoc import mask_text_doc, read_text_doc

MAX_CHARS = 2_000_000


@dataclass
class MaskedRead:
    format: str
    text: str
    masked: int
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _pdf_text(path: Path, image: bool) -> tuple[str, list[str]]:
    if image:
        return "", ["Görselin metin katmanı yok; okuma çıktısında içerik yer almaz (maskeli kopya yazılabilir)."]
    parts, empty = [], []
    with pymupdf.open(path) as doc:
        for i, page in enumerate(doc, 1):
            text = page.get_text().strip()
            if not text:
                empty.append(i)
            parts.append(f"--- Sayfa {i} ---\n{text}")
    notes = []
    if empty:
        notes.append(
            f"Metin katmanı olmayan sayfalar (taranmış olabilir): {', '.join(map(str, empty))}. "
            "Bu sayfaların içeriği okuma çıktısında yer almaz."
        )
    return "\n\n".join(parts), notes


def _office_text(path: Path, fmt: office.OfficeFormat) -> str:
    if fmt is office.EXCEL:
        out = []
        for sheet in office.sheet_preview(path, max_rows=100_000, max_cols=500):
            out.append(f"--- Sayfa: {sheet['name']} ---")
            for row in sheet["rows"]:
                out.append("\t".join(c["text"] for c in row["cells"]).rstrip("\t"))
        return "\n".join(out)
    out = []
    with office.open_zip(path, fmt) as z:
        for name in sorted(z.namelist(), key=office._reading_order(fmt)):
            if not fmt.text_parts.match(name):
                continue
            lines = [office.unit_text(s) for _u, s in office.units(fmt, office.parse(z.read(name)))]
            lines = [x for x in lines if x.strip()]
            if lines:
                out.append(f"--- {name} ---")
                out.extend(lines)
    return "\n".join(out)


def read_masked(source: str | os.PathLike, rules: Rules) -> MaskedRead:
    src = Path(source)
    if not src.is_file():
        raise PdfError("Dosya bulunamadı")
    kind = kind_of(src)
    counts: dict[str, int] = {}
    tmp = klasor_ac("bulutbelge-okuma-")
    try:
        target = tmp / f"maskeli{src.suffix.lower()}"
        if kind == "metin":
            out, masked, warnings = mask_text_doc(src, target, rules, counts=counts)
            text, notes = read_text_doc(out), []
        elif kind == "eposta":
            out, masked, warnings = mask_eml(src, target, rules, counts=counts)
            text, notes = preview_text(out), []
        elif kind == "udf":
            out, masked, warnings = mask_udf(src, target, rules, counts=counts)
            text, notes = udf_preview(out), []
        elif kind in ("word", "sunum", "tablo"):
            fmt = office.format_of(src)
            assert fmt is not None
            out, masked, warnings = office.mask(src, target, fmt, rules, counts=counts)
            text, notes = _office_text(Path(out), fmt), []
        else:
            result = mask_pdf(src, target, rules, counts=counts)
            out, masked, warnings = result.target, result.masked, result.warnings
            text, notes = _pdf_text(Path(out), kind == "gorsel")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if len(text) > MAX_CHARS:
        text = text[:MAX_CHARS]
        notes.append(f"Çıktı {MAX_CHARS:,} karakterde kesildi.".replace(",", "."))
    # Özel nitelikli sözcükler maskelenmez; maskeli metinde taranır (TAKIP 1.46).
    special = special_warnings(scan_special(text))
    return MaskedRead(kind, text, masked, counts, [*warnings, *notes, *special])
