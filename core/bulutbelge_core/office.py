"""Office belgeleri (Word .docx, PowerPoint .pptx, Excel .xlsx) için ortak motor.

Üçü de içinde XML dosyaları olan bir ZIP arşividir (Office Open XML). Metin,
biçime göre farklı öğelerdedir ama yapı aynıdır:

| Biçim      | "Birim" (birlikte taranan metin)          | Metin öğesi       |
|------------|-------------------------------------------|-------------------|
| Word       | paragraf `w:p`                            | `w:t`, `w:instrText` |
| PowerPoint | paragraf `a:p`, eski yorum `p:text`       | `a:t`             |
| Excel      | paylaşılan metin `si`, satır içi `is`, sayı hücresi `v`, yorum `text` | `t` |

Office bir cümleyi biçim değişikliklerinde parçalara (run) böler; bir TC
numarası bile "12345" + "678950" diye iki parçada olabilir. Bu yüzden her birim
bütün olarak taranır, bulgular sonra parçalara geri eşlenir ve değer
parçaların içinden silinir. Biçim, tablo, görsel, formül yapısı korunur.

Değer yalnızca görünen metinden değil, gizli yerlerden de silinir: izlenen
değişiklikte silinmiş metin, yorum yazarları, belge özellikleri, bulgu içeren
dış bağlantı hedefleri. Kaçak denetimi arşivdeki TÜM XML parçalarının metnini ve
özniteliklerini okur; işaretli bir değer herhangi bir yerde kalmışsa dosya
yazılmaz.
"""

from __future__ import annotations

import io
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from lxml import etree

from .gecici import gecici_klasor
from .detect import MEDIUM, Finding, detect
from .image import IMAGE_EXTS
from .loose import find_split_cells
from .pdf import PdfError, _normalize, count_types, unique_path
from .names import initials, name_hints
from . import tablo
from .rules import BLACKOUT, BLUR, INITIALS, KEEP_LAST4, LABEL, PSEUDONYM, Rules
from .validators import digits_only

MAX_BYTES = 50 * 1024 * 1024
# ZIP bombasına karşı açılmış toplam boyut sınırı.
MAX_UNZIPPED = 300 * 1024 * 1024
BLACKOUT_TEXT = "█████"

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
P = "{http://schemas.openxmlformats.org/presentationml/2006/main}"
S = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
TC = "{http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments}"
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"

_PROPS_PARTS = ("docProps/core.xml", "docProps/app.xml", "docProps/custom.xml")
_APP_PERSONAL = {"Company", "Manager", "HyperlinkBase"}

_PARSER = etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=False, remove_blank_text=False)


@dataclass(frozen=True)
class OfficeFormat:
    name: str
    exts: frozenset[str]
    main_part: str
    text_parts: re.Pattern[str]
    units: tuple[str, ...]  # birlikte taranan öğeler
    texts: tuple[str, ...]  # birimin içindeki metin öğeleri
    separators: dict[str, str]  # sekme, satır sonu gibi öğeler → ayraç
    self_text: tuple[str, ...] = ()  # metni doğrudan kendisinde olan birimler
    removed: tuple[str, ...] = ()  # tamamen kaldırılan öğeler (izlenen silmeler)
    person_attrs: tuple[str, ...] = ()  # metin parçalarında boşaltılan kişi öznitelikleri
    people_parts: dict[str, tuple[str, ...]] = field(default_factory=dict)  # yazar listeleri: parça → öznitelikler
    people_texts: tuple[str, ...] = ()  # metni kişi adı olan öğeler (Excel yorum yazarları)


WORD = OfficeFormat(
    name="Word",
    exts=frozenset({".docx"}),
    main_part="word/document.xml",
    text_parts=re.compile(r"^word/(document|header\d*|footer\d*|footnotes|endnotes|comments)\.xml$"),
    units=(W + "p",),
    texts=(W + "t", W + "instrText"),
    separators={W + "tab": "\t", W + "br": "\n", W + "cr": "\n"},
    removed=(W + "del", W + "moveFrom"),
    person_attrs=(W + "author", W + "initials"),
)

POWERPOINT = OfficeFormat(
    name="PowerPoint",
    exts=frozenset({".pptx"}),
    main_part="ppt/presentation.xml",
    text_parts=re.compile(
        r"^ppt/(slides/slide\d+|notesSlides/notesSlide\d+|slideLayouts/slideLayout\d+|slideMasters/slideMaster\d+|"
        r"comments/[^/]+|charts/chart\d+)\.xml$"
    ),
    units=(A + "p", P + "text"),
    texts=(A + "t",),
    separators={A + "br": "\n"},
    self_text=(P + "text",),
    people_parts={"ppt/commentAuthors.xml": ("name", "initials"), "ppt/authors.xml": ("name", "initials", "userId")},
)

EXCEL = OfficeFormat(
    name="Excel",
    exts=frozenset({".xlsx"}),
    main_part="xl/workbook.xml",
    # Yorumlar Excel'de xl/comments1.xml, bazı araçlarda xl/comments/comment1.xml olarak yazılır.
    text_parts=re.compile(
        r"^xl/(sharedStrings|worksheets/sheet\d+|comments\d*|comments/[^/]+|threadedComments/[^/]+)\.xml$"
    ),
    units=(S + "si", S + "is", S + "v", S + "text", TC + "text"),
    texts=(S + "t",),
    separators={},
    self_text=(S + "v", TC + "text"),
    people_parts={"xl/persons/person.xml": ("displayName", "userId", "providerId")},
    people_texts=(S + "author",),
)

FORMATS = (WORD, POWERPOINT, EXCEL)


def format_of(path: str | os.PathLike) -> OfficeFormat | None:
    ext = Path(path).suffix.lower()
    return next((f for f in FORMATS if ext in f.exts), None)


@dataclass
class _Segment:
    node: etree._Element | None  # metin öğesi; ayraç için None
    start: int
    text: str


@dataclass
class OfficeFinding:
    id: str
    finding: Finding
    replacement: str
    part: str
    unit: int  # parçadaki birim sırası


@dataclass
class OfficeScan:
    findings: list[OfficeFinding]
    warnings: list[str] = field(default_factory=list)


# ---------------------------------------------------------------- okuma


def open_zip(path: Path, fmt: OfficeFormat) -> zipfile.ZipFile:
    if not path.is_file():
        raise PdfError("Dosya bulunamadı")
    if path.stat().st_size > MAX_BYTES:
        raise PdfError(f"Dosya çok büyük; en fazla {MAX_BYTES // (1024 * 1024)} MB")
    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        # Parolalı Office dosyası ZIP değil, şifreli OLE dosyasıdır; eski .doc/.xls/.ppt da öyle.
        with path.open("rb") as f:
            ole = f.read(8) == b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"
        if ole:
            raise PdfError(
                f"{fmt.name} dosyası eski ikili biçimde (.doc/.xls/.ppt) ya da parolalı; "
                f"desteklenmiyor. Office'te {fmt.name} (.docx/.xlsx/.pptx) olarak kaydedip deneyin"
            ) from None
        raise PdfError(f"{fmt.name} dosyası açılamadı (parolalı, bozuk ya da eski biçimde olabilir)") from None
    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
        z.close()
        raise PdfError(f"{fmt.name} dosyasının içeriği beklenmeyecek kadar büyük")
    if fmt.main_part not in z.namelist():
        z.close()
        raise PdfError(f"Dosya bir {fmt.name} belgesi değil")
    return z


