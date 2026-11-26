"""UYAP belgeleri (.udf): ZIP içinde `content.xml`.

UDF bir ZIP paketidir. Belgenin bütün metni `content.xml` içindeki tek bir
`<content>` (CDATA) öğesindedir; paragraf, tablo ve biçim öğeleri bu metne
`startOffset`/`length` karakter konumlarıyla bağlanır. Bu yüzden maskeleme
UZUNLUĞU KORUYARAK yapılır: her bulgunun karakteri `█` olur (satır sonları
kalır), böylece konumlar, biçim, tablo ve paragraf yapısı bozulmaz. Uzunluğu
değiştiren yöntemler (etiket, takma ad…) UDF'de karartmaya çevrilir.

Gizli yerler: `documentproperties.xml` (yazar, kurum, belge no gibi özellikler)
boşaltılır, `sign.sgn` (elektronik imza; içerik değişince geçersiz olur)
çıkarılır. Çıktı yeniden okunur; değer herhangi bir XML parçasında kalmışsa ya
da metin uzunluğu değişmişse dosya yazılmaz. DOCTYPE içeren belge reddedilir.
"""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .detect import Finding, detect
from .names import name_hints
from .pdf import PdfError, _normalize, count_types, unique_path
from .rules import Rules, kacak_iletisi, kacak_kabul

UDF_EXTS = {".udf"}
MAX_BYTES = 50 * 1024 * 1024
MAX_UNZIPPED = 300 * 1024 * 1024

CONTENT_PART = "content.xml"
_PROPS_PART = "documentproperties.xml"
_SIGNATURE_PARTS = ("sign.sgn",)
_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp", ".emf", ".wmf", ".svg"}
_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, strip_cdata=False)


@dataclass
class UdfFinding:
    id: str
    finding: Finding  # start/end: önizleme metni içindeki konum
    replacement: str


@dataclass
class UdfScan:
    text: str  # önizleme: birimlerin alt alta hâli (ana metin tek birimdir)
    findings: list[UdfFinding]
    warnings: list[str] = field(default_factory=list)


