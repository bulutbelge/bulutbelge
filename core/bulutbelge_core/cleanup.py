"""Temizlik özeti: maskeli kopyada silinen yazar, yorum, izlenen değişiklik ve meta veri.

Kaynak dosya okunur; yalnızca adetler ve alan adları döner. Yazar adı, yorum metni ve meta veri
değerleri hiçbir yerde tutulmaz ya da yazılmaz (rapora değer girmez).
Anahtarlar: yazar, yorum, izlenen_silme, izlenen_ekleme (adet); meta (dolu alan adları);
ek_dosya, form_alani (adet); xml_meta (var/yok). Boş olanlar dönmez.
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path
from typing import Any

import pymupdf
from lxml import etree

from . import office
from .documents import kind_of
from .pdf import PdfError

_COMMENT_TAGS = {"comment", "cm", "threadedComment"}  # Word/Excel yorumu, PowerPoint yorumu, Excel ileti dizisi
_CORE_LABELS = {
    "creator": "yazar",
    "lastModifiedBy": "son değiştiren",
    "title": "başlık",
    "subject": "konu",
    "keywords": "anahtar sözcükler",
    "description": "açıklama",
    "category": "kategori",
    "contentStatus": "durum",
    "lastPrinted": "son yazdırma",
    "revision": "düzeltme no",
    "version": "sürüm",
    "language": "dil",
    "identifier": "tanımlayıcı",
}
_APP_LABELS = {"Company": "şirket", "Manager": "yönetici", "HyperlinkBase": "bağlantı tabanı"}
_PDF_META_LABELS = {
    "author": "yazar",
    "title": "başlık",
    "subject": "konu",
    "keywords": "anahtar sözcükler",
    "creator": "oluşturan uygulama",
    "producer": "üretici uygulama",
    "creationDate": "oluşturma tarihi",
    "modDate": "değiştirme tarihi",
    "trapped": "trapped",
}


def _compact(summary: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in summary.items() if v}


def _office_meta(z: zipfile.ZipFile) -> list[str]:
    names = set(z.namelist())
    found: list[str] = []
    for part in office._PROPS_PARTS:
        if part not in names:
            continue
        for el in office.parse(z.read(part)).iter():
            if not isinstance(el.tag, str) or not (el.text or "").strip():
                continue
            local = etree.QName(el).localname
            if part == "docProps/core.xml" and local in _CORE_LABELS:
                found.append(_CORE_LABELS[local])
            elif part == "docProps/app.xml" and local in office._APP_PERSONAL:
                found.append(_APP_LABELS[local])
            elif part == "docProps/custom.xml" and len(el) == 0 and local != "Properties":
                found.append("özel özellik")
    return found


def _office_summary(path: Path, fmt: office.OfficeFormat) -> dict[str, Any]:
    authors: set[str] = set()
    comments = deleted = inserted = 0
    with office.open_zip(path, fmt) as z:
        for name in z.namelist():
            if fmt.text_parts.match(name):
                for el in office.parse(z.read(name)).iter():
                    if not isinstance(el.tag, str):
                        continue
                    local = etree.QName(el).localname
                    if local in _COMMENT_TAGS:
                        comments += 1
                    if el.tag in fmt.removed:
                        deleted += 1
                    elif fmt is office.WORD and local in ("ins", "moveTo"):
                        inserted += 1
                    for attr in fmt.person_attrs:
                        if (el.get(attr) or "").strip() and attr.endswith("author"):
                            authors.add(el.get(attr))
                    if el.tag in fmt.people_texts and (el.text or "").strip():
                        authors.add(el.text)
            elif name in fmt.people_parts:
                for el in office.parse(z.read(name)).iter():
                    if not isinstance(el.tag, str):
                        continue
                    for attr in fmt.people_parts[name][:1]:  # ad / görünen ad
                        if (el.get(attr) or "").strip():
                            authors.add(el.get(attr))
        meta = _office_meta(z)
    return _compact(
        {
            "yazar": len(authors),
            "yorum": comments,
            "izlenen_silme": deleted,
            "izlenen_ekleme": inserted,
            "meta": sorted(set(meta)),
        }
    )


def _pdf_summary(path: Path) -> dict[str, Any]:
    doc = pymupdf.open(path)
    try:
        if not doc.is_pdf or doc.needs_pass:
            return {}
        meta = [label for key, label in _PDF_META_LABELS.items() if (doc.metadata or {}).get(key)]
        authors: set[str] = set()
        comments = fields = 0
        for page in doc:
            for annot in page.annots() or []:
                if annot.type[0] == pymupdf.PDF_ANNOT_REDACT:
                    continue
                comments += 1
                who = (annot.info or {}).get("title")
                if who:
                    authors.add(who)
            fields += sum(1 for _ in (page.widgets() or []))
        return _compact(
            {
                "yazar": len(authors),
                "yorum": comments,
                "meta": meta,
                "xml_meta": bool((doc.get_xml_metadata() or "").strip()),
                "ek_dosya": doc.embfile_count(),
                "form_alani": fields,
            }
        )
    finally:
        doc.close()


def cleanup_summary(source: str | os.PathLike) -> dict[str, Any] | None:
    """Kaynağın maskeli kopyada silinecek yazar, yorum, izlenen değişiklik ve meta veri özeti.

    Okunamazsa ya da biçim desteklenmiyorsa (metin, görsel) None döner; boş sonuç {} olur.
    """
    p = Path(source)
    try:
        kind = kind_of(p)
        if kind == "pdf":
            return _pdf_summary(p)
        fmt = office.format_of(p)
        if fmt is not None:
            return _office_summary(p, fmt)
    except (PdfError, OSError, zipfile.BadZipFile, etree.XMLSyntaxError, RuntimeError, ValueError):
        return None
    return None