def parse(data: bytes) -> etree._Element:
    if b"<!DOCTYPE" in data[:2000]:
        raise PdfError("Belgede beklenmeyen DOCTYPE; güvenlik nedeniyle açılmadı")
    try:
        return etree.fromstring(data, _PARSER)
    except etree.XMLSyntaxError:
        raise PdfError("Belgenin içi bozuk") from None


def _is_unit(fmt: OfficeFormat, el: etree._Element) -> bool:
    if el.tag not in fmt.units:
        return False
    if el.tag == S + "v":
        # Excel: yalnızca sayı ve formül metni sonuçları; paylaşılan metin dizini (t="s") değil.
        return el.getparent() is not None and el.getparent().get("t") in (None, "n", "str")
    return True


def units(fmt: OfficeFormat, root: etree._Element) -> list[tuple[etree._Element, list[_Segment]]]:
    """Parçadaki birimler ve her birinin metin parçaları (belge sırasıyla)."""
    out = []
    unit_tags = set(fmt.units)
    for u in root.iter(*fmt.units):
        if not _is_unit(fmt, u):
            continue
        segments: list[_Segment] = []
        if u.tag in fmt.self_text:
            segments.append(_Segment(u, 0, u.text or ""))
        else:
            pos = 0
            for node in u.iter(*fmt.texts, *fmt.separators):
                # İç içe başka bir birime (metin kutusu içindeki paragraf) ait olan orada işlenir.
                owner = next((a for a in node.iterancestors() if a.tag in unit_tags), None)
                if owner is not u:
                    continue
                if node.tag in fmt.texts:
                    text = node.text or ""
                    segments.append(_Segment(node, pos, text))
                else:
                    text = fmt.separators[node.tag]
                    segments.append(_Segment(None, pos, text))
                pos += len(text)
        out.append((u, segments))
    return out


def unit_text(segments: list[_Segment]) -> str:
    return "".join(s.text for s in segments)


def _remove_tracked(fmt: OfficeFormat, root: etree._Element) -> int:
    removed = 0
    for tag in fmt.removed:
        for el in list(root.iter(tag)):
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
                removed += 1
    return removed


def _replacement(f: Finding, rules: Rules) -> str:
    if rules.method_for(f.type, f.source) in (BLACKOUT, BLUR):
        # Office'te bulanık dolgu yok; ikisi de sabit uzunlukta karartma (uzunluk sızmasın).
        return BLACKOUT_TEXT
    return rules.replacement_for(f, ascii_only=False)


def load(z: zipfile.ZipFile, fmt: OfficeFormat, rules: Rules) -> tuple[dict[str, etree._Element], list[OfficeFinding], int]:
    roots: dict[str, etree._Element] = {}
    findings: list[OfficeFinding] = []
    removed = 0
    pending: list[tuple[str, int, str]] = []
    for name in sorted(z.namelist(), key=_reading_order(fmt)):
        if not fmt.text_parts.match(name):
            continue
        root = parse(z.read(name))
        removed += _remove_tracked(fmt, root)
        roots[name] = root
        for ui, (_u, segments) in enumerate(units(fmt, root)):
            text = unit_text(segments)
            if text.strip():
                pending.append((name, ui, text))
    # Belge düzeyi ad ipuçları (e-posta adreslerinden); ilk metin parçası belgenin başı sayılır.
    hints = name_hints([t for _n, _u, t in pending]) if rules.types["kisi_adi"].enabled else frozenset()
    for n, (name, ui, text) in enumerate(pending):
        for f in detect(text, rules, hints, lead=n == 0):
            findings.append(
                OfficeFinding(f"o:{name}:{ui}:{f.start}:{f.end}", f, _replacement(f, rules), name, ui)
            )
    if fmt is EXCEL:
        findings.extend(_split_cell_findings(fmt, roots, findings, rules))
    return roots, findings, removed


SPLIT_NOTE = "hücreler arası bölünmüş değer"


def _col_number(ref: str) -> int:
    n = 0
    for ch in ref:
        if not ch.isalpha():
            break
        n = n * 26 + ord(ch.upper()) - 64
    return n


def _split_cell_findings(
    fmt: OfficeFormat, roots: dict[str, etree._Element], existing: list[OfficeFinding], rules: Rules
) -> list[OfficeFinding]:
    """Yan yana hücrelere bölünmüş TC/IBAN/telefon (TAKIP 1.62).

    Satırdaki ardışık sütunların metni birleştirilir; bulunan değerin her hücresi (paylaşılan metin
    hücresiyse o metin) kendi bulgusu olur. Hücre başına bir bulgu: kullanıcı hücreleri ayrı seçebilir.
    """
    shared = roots.get("xl/sharedStrings.xml")
    shared_texts = {
        i: unit_text(segs) for i, (_u, segs) in enumerate(units(fmt, shared))
    } if shared is not None else {}
    out: list[OfficeFinding] = []
    seen = {f.id for f in existing}
    for name, root in roots.items():
        if not re.match(r"^xl/worksheets/sheet\d+\.xml$", name):
            continue
        sheet_units = units(fmt, root)  # elemanlar canlı kalsın (lxml vekilleri)
        index = {u: i for i, (u, _s) in enumerate(sheet_units)}
        for row in root.iter(S + "row"):
            run: list[tuple[int, str, int, str]] = []  # (sütun, parça, birim sırası, birim metni)
            groups: list[list[tuple[int, str, int, str]]] = []
            for c in row.iter(S + "c"):
                t = c.get("t")
                v = c.find(S + "v")
                cell: tuple[str, int, str] | None = None
                if t == "s" and v is not None and (v.text or "").strip().isdigit():
                    k = int(v.text)
                    if k in shared_texts:
                        cell = ("xl/sharedStrings.xml", k, shared_texts[k])
                elif t in (None, "n", "str") and v is not None and v in index:
                    cell = (name, index[v], v.text or "")
                elif t == "inlineStr" and c.find(S + "is") is not None and c.find(S + "is") in index:
                    is_ = c.find(S + "is")
                    cell = (name, index[is_], "".join(x.text or "" for x in is_.iter(S + "t")))
                col = _col_number(c.get("r", ""))
                if cell is None or not col or (run and col != run[-1][0] + 1):
                    if run:
                        groups.append(run)
                    run = []
                    if cell is None or not col:
                        continue
                run.append((col, *cell))
            if run:
                groups.append(run)
            for grp in groups:
                if len(grp) < 2:
                    continue
                for kind, i, j, _conf in find_split_cells([g[3] for g in grp]):
                    if not rules.types[kind].enabled:
                        continue
                    for _col, part, ui, text in grp[i : j + 1]:
                        fid = f"o:{part}:{ui}:0:{len(text)}"
                        if fid in seen or any(f.part == part and f.unit == ui for f in existing + out):
                            continue
                        seen.add(fid)
                        f = Finding(kind, 0, len(text), text, MEDIUM, SPLIT_NOTE)
                        out.append(OfficeFinding(fid, f, _replacement(f, rules), part, ui))
    return out