def is_udf(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in UDF_EXTS


def _open(path: Path) -> zipfile.ZipFile:
    if not path.is_file():
        raise PdfError("Dosya bulunamadı")
    if path.stat().st_size > MAX_BYTES:
        raise PdfError(f"Dosya çok büyük; en fazla {MAX_BYTES // (1024 * 1024)} MB")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        raise PdfError("UDF dosyası açılamadı (bozuk ya da UDF olmayan bir dosya)") from None
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        z.close()
        raise PdfError("UDF dosyasının içeriği beklenmeyecek kadar büyük")
    if CONTENT_PART not in z.namelist():
        z.close()
        raise PdfError("Dosya bir UDF belgesi değil (content.xml yok)")
    return z


def _parse(data: bytes) -> etree._Element:
    if b"<!DOCTYPE" in data[:2000]:
        raise PdfError("Belgede beklenmeyen DOCTYPE; güvenlik nedeniyle açılmadı")
    try:
        return etree.fromstring(data, _PARSER)
    except etree.XMLSyntaxError:
        raise PdfError("Belgenin içi bozuk") from None


def _units(root: etree._Element) -> list[tuple[etree._Element, str]]:
    """Metni olan öğeler: (öğe, "text" | "tail"). Ana metin (`content`) ilk sırada."""
    out: list[tuple[etree._Element, str]] = []
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.text and el.text.strip():
            out.append((el, "text"))
        if el.tail and el.tail.strip() and el is not root:
            out.append((el, "tail"))
    return out


def _get(unit: tuple[etree._Element, str]) -> str:
    el, which = unit
    return (el.text if which == "text" else el.tail) or ""


def _blackout(value: str) -> str:
    return "".join(c if c in "\r\n" else "█" for c in value)


def _scan_root(root: etree._Element, rules: Rules):
    units = _units(root)
    texts = [_get(u) for u in units]
    hints = name_hints(texts) if rules.types["kisi_adi"].enabled else frozenset()
    findings: list[UdfFinding] = []
    base = 0
    for n, text in enumerate(texts):
        for f in detect(text, rules, hints, lead=n == 0):
            shifted = Finding(f.type, base + f.start, base + f.end, f.value, f.confidence, f.source)
            findings.append(UdfFinding(f"u:{n}:{f.start}:{f.end}", shifted, _blackout(f.value)))
        base += len(text) + 1  # önizlemede birimler "\n" ile ayrılır
    return units, texts, findings


def _notes(z: zipfile.ZipFile) -> list[str]:
    names = z.namelist()
    out = []
    if any(n in names for n in _SIGNATURE_PARTS):
        out.append("Belgede elektronik imza var; maskeli kopyada imza çıkarılır (içerik değiştiği için geçersiz olurdu).")
    others = [n for n in names if n not in (CONTENT_PART, _PROPS_PART, *_SIGNATURE_PARTS) and not n.endswith("/")]
    images = [n for n in others if Path(n).suffix.lower() in _IMAGE_SUFFIXES]
    if images:
        out.append(
            f"Belgede {len(images)} görsel var: UDF içindeki görseller taranmadı, maskeli kopyada olduğu gibi kalır. "
            "Kendiniz kontrol edin."
        )
    if len(others) > len(images):
        out.append("Belgede metin dışı başka dosyalar var; içleri taranmaz, maskeli kopyada olduğu gibi kalır.")
    out.append("Maskeli UDF'de metin uzunluğu korunur: tüm yöntemler karartma olarak uygulanır.")
    return out


def scan_udf(path: str | os.PathLike, rules: Rules) -> UdfScan:
    with _open(Path(path)) as z:
        root = _parse(z.read(CONTENT_PART))
        _units, texts, findings = _scan_root(root, rules)
        return UdfScan("\n".join(texts), findings, _notes(z))


def preview_text(path: str | os.PathLike) -> str:
    with _open(Path(path)) as z:
        return "\n".join(_get(u) for u in _units(_parse(z.read(CONTENT_PART))))


def _set(unit: tuple[etree._Element, str], text: str, cdata: bool) -> None:
    el, which = unit
    if which == "text":
        el.text = etree.CDATA(text) if cdata else text
    else:
        el.tail = text


def _scrub_props(data: bytes) -> bytes:
    """Belge özelliklerinin değerleri (öğe metni ve öznitelikler) boşaltılır; yapı kalır."""
    root = _parse(data)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.text and el.text.strip():
            el.text = ""
        if el.tail and el.tail.strip():
            el.tail = None
        for k in list(el.attrib):
            if k.lower() in ("key", "name", "type", "format_id"):
                continue
            el.attrib[k] = ""
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def _all_text(data: bytes) -> str:
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.endswith((".xml", ".rels")):
                continue
            raw = z.read(name)
            try:
                root = _parse(raw)
            except PdfError:
                parts.append(raw.decode("utf-8", "replace"))
                continue
            for el in root.iter():
                if isinstance(el.tag, str):
                    parts.append(el.text or "")
                    parts.extend(el.attrib.values())
                parts.append(el.tail or "")
                parts.append("\n")
    return "".join(parts)


def mask_udf(
    source: str | os.PathLike,
    target: str | os.PathLike,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    make_dirs: bool = False,
    counts: dict[str, int] | None = None,
) -> tuple[str, int, list[str]]:
    """Maskeli kopyayı yazar; (hedef yol, maskelenen sayısı, uyarılar) döner."""
    excluded = excluded_ids or set()
    src = Path(source).resolve()
    dst = Path(target).resolve()
    if src == dst:
        raise PdfError("Hedef, kaynak dosyanın kendisi olamaz")
    if dst.suffix.lower() != src.suffix.lower():
        dst = dst.with_suffix(src.suffix)
    if make_dirs:
        dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.parent.is_dir():
        raise PdfError("Hedef klasör bulunamadı")
    dst = unique_path(dst)

    with _open(src) as z:
        root = _parse(z.read(CONTENT_PART))
        units, texts, findings = _scan_root(root, rules)
        included = [f for f in findings if f.id not in excluded]
        by_unit: dict[int, list[UdfFinding]] = {}
        for f in included:
            by_unit.setdefault(int(f.id.split(":")[1]), []).append(f)
        for n, items in by_unit.items():
            chars = list(texts[n])
            offset = sum(len(t) + 1 for t in texts[:n])
            for f in items:
                s, e = f.finding.start - offset, f.finding.end - offset
                chars[s:e] = _blackout("".join(chars[s:e]))
            new = "".join(chars)
            if len(new) != len(texts[n]):
                raise PdfError("UDF maskelemesinde metin uzunluğu değişti. Dosya yazılmadı.")
            _set(units[n], new, cdata=units[n][0].getparent() is root and units[n][0].tag == "content")
        warnings = _notes(z)

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zd:
            for info in z.infolist():
                name = info.filename
                if name in _SIGNATURE_PARTS:
                    continue
                if name == CONTENT_PART:
                    data = etree.tostring(root, xml_declaration=True, encoding="UTF-8")
                elif name == _PROPS_PART:
                    data = _scrub_props(z.read(name))
                else:
                    data = z.read(name)
                new_info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                new_info.compress_type = zipfile.ZIP_DEFLATED
                zd.writestr(new_info, data)
    data = out.getvalue()

    # Çıktıyı yeniden oku: değer kalmış mı, metin uzunluğu ve yapı aynı mı.
    with zipfile.ZipFile(io.BytesIO(data)) as zo:
        again = _units(_parse(zo.read(CONTENT_PART)))
        if sum(len(_get(u)) for u in again) != sum(len(t) for t in texts):
            raise PdfError("UDF maskelemesinde metin uzunluğu değişti. Dosya yazılmadı.")
    text = _normalize(_all_text(data))
    kept = {_normalize(f.finding.value) for f in findings if f.id in excluded}
    gone: dict[str, str] = {}
    for f in included:
        gone.setdefault(_normalize(f.finding.value), f.finding.type)
    leaked = [tur for v, tur in gone.items() if v and v not in kept and v in text]
    if leaked and not kacak_kabul(leaked):
        raise PdfError(kacak_iletisi(leaked, "belgenin başka bir yerinde"))

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=dst.suffix, dir=dst.parent)
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(data)
        os.replace(tmp_name, dst)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    if counts is not None:
        count_types(counts, (f.finding.type for f in included))
    return str(dst), len(included), warnings