def _reading_order(fmt: OfficeFormat):
    """Parçaların okunma sırası: ana metin, sonra notlar, en son yorumlar.

    Takma adlar bu sırayla numaralanır; listedeki ilk kişi "Kişi-1" olsun, yorumdaki kişi değil.
    """

    def key(name: str) -> tuple:
        low = name.lower()
        return (name != fmt.main_part, "comment" in low, "notes" in low, _natural(name))

    return key


def _natural(name: str) -> list:
    """slide2 < slide10 sıralaması."""
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", name)]


def warnings_for(z: zipfile.ZipFile, fmt: OfficeFormat, roots: dict[str, etree._Element], removed: int) -> list[str]:
    names = z.namelist()
    out = []
    media = [n for n in names if "/media/" in n]
    unscanned = [n for n in media if not _is_scannable_media(n)]
    if unscanned:
        out.append(
            f"Belgede {len(unscanned)} görsel var. Görsellerdeki yazı ve yüzler taranmaz; gerekirse belgeyi PDF'e "
            "çevirip “Alan seç” ile maskeleyin."
        )
    if removed:
        out.append("Belgede izlenen değişiklik var. Silinmiş metin maskeli kopyada tamamen kaldırılır.")
    if any("/embeddings/" in n for n in names):
        out.append("Belgede gömülü dosya (başka bir belge ya da tablo) var; içi taranmaz, maskeli kopyada silinir.")
    if any("comment" in n.lower() for n in roots):
        out.append("Belgede yorum var. Yorumlar da taranır; yorum yazarlarının adı silinir.")
    if fmt is EXCEL:
        out.append(
            "Excel'de tarih biçimli hücreler (doğum tarihi gibi) sayı olarak saklanır ve bu türde bulunamaz; "
            "gerekirse sütunu metin olarak kaydedin."
        )
    return out


def _is_scannable_media(name: str) -> bool:
    return "/media/" in name and Path(name).suffix.lower() in IMAGE_EXTS


def _media_findings(data: bytes, suffix: str, rules: Rules) -> list | None:
    """Gömülü görseli görsel dosya gibi tarar (yüz + OCR); açılamazsa None.

    Görsel yalnızca geçici klasöre yazılır, iş bitince silinir.
    """
    from .pdf import scan_pdf

    with gecici_klasor("bb-gorsel-") as tmp:
        src = Path(tmp) / f"g{suffix}"
        src.write_bytes(data)
        try:
            return scan_pdf(src, rules).findings
        except Exception:
            return None


def _mask_media(data: bytes, suffix: str, rules: Rules) -> tuple[bytes, int, bool]:
    """Görseli maskeler: (yeni veri, maskelenen sayısı, taranabildi mi).

    Bulgu yoksa görsel olduğu gibi kalır (yeniden kodlama kaliteyi bozmasın).
    """
    from .pdf import mask_pdf

    found = _media_findings(data, suffix, rules)
    if found is None:
        return data, 0, False
    if not found:
        return data, 0, True
    with gecici_klasor("bb-gorsel-") as tmp:
        src = Path(tmp) / f"g{suffix}"
        src.write_bytes(data)
        try:
            res = mask_pdf(src, Path(tmp) / f"c{suffix}", rules)
        except Exception:
            # Maskelenemeyen görsel kopyaya girmez (değer görselde kalmasın).
            raise PdfError("Belgedeki bir görselde bulgu var ama görsel maskelenemedi. Dosya yazılmadı.") from None
        return Path(res.target).read_bytes(), len(found), True


def _media_warnings(scanned: int, masked: int, failed: int) -> list[str]:
    from .ocr import ocr_available

    out = []
    if masked:
        out.append(
            f"Belgedeki görsellerde {masked} bulgu (yüz, görsel içindeki yazı) bulundu ve maskeli kopyada silindi. "
            "Görsel bulguları ayrı ayrı onaylanmaz; sonucu maskeli kopyada kontrol edin."
        )
    if scanned and not ocr_available():
        out.append("Belgedeki görsellerde yazı okunamadı (OCR dil dosyaları kurulu değil); yalnızca yüz tarandı.")
    if failed:
        out.append(f"Belgede {failed} görsel açılamadı; taranmadı ve kopyada olduğu gibi kaldı.")
    return out


def scan(path: str | os.PathLike, fmt: OfficeFormat, rules: Rules) -> OfficeScan:
    with open_zip(Path(path), fmt) as z:
        roots, findings, removed = load(z, fmt, rules)
        warnings = warnings_for(z, fmt, roots, removed)
        found = failed = scanned = 0
        for name in z.namelist():
            if not _is_scannable_media(name):
                continue
            res = _media_findings(z.read(name), Path(name).suffix.lower(), rules)
            if res is None:
                failed += 1
                continue
            scanned += 1
            found += len(res)
        warnings += _media_warnings(scanned, found, failed)
    return OfficeScan(findings, warnings)


# ---------------------------------------------------------------- maskeleme


def _apply(fmt: OfficeFormat, roots: dict[str, etree._Element], included: list[OfficeFinding]) -> None:
    by_unit: dict[tuple[str, int], list[OfficeFinding]] = {}
    for f in included:
        by_unit.setdefault((f.part, f.unit), []).append(f)
    for part, root in roots.items():
        all_units = units(fmt, root)
        for (p, ui), items in by_unit.items():
            if p == part:
                el, segments = all_units[ui]
                _apply_unit(segments, items)
                if el.tag == S + "v":
                    _number_to_text(el)


def _apply_unit(segments: list[_Segment], items: list[OfficeFinding]) -> None:
    # Her metin öğesi için düzenlemeler: (yerel başlangıç, yerel bitiş, yeni metin).
    edits: dict[int, list[tuple[int, int, str]]] = {}
    for f in items:
        start, end = f.finding.start, f.finding.end
        first = True
        for i, seg in enumerate(segments):
            s, e = max(start, seg.start), min(end, seg.start + len(seg.text))
            if s >= e or seg.node is None:
                continue
            edits.setdefault(i, []).append((s - seg.start, e - seg.start, f.replacement if first else ""))
            first = False
    for i, changes in edits.items():
        node = segments[i].node
        text = node.text or ""
        for s, e, new in sorted(changes, reverse=True):
            text = text[:s] + new + text[e:]
        node.text = text
        if node.tag in (W + "t", S + "t"):
            node.set(XML_SPACE, "preserve")


def _number_to_text(v: etree._Element) -> None:
    """Maskelenen Excel sayı hücresini metin hücresine çevirir (sayı yerine "█████" yazılamaz).

    Hücrede formül varsa o da kaldırılır; aksi hâlde Excel açılışta değeri yeniden hesaplardı.
    """
    cell = v.getparent()
    text = v.text or ""
    cell.remove(v)
    for f in cell.findall(S + "f"):
        cell.remove(f)
    cell.set("t", "inlineStr")
    is_ = etree.SubElement(cell, S + "is")
    t = etree.SubElement(is_, S + "t")
    t.text = text
    t.set(XML_SPACE, "preserve")


def _scrub_people(fmt: OfficeFormat, root: etree._Element) -> None:
    for el in root.iter():
        for attr in fmt.person_attrs:
            if attr in el.attrib:
                el.set(attr, "")
        if el.tag in fmt.people_texts:
            el.text = ""


_TEXT_ATTRS = frozenset({"descr", "title", "tooltip", "alt", "caption"})  # name/label yapıyı bozabilir (sayfa adı, tanımlı ad)


def _sweep_attributes(roots: dict[str, etree._Element], included: list[OfficeFinding], rules: Rules) -> None:
    """Öznitelik değerlerinde (görsel alternatif metni `descr`, köprü ipucu `tooltip` vb.) kalan değerleri değiştirir.

    Bulgular metin öğelerinde uygulanır; aynı değer bir özniteliğin içinde de geçebilir ve orada kalırdı
    (TAKIP 1.57: gizli-word.docx görsel alternatif metni). Metin öznitelikleri ayrıca taranır. Her bulgunun değeri, bulunduğu yerin yerine
    konan metinle aynı biçimde değiştirilir; uzun değerler önce.
    """
    pairs = sorted(
        {(f.finding.value, f.replacement) for f in included if len(f.finding.value) >= 3 and f.finding.value != f.replacement},
        key=lambda p: -len(p[0]),
    )
    for root in roots.values():
        for el in root.iter():
            if not isinstance(el.tag, str):
                continue
            for key, val in list(el.attrib.items()):
                new = val
                for old, repl in pairs:
                    if old in new:
                        new = new.replace(old, repl)
                # Metin taşıyan özniteliklerde (alternatif metin, köprü ipucu) bu değerlerin dışında da kişisel bilgi olabilir.
                if etree.QName(key).localname in _TEXT_ATTRS and len(new) >= 6:
                    for f in sorted(detect(new, rules), key=lambda f: -f.start):
                        new = new[: f.start] + _replacement(f, rules) + new[f.end :]
                if new != val:
                    el.set(key, new)


def _scrub_people_part(attrs: tuple[str, ...], data: bytes) -> bytes:
    root = parse(data)
    for el in root.iter():
        for a in attrs:
            if a in el.attrib:
                el.set(a, "")
    return _dump(root)


def _scrub_props(name: str, data: bytes) -> bytes:
    root = parse(data)
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname
        if name == "docProps/core.xml" and local not in ("coreProperties", "created", "modified"):
            el.text = ""
        elif name == "docProps/app.xml" and local in _APP_PERSONAL:
            el.text = ""
        elif name == "docProps/custom.xml" and len(el) == 0 and local != "Properties":
            el.text = ""
    return _dump(root)


def _is_thumbnail(name: str) -> bool:
    return name.startswith("docProps/thumbnail.")


def _drop_thumbnail_rels(data: bytes) -> bytes:
    """Kök ilişkilerden docProps/thumbnail.* hedefli ilişkiyi kaldırır."""
    root = parse(data)
    for rel in list(root):
        if _is_thumbnail(rel.get("Target", "").lstrip("/")):
            root.remove(rel)
    return _dump(root)


def _scrub_rels(data: bytes, rules: Rules) -> bytes:
    """Dış bağlantı hedeflerinde (mailto:, web adresi) bulgu varsa hedefi kaldırır."""
    root = parse(data)
    for rel in root:
        if rel.get("TargetMode") == "External" and detect(rel.get("Target", ""), rules):
            rel.set("Target", "#")
    return _dump(root)


# ---------------------------------------------------------------- aktif içerik (TAKIP 2.21)

# Maskeli kopyada bulunmaması gereken parçalar: makro, OLE/gömülü nesne, ActiveX, dış çalışma kitabı bağlantıları.
_AKTIF_PARCA = re.compile(
    r"(^|/)(vbaProject\.bin|vbaData\.xml|vbaProjectSignature\.bin|[^/]*\.vml|[^/]*\.wll)$|"
    r"/(embeddings|activeX|externalLinks|customUI|oleObjects)/|^(customUI)/",
    re.IGNORECASE,
)
# Bu ilişki türleri (son bölüm) bağlantı hedefi dış olsun ya da olmasın atılır; köprüler (hyperlink) kalır.
_AKTIF_ILISKI = (
    "vbaproject", "vbaprojectsignature", "oleobject", "package", "activexcontrol", "activexcontrolbinary",
    "externallink", "externallinkpath", "attachedtemplate", "subdocument", "frame", "customui", "extensibility",
    "ole", "control", "macrosheet", "dialogsheet", "vbadata",
)
# Makro etkin ana parça içerik türleri → makrosuz karşılığı.
_MAKROSUZ_TUR = {
    "application/vnd.ms-word.document.macroenabled.main+xml":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
    "application/vnd.ms-word.template.macroenabledtemplate.main+xml":
        "application/vnd.openxmlformats-officedocument.wordprocessingml.template.main+xml",
    "application/vnd.ms-excel.sheet.macroenabled.main+xml":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml",
    "application/vnd.ms-excel.template.macroenabled.main+xml":
        "application/vnd.openxmlformats-officedocument.spreadsheetml.template.main+xml",
    "application/vnd.ms-powerpoint.presentation.macroenabled.main+xml":
        "application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml",
    "application/vnd.ms-powerpoint.slideshow.macroenabled.main+xml":
        "application/vnd.openxmlformats-officedocument.presentationml.slideshow.main+xml",
}
# Gövdeden atılan öğeler (yerel adlarıyla): gömülü nesne, ActiveX denetimi, dış kitap başvurusu, ekli şablon,
# alanların otomatik güncellenmesi.
_AKTIF_OGE = frozenset(
    {"object", "OLEObject", "control", "oleObj", "oleObjects", "controls", "externalReferences", "attachedTemplate",
     "updateFields"}
)
_ALAN_RISKLI = re.compile(r"^\s*(DDE|DDEAUTO|LINK|INCLUDETEXT|INCLUDEPICTURE|IMPORT|AUTOTEXT)\b", re.IGNORECASE)
_AKTIF_XML = re.compile(
    r"^(word/[^/]+|xl/workbook|xl/worksheets/[^/]+|ppt/slides/[^/]+|ppt/presentation)\.xml$"
)


def _aktif_parca_mi(name: str) -> bool:
    return bool(_AKTIF_PARCA.search(name))


def _aktif_oge_temizle(root: etree._Element) -> bool:
    """Gövdeden gömülü nesne/ActiveX/dış başvuru öğelerini ve riskli alan kodlarını atar; değişirse True."""
    changed = False
    for el in list(root.iter()):
        if not isinstance(el.tag, str):
            continue
        local = etree.QName(el).localname
        if local in _AKTIF_OGE and el.getparent() is not None:
            _kaldir(el)
            changed = True
        elif local == "instrText" and el.text and _ALAN_RISKLI.match(el.text):
            el.text = ""
            changed = True
    return changed


def _kaldir(el: etree._Element) -> None:
    parent = el.getparent()
    tail = el.tail
    if tail:
        prev = el.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + tail
        else:
            parent.text = (parent.text or "") + tail
    parent.remove(el)


def _aktif_rels(data: bytes) -> bytes:
    """İlişkilerden makro, OLE, ActiveX, dış bağlantı ve şablon ilişkilerini atar; köprüler kalır."""
    root = parse(data)
    for rel in list(root):
        kind = rel.get("Type", "").rsplit("/", 1)[-1].lower()
        target = rel.get("Target", "")
        if kind in _AKTIF_ILISKI or (
            rel.get("TargetMode") != "External" and _aktif_parca_mi(target.lstrip("/").replace("../", ""))
        ):
            root.remove(rel)
    return _dump(root)


def _aktif_content_types(data: bytes, dropped: set[str]) -> bytes:
    root = parse(data)
    for el in list(root):
        part = el.get("PartName", "").lstrip("/")
        if part and (part in dropped or _aktif_parca_mi(part)):
            root.remove(el)
            continue
        ct = el.get("ContentType", "")
        if ct.lower() in _MAKROSUZ_TUR:
            el.set("ContentType", _MAKROSUZ_TUR[ct.lower()])
        elif "macroenabled" in ct.lower() or "vbaproject" in ct.lower():
            root.remove(el)
    return _dump(root)


def aktif_icerik_kaldi(data: bytes) -> list[str]:
    """Maskeli Office baytlarında hâlâ duran aktif içerik izlerini listeler (doğrulama; boş liste = temiz)."""
    kalan = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if _aktif_parca_mi(name):
                kalan.append(name)
            elif name.endswith(".rels"):
                for rel in parse(z.read(name)):
                    if rel.get("Type", "").rsplit("/", 1)[-1].lower() in _AKTIF_ILISKI:
                        kalan.append(f"{name}:{rel.get('Id')}")
            elif name == "[Content_Types].xml" and b"macroEnabled" in z.read(name):
                kalan.append(name)
    return kalan



def _manual_method(rules: Rules) -> str:
    method = rules.method_for("elle") if "elle" in rules.types else BLACKOUT
    return LABEL if method == LABEL else BLACKOUT


def line_replacement(text: str, method: str, rules: Rules) -> str:
    """Elle seçilen satır/sütundaki bir hücrenin yerine yazılacak metin."""
    if method == LABEL:
        return "[GIZLI]"
    if method == KEEP_LAST4:
        d = digits_only(text)
        return "**** " + d[-4:] if len(d) > 4 else "****"
    if method == INITIALS:
        return initials(text) if text.strip() else BLACKOUT_TEXT
    if method == PSEUDONYM:
        if rules.pseudonyms is None:
            raise PdfError("Takma ad için önce özel ifade kasasının kilidini açın")
        return rules.pseudonyms.label("elle", text) if text.strip() else BLACKOUT_TEXT
    return BLACKOUT_TEXT


def _cell_text(c: etree._Element, shared: list[str]) -> str:
    t, v = c.get("t"), c.find(S + "v")
    if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
        return shared[int(v.text)]
    if t == "inlineStr" and c.find(S + "is") is not None:
        return "".join(x.text or "" for x in c.find(S + "is").iter(S + "t"))
    return (v.text or "") if v is not None else ""


def _blank_unused_shared(roots: dict[str, etree._Element]) -> None:
    """Hiçbir hücrenin kullanmadığı paylaşılan metinleri boşaltır (silinen değer dosyada kalmasın)."""
    shared = roots.get("xl/sharedStrings.xml")
    if shared is None:
        return
    used: set[int] = set()
    for name, root in roots.items():
        if not name.startswith("xl/worksheets/"):
            continue
        for c in root.iter(S + "c"):
            v = c.find(S + "v")
            if c.get("t") == "s" and v is not None and (v.text or "").isdigit():
                used.add(int(v.text))
    for i, si in enumerate(shared.iter(S + "si")):
        if i in used:
            continue
        for t in si.iter(S + "t"):
            t.text = ""


def _set_inline_text(c: etree._Element, text: str) -> None:
    for child in list(c):
        c.remove(child)
    c.set("t", "inlineStr")
    t = etree.SubElement(etree.SubElement(c, S + "is"), S + "t")
    t.text = text
    t.set(XML_SPACE, "preserve")


def _apply_column_rules(
    z: zipfile.ZipFile, roots: dict[str, etree._Element], rules: Rules, stats: dict[str, int]
) -> int:
    """Başlığı bir sütun kuralıyla eşleşen sütunların dolu hücrelerini türün yöntemiyle değiştirir.

    Başlık, sayfadaki ilk dolu satırdır. Hücre içeriğe bakılmadan o türden sayılır; değer, formül ve
    satır içi metin kaldırılır. Sayılar `stats`'a tür bazında yazılır.
    """
    names = z.namelist()
    shared = (
        [unit_text(seg) for _u, seg in units(EXCEL, parse(z.read("xl/sharedStrings.xml")))]
        if "xl/sharedStrings.xml" in names
        else []
    )
    total = 0
    for _name, part in sheet_list(z):
        if part not in roots:
            continue
        # Özgün değerler zip'ten okunur; otomatik bulgular `roots`'u çoktan değiştirmiş olabilir.
        original = {oc.get("r") or "": _cell_text(oc, shared) for oc in parse(z.read(part)).iter(S + "c")}
        shared_now = (
            [unit_text(seg) for _u, seg in units(EXCEL, roots["xl/sharedStrings.xml"])]
            if "xl/sharedStrings.xml" in roots
            else shared
        )
        cells = []
        for c in roots[part].iter(S + "c"):
            m = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r") or "")
            if m:
                cells.append((int(m.group(2)), _col_index(m.group(1)), c, original.get(c.get("r") or "", "")))
        filled = [row for row, _col, _c, text in cells if text.strip()]
        if not filled:
            continue
        header_row = min(filled)
        kinds = {col: rules.column_type(text) for row, col, _c, text in cells if row == header_row}
        acts = {
            col: rules.column_action(text)
            for row, col, _c, text in cells
            if row == header_row and not kinds.get(col)
        }
        for row, col, c, text in cells:
            act = acts.get(col)
            if row != header_row and act in (tablo.ACTION_AGE, tablo.ACTION_DATE) and text.strip():
                numeric = False
                if act == tablo.ACTION_AGE:
                    new = tablo.top_code_age(text, rules.age_limit)
                else:
                    new = tablo.shift_date(text, rules.shift_days())
                    if new is None and c.get("t") in (None, "n") and c.find(S + "v") is not None:
                        new = tablo.shift_serial(text, rules.shift_days())  # Excel tarih seri numarası
                        numeric = new is not None
                if new is not None:
                    if numeric:  # sayı ve hücre biçimi kalır
                        c.find(S + "v").text = new
                        for f_el in c.findall(S + "f"):
                            c.remove(f_el)
                    else:
                        _set_inline_text(c, new)
                    stats["dogum_tarihi"] = stats.get("dogum_tarihi", 0) + 1
                    total += 1
                continue
            kind = kinds.get(col)
            if row == header_row or not kind:
                continue
            if c.find(S + "v") is None and c.find(S + "is") is None and c.find(S + "f") is None:
                continue  # boş (yalnızca biçimli) hücre
            # Otomatik bulgu hücreyi zaten değiştirdiyse o bulgu sayılmıştır; aynı hücre ikinci kez sayılmaz.
            counted = _cell_text(c, shared_now) != text
            f = Finding(kind, 0, len(text), text, "yuksek", "sütun")
            _set_inline_text(c, _replacement(f, rules))
            if not counted:
                stats[kind] = stats.get(kind, 0) + 1
            total += 1
    if total:
        _blank_unused_shared(roots)
    return total


def _table_k_warnings(z: zipfile.ZipFile, rules: Rules) -> list[str]:
    """Dolaylı sütun eylemi olan sayfalar için k-anonimlik uyarıları (özgün değerler üzerinden)."""
    names = z.namelist()
    shared = (
        [unit_text(seg) for _u, seg in units(EXCEL, parse(z.read("xl/sharedStrings.xml")))]
        if "xl/sharedStrings.xml" in names
        else []
    )
    out: list[str] = []
    for _name, part in sheet_list(z):
        grid: dict[int, dict[int, str]] = {}
        for c in parse(z.read(part)).iter(S + "c"):
            m = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r") or "")
            if m:
                grid.setdefault(int(m.group(2)), {})[_col_index(m.group(1))] = _cell_text(c, shared)
        filled = [r for r, row in grid.items() if any(v.strip() for v in row.values())]
        if len(filled) < 2:
            continue
        header_row = min(filled)
        heads = grid[header_row]
        quasi = sorted(
            col for col, h in heads.items() if rules.column_action(h) == tablo.ACTION_QUASI and not rules.column_type(h)
        )
        if not quasi:
            continue
        width = max(heads) + 1
        rows = [[grid[r].get(col, "") for col in range(width)] for r in sorted(filled) if r != header_row]
        w = tablo.k_anonymity_warning(rows, quasi, rules.k_threshold, [heads[c] for c in quasi])
        if w:
            out.append(w)
    return out


_REF = re.compile(
    r"(?<![\w.])(?:(?:'((?:[^']|'')+)'|([\w.]+))!)?"
    r"(\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?|\$?[A-Z]{1,3}:\$?[A-Z]{1,3}|\$?\d+:\$?\d+)(?![\w(])"
)


def _ref_bounds(ref: str) -> tuple[int | None, int | None, int | None, int | None]:
    """Başvurunun (ilk sütun, son sütun, ilk satır, son satır) sınırları; belirtilmeyen None."""
    cols: list[int] = []
    rows: list[int] = []
    for p in ref.replace("$", "").split(":"):
        m = re.fullmatch(r"([A-Z]*)(\d*)", p)
        if m and m.group(1):
            cols.append(_col_index(m.group(1)))
        if m and m.group(2):
            rows.append(int(m.group(2)))
    return (
        min(cols) if cols else None,
        max(cols) if cols else None,
        min(rows) if rows else None,
        max(rows) if rows else None,
    )


def _dependent_formulas(
    z: zipfile.ZipFile,
    wanted: dict[str, tuple[dict[int, str], dict[int, str]]],
    names: dict[str, str],
) -> list[str]:
    """Seçilen satır/sütunlara başvuran ama kendisi silinmeyen formül hücrelerinin adresleri ("Sayfa!D3").

    Bu hücrelerin önbellekteki son değerleri seçilen verinin türevi olabilir. Yalnızca ilk formül
    metinleri taranır (paylaşılan formülün devam hücreleri ve adlandırılmış aralıklar kapsanmaz).
    """
    out: list[str] = []
    for part, sheet in names.items():
        for c in parse(z.read(part)).iter(S + "c"):
            f = c.find(S + "f")
            addr = c.get("r") or ""
            m = re.fullmatch(r"([A-Z]+)(\d+)", addr)
            if f is None or not f.text or not m:
                continue
            own_rows, own_cols = wanted.get(part, ({}, {}))
            if int(m.group(2)) in own_rows or _col_index(m.group(1)) in own_cols:
                continue  # hücre zaten siliniyor
            text = re.sub(r'"(?:[^"]|"")*"', '""', f.text)
            for r in _REF.finditer(text):
                target = (r.group(1) or r.group(2) or "").replace("''", "'")
                tpart = next((p for p, n in names.items() if n == target), None) if target else part
                if tpart not in wanted:
                    continue
                c1, c2, r1, r2 = _ref_bounds(r.group(3))
                rows, cols = wanted[tpart]
                row_hit = any((r1 is None or r1 <= x) and (r2 is None or x <= r2) for x in rows)
                col_hit = any((c1 is None or c1 <= x) and (c2 is None or x <= c2) for x in cols)
                if (r1 is not None and row_hit) or (c1 is not None and col_hit):
                    out.append(f"{sheet}!{addr}")
                    break
    return out


def _clear_cells(
    z: zipfile.ZipFile,
    roots: dict[str, etree._Element],
    selections: list[CellSelection],
    rules: Rules,
    dependents: list[str] | None = None,
) -> int:
    """Seçilen satır/sütunlardaki hücreleri, yönteme göre yazılan metinle satır içi hücreye çevirir.

    Değer, formül ve satır içi metin kaldırılır (maskeleme gerçek silmedir). Ardından hiçbir hücrenin
    kullanmadığı paylaşılan metinler boşaltılır; yoksa silinen değer `sharedStrings.xml`'de kalırdı.
    Bir hücre hem satır hem sütun seçimindeyse daha sıkı yöntem uygulanır
    (karartma > etiket > takma ad > baş harfler > son 4 hane).
    """
    by_name = {name: part for name, part in sheet_list(z)}
    default = _manual_method(rules)
    wanted: dict[str, tuple[dict[int, str], dict[int, str]]] = {}
    for sel in selections:
        sheet, axis, index = sel[0], sel[1], sel[2]
        method = sel[3] if len(sel) > 3 and sel[3] else default
        if method not in LINE_METHODS:
            raise PdfError(f"Satır/sütun için geçersiz yöntem: {method}")
        part = by_name.get(sheet)
        if part is None or part not in roots:
            raise PdfError(f"Excel sayfası bulunamadı: {sheet}")
        rows, cols = wanted.setdefault(part, ({}, {}))
        if axis == "row" and isinstance(index, int) and index >= 1:
            rows[index] = method
        elif axis == "col" and isinstance(index, int) and index >= 0:
            cols[index] = method
        else:
            raise PdfError("Satır ya da sütun seçimi geçersiz")

    if dependents is not None:
        dependents.extend(_dependent_formulas(z, wanted, {part: name for name, part in by_name.items()}))

    # Yöntem (son 4 hane, baş harfler, takma ad) hücrenin özgün değerine uygulanır; `roots` otomatik
    # bulgularla çoktan değişmiş olabilir, bu yüzden değerler zip'teki özgün parçalardan okunur.
    names = z.namelist()
    shared = (
        [unit_text(seg) for _u, seg in units(EXCEL, parse(z.read("xl/sharedStrings.xml")))]
        if "xl/sharedStrings.xml" in names
        else []
    )
    original: dict[tuple[str, str], str] = {}
    for part in wanted:
        for oc in parse(z.read(part)).iter(S + "c"):
            original[(part, oc.get("r") or "")] = _cell_text(oc, shared)
    strict = {m: i for i, m in enumerate((BLACKOUT, LABEL, PSEUDONYM, INITIALS, KEEP_LAST4))}
    cleared = 0
    for part, (rows, cols) in wanted.items():
        for c in list(roots[part].iter(S + "c")):
            m = re.fullmatch(r"([A-Z]+)(\d+)", c.get("r") or "")
            if not m:
                continue
            hit = [x for x in (rows.get(int(m.group(2))), cols.get(_col_index(m.group(1)))) if x]
            if not hit:
                continue
            if c.find(S + "v") is None and c.find(S + "is") is None and c.find(S + "f") is None:
                continue  # boş (yalnızca biçimli) hücre
            method = min(hit, key=lambda x: strict[x])
            text = line_replacement(original.get((part, c.get("r") or ""), ""), method, rules)
            for child in list(c):
                c.remove(child)
            c.set("t", "inlineStr")
            is_ = etree.SubElement(c, S + "is")
            t = etree.SubElement(is_, S + "t")
            t.text = text
            t.set(XML_SPACE, "preserve")
            cleared += 1

    if cleared:
        _blank_unused_shared(roots)
    return cleared


def _dump(root: etree._Element) -> bytes:
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)


# Elle seçilen Excel satırı ya da sütunu: (sayfa adı, "row" | "col", sıra[, yöntem]). Satır 1'den,
# sütun 0'dan (A=0). Yöntem verilmezse kural takımındaki "Elle seçilen alan" yöntemi kullanılır.
CellSelection = tuple  # (str, str, int) ya da (str, str, int, str)

# Satır/sütun seçiminde kullanılabilen yöntemler (hücrenin ne tür bilgi taşıdığı bilinmez).
LINE_METHODS = (BLACKOUT, LABEL, KEEP_LAST4, INITIALS, PSEUDONYM)


def mask_bytes(
    source: str | os.PathLike,
    fmt: OfficeFormat,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    manual_cells: list[CellSelection] | None = None,
    stats: dict[str, int] | None = None,
) -> tuple[bytes, list[str], list[OfficeFinding], list[OfficeFinding]]:
    """Maskeli belgeyi bellekte üretir: (veri, uyarılar, dahil edilenler, tüm bulgular).

    `manual_cells` (yalnızca Excel): bu satır ve sütunlardaki dolu hücrelerin tamamı silinir.
    `stats` verilirse elle silinen hücre sayısı "elle" anahtarına yazılır.
    """
    excluded_ids = excluded_ids or set()
    if manual_cells and fmt is not EXCEL:
        raise PdfError("Satır ve sütun seçimi yalnızca Excel için")
    with open_zip(Path(source), fmt) as z:
        roots, findings, removed = load(z, fmt, rules)
        warnings = warnings_for(z, fmt, roots, removed)
        included = [f for f in findings if f.id not in excluded_ids]
        _apply(fmt, roots, included)
        if (rules.column_rules or rules.column_actions) and fmt is EXCEL:
            if stats is None:
                stats = {}
            warnings.extend(_table_k_warnings(z, rules))
            if _apply_column_rules(z, roots, rules, stats):
                warnings.append(
                    "Başlığa göre sütun kuralı uygulanan hücreler silindi. Bu hücrelere başvuran formüllerin "
                    "son hesaplanan değerleri başka hücrelerde kalabilir."
                )
        if manual_cells:
            dependents: list[str] = []
            cleared = _clear_cells(z, roots, manual_cells, rules, dependents)
            if stats is not None:
                stats["elle"] = stats.get("elle", 0) + cleared
            if cleared:
                warnings.append(
                    f"Seçilen satır ve sütunlarda {cleared} hücre silindi. Bu hücrelere başvuran formüllerin "
                    "son hesaplanan değerleri başka hücrelerde kalabilir; gerekirse o hücreleri de seçin."
                )
            if dependents:
                shown = ", ".join(dependents[:10]) + (f" ve {len(dependents) - 10} hücre daha" if len(dependents) > 10 else "")
                warnings.append(
                    f"{len(dependents)} formül hücresi silinen alana başvuruyor ({shown}). Önbellekteki son "
                    "değerleri seçilen verinin türevi olabilir; bu hücreleri de seçin ya da dosyayı açıp kontrol edin."
                )
        for root in roots.values():
            _scrub_people(fmt, root)
        _sweep_attributes(roots, included, rules)
        for root in roots.values():
            _aktif_oge_temizle(root)
        dropped = {n for n in z.namelist() if _aktif_parca_mi(n)}
        if dropped:
            warnings.append(
                f"Belgedeki {len(dropped)} aktif içerik parçası (makro, gömülü nesne, ActiveX, dış kitap bağlantısı) "
                "maskeli kopyadan silindi."
            )

        media: dict[str, bytes] = {}
        media_masked = media_failed = media_scanned = 0
        for name in z.namelist():
            if not _is_scannable_media(name):
                continue
            data, n, ok = _mask_media(z.read(name), Path(name).suffix.lower(), rules)
            if not ok:
                media_failed += 1
                continue
            media_scanned += 1
            if n:
                media[name] = data
                media_masked += n
        if media_masked and stats is not None:
            stats["görsel"] = stats.get("görsel", 0) + media_masked
        warnings += _media_warnings(media_scanned, media_masked, media_failed)

        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
            for info in z.infolist():
                name = info.filename
                if name in dropped:
                    continue  # makro, OLE/gömülü nesne, ActiveX, dış bağlantı parçaları atılır (TAKIP 2.21)
                if _is_thumbnail(name):
                    continue  # önizleme görseli özgün sayfayı gösterir; atılır, ilişkisi aşağıda silinir (TAKIP 1.57)
                if name == "_rels/.rels":
                    data = _aktif_rels(_scrub_rels(_drop_thumbnail_rels(z.read(name)), rules))
                elif name == "[Content_Types].xml":
                    data = _aktif_content_types(z.read(name), dropped)
                elif name in roots:
                    data = _dump(roots[name])
                elif name in media:
                    data = media[name]
                elif name in _PROPS_PARTS:
                    data = _scrub_props(name, z.read(name))
                elif name in fmt.people_parts:
                    data = _scrub_people_part(fmt.people_parts[name], z.read(name))
                elif name.endswith(".rels"):
                    data = _aktif_rels(_scrub_rels(z.read(name), rules))
                elif _AKTIF_XML.match(name):
                    root = parse(z.read(name))
                    data = _dump(root) if _aktif_oge_temizle(root) else z.read(name)
                else:
                    data = z.read(name)
                # Sabit zaman damgası; orijinal ZIP'in ek alanları (kişisel olabilir) taşınmaz.
                new = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                new.compress_type = zipfile.ZIP_DEFLATED
                dst.writestr(new, data)
    return out.getvalue(), warnings, included, findings


def mask(
    source: str | os.PathLike,
    target: str | os.PathLike,
    fmt: OfficeFormat,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    make_dirs: bool = False,
    counts: dict[str, int] | None = None,
    manual_cells: list[CellSelection] | None = None,
) -> tuple[str, int, list[str]]:
    """Maskeli kopyayı yazar; (hedef yol, maskelenen sayısı, uyarılar) döner.

    `counts`: verilirse maskelenenler tür bazında buraya sayılır.
    """
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

    stats: dict[str, int] = {}
    data, warnings, included, findings = mask_bytes(src, fmt, rules, excluded_ids, manual_cells, stats)
    verify(data, included, findings)

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
        for key, n in stats.items():
            counts[key] = counts.get(key, 0) + n
    return str(dst), len(included) + sum(stats.values()), warnings


def all_text(data: bytes) -> str:
    """Arşivdeki tüm XML parçalarının metni ve öznitelik değerleri (kaçak denetimi için)."""
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if not name.endswith((".xml", ".rels", ".vml")):
                continue
            try:
                root = parse(z.read(name))
            except PdfError:
                # Ayrıştırılamayan parça: ham metni denetle (gizli değer kaçmasın).
                parts.append(z.read(name).decode("utf-8", "replace"))
                continue
            for el in root.iter():
                if isinstance(el.tag, str) and el.text:
                    parts.append(el.text)
                parts.extend(el.attrib.values())
                parts.append("\n")
    return "".join(parts)


def verify(data: bytes, included: list[OfficeFinding], findings: list[OfficeFinding]) -> None:
    text = _normalize(all_text(data))
    included_ids = {f.id for f in included}
    kept = {_normalize(f.finding.value) for f in findings if f.id not in included_ids}
    must_be_gone = {
        _normalize(f.finding.value)
        for f in included
        if _normalize(f.finding.value) not in _normalize(f.replacement)
        and f.finding.source != SPLIT_NOTE  # kısa parçalar başka yerlerde rastlantıyla geçer
    } - kept
    kalan = aktif_icerik_kaldi(data)
    if kalan:
        raise PdfError(f"Aktif içerik kaldı ({', '.join(kalan[:3])}). Dosya yazılmadı.")
    leaked = sum(1 for v in must_be_gone if v and v in text)
    if leaked:
        raise PdfError(
            f"Kaçak tespiti: maskelenmesi gereken {leaked} değer belgenin başka bir yerinde "
            "(gizli alan, bağlantı, formül, özellik) hâlâ okunuyor. Dosya yazılmadı."
        )


# ---------------------------------------------------------------- önizleme yardımcıları


def _rels(z: zipfile.ZipFile, part: str) -> dict[str, str]:
    """Bir parçanın ilişkileri: rId → hedef parça yolu."""
    folder, name = part.rsplit("/", 1)
    rels_name = f"{folder}/_rels/{name}.rels"
    if rels_name not in z.namelist():
        return {}
    out = {}
    for rel in parse(z.read(rels_name)):
        target = rel.get("Target", "")
        if rel.get("TargetMode") == "External":
            continue
        path = target.lstrip("/") if target.startswith("/") else _join(folder, target)
        out[rel.get("Id")] = path
    return out


def _join(folder: str, target: str) -> str:
    parts = folder.split("/") + target.split("/")
    out: list[str] = []
    for p in parts:
        if p == "..":
            if out:
                out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"


def slide_order(z: zipfile.ZipFile) -> list[str]:
    """Sunumdaki slaytların gösterim sırası (dosya adı sırası değil)."""
    pres = parse(z.read("ppt/presentation.xml"))
    rels = _rels(z, "ppt/presentation.xml")
    return [rels[s.get(R + "id")] for s in pres.iter(P + "sldId") if s.get(R + "id") in rels]


def sheet_list(z: zipfile.ZipFile) -> list[tuple[str, str]]:
    """Excel sayfaları: (sayfa adı, parça yolu) çalışma kitabındaki sırayla."""
    wb = parse(z.read("xl/workbook.xml"))
    rels = _rels(z, "xl/workbook.xml")
    return [(s.get("name", ""), rels[s.get(R + "id")]) for s in wb.iter(S + "sheet") if s.get(R + "id") in rels]



def _col_index(ref: str) -> int:
    n = 0
    for ch in re.match(r"[A-Z]+", ref).group():
        n = n * 26 + ord(ch) - 64
    return n - 1


def sheet_preview(path: str | os.PathLike, max_rows: int = 300, max_cols: int = 40) -> list[dict]:
    """Excel sayfalarının önizleme ızgarası.

    Her hücre: görünen metin ve "birim" anahtarı ("parça:sıra"). Bulgular aynı anahtarla
    gelir; arayüz hücredeki değeri bu anahtar ve karakter aralığıyla işaretler. Paylaşılan
    metin birden çok hücrede kullanılıyorsa hepsi aynı birimi gösterir (birlikte maskelenir).
    """
    with open_zip(Path(path), EXCEL) as z:
        shared: list[tuple[str, str]] = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = parse(z.read("xl/sharedStrings.xml"))
            for ui, (_el, segments) in enumerate(units(EXCEL, root)):
                shared.append((unit_text(segments), f"xl/sharedStrings.xml:{ui}"))
        out = []
        for name, part in sheet_list(z):
            if part not in z.namelist():
                continue
            root = parse(z.read(part))
            # Liste canlı kalmalı: lxml öğe nesneleri ancak bir başvuru varken aynı kalır.
            sheet_units = units(EXCEL, root)
            index = {el: ui for ui, (el, _s) in enumerate(sheet_units)}
            rows: dict[int, dict[int, dict]] = {}
            max_c = 0
            for c in root.iter(S + "c"):
                ref = c.get("r") or ""
                m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
                if not m:
                    continue
                r, col = int(m.group(2)), _col_index(ref)
                if r > max_rows or col >= max_cols:
                    continue
                t = c.get("t")
                v = c.find(S + "v")
                cell = {"text": "", "unit": None}
                if t == "s" and v is not None and (v.text or "").isdigit() and int(v.text) < len(shared):
                    cell["text"], cell["unit"] = shared[int(v.text)]
                elif t == "inlineStr" and c.find(S + "is") is not None:
                    is_ = c.find(S + "is")
                    cell["text"] = "".join(x.text or "" for x in is_.iter(S + "t"))
                    cell["unit"] = f"{part}:{index[is_]}" if is_ in index else None
                elif t == "b" and v is not None:
                    cell["text"] = "DOĞRU" if v.text == "1" else "YANLIŞ"
                elif v is not None:
                    cell["text"] = v.text or ""
                    if v in index:
                        cell["unit"] = f"{part}:{index[v]}"
                rows.setdefault(r, {})[col] = cell
                max_c = max(max_c, col + 1)
            grid = []
            for r in sorted(rows):
                grid.append({"row": r, "cells": [rows[r].get(ci, {"text": "", "unit": None}) for ci in range(max_c)]})
            out.append({"name": name, "cols": max_c, "rows": grid})
    return out
