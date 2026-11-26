"""Metin tabanlı belgeler: XML (e-Fatura, e-Arşiv, UBL), CSV ve düz metin türleri (TXT, LOG, MD, JSON, TSV, INI, YAML).

Dosya olduğu gibi okunur ve yalnızca içerik bölümleri taranır; biçim, girinti
ve satır sonları korunur. XML'de içerik bölümü; etiketler arasındaki metin,
öznitelik değerleri, CDATA ve yorumlardır. Etiket ve öznitelik adları
değişmez, böylece belge geçerli XML olarak kalır.

Güvenlik:
- DOCTYPE içeren XML reddedilir (dış varlık/XXE ve "billion laughs" riskleri,
  ayrıca varlıklar içinde gizlenmiş veri taranamaz).
- e-Fatura'daki gömülü dosyalar (base64 PDF, XSLT) taranamaz; kişisel veri
  taşıyabilecekleri için maskeli kopyada içerikleri silinir.
- Çıktı yeniden okunur; XML bozulmuşsa ya da işaretli bir değer hâlâ
  okunuyorsa dosya yazılmaz.
"""

from __future__ import annotations

import os
import re
import tempfile
from lxml import etree as ET
from dataclasses import dataclass, field
from html import escape
from pathlib import Path

from .detect import HIGH, MEDIUM, Finding, detect
from .loose import find_split_cells
from .names import name_hints
from .pdf import PdfError, _normalize, count_types, unique_path
from .rules import BLACKOUT, BLUR, Rules, kacak_iletisi, kacak_kabul
from .xmltok import iter_tokens

# xml ve csv kendi kurallarıyla; geri kalanı düz metin gibi taranır ve maskelenir (biçim işareti taşımayan türler).
TEXT_EXTS = {".xml", ".txt", ".csv", ".log", ".md", ".json", ".tsv", ".ini", ".yaml", ".yml"}
MAX_BYTES = 20 * 1024 * 1024

_BLACKOUT_TEXT = "█████"
_BLACKOUT_FALLBACK = "*****"  # █ yazılamayan kodlamalarda (ör. Windows-1254)

# Etiket: öznitelik değerleri ">" içerebileceği için tırnaklar ayrıca ele alınır. Yorum, CDATA ve işleme
# talimatı `xmltok.iter_tokens` ile doğrusal taranır (kapanmayan açıcı ikinci dereceden sürüyordu, F9/F20).
_TOKEN = re.compile(
    r"<!--(?P<comment>.*?)-->"
    r"|<!\[CDATA\[(?P<cdata>.*?)\]\]>"
    r"|<\?.*?\?>"
    r"|(?P<tag><[A-Za-z_:/][^<>\"']*(?:(?:\"[^\"]*\"|'[^']*')[^<>\"']*)*>)",
    re.DOTALL,
)
_ATTR_VALUE = re.compile(r"(?P<name>[A-Za-z_][\w.:-]*)\s*=\s*(?:\"(?P<dq>[^\"]*)\"|'(?P<sq>[^']*)')")
_DOCTYPE = re.compile(r"<!DOCTYPE", re.IGNORECASE)
_XML_ENCODING = re.compile(rb"^\s*<\?xml[^>]*encoding\s*=\s*[\"']([A-Za-z0-9._-]+)[\"']")
_CHAR_REF = re.compile(r"&#[0-9xX]")
# Gömülü dosya: uzun, yalnızca base64 karakterlerinden oluşan metin. Sınıf boşluğu da içerdiği için baştaki
# ve sondaki `\s*` gereksizdi ve tam eşleşme başarısız olunca kübik geri izliyordu (F19); dil aynı.
_BASE64 = re.compile(r"[A-Za-z0-9+/=\s]{1000,}")


@dataclass
class TextFinding:
    id: str
    finding: Finding
    replacement: str


@dataclass
class TextScan:
    text: str
    fmt: str  # "xml" | "txt" | "csv"
    encoding: str
    findings: list[TextFinding]
    warnings: list[str] = field(default_factory=list)
    embedded: list[tuple[int, int]] = field(default_factory=list)  # silinecek gömülü dosyalar


def is_text_doc(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in TEXT_EXTS


def _read(path: Path) -> tuple[str, str, bytes]:
    """Metin, kodlama ve (varsa) BOM."""
    if not path.is_file():
        raise PdfError("Dosya bulunamadı")
    raw = path.read_bytes()
    if len(raw) > MAX_BYTES:
        raise PdfError(f"Dosya çok büyük; en fazla {MAX_BYTES // (1024 * 1024)} MB")
    for bom, enc in ((b"\xef\xbb\xbf", "utf-8"), (b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
        if raw.startswith(bom):
            return _decode(raw[len(bom):], enc), enc, bom
    candidates = ["utf-8", "cp1254"]  # Türkçe Windows dosyaları çoğunlukla 1254'tür
    m = _XML_ENCODING.match(raw)
    if m:
        candidates.insert(0, m.group(1).decode("ascii").lower())
    for enc in candidates:
        try:
            return raw.decode(enc), enc, b""
        except (UnicodeDecodeError, LookupError):
            continue
    raise PdfError("Dosyanın karakter kodlaması tanınamadı")


def _decode(raw: bytes, enc: str) -> str:
    try:
        return raw.decode(enc)
    except UnicodeDecodeError:
        raise PdfError("Dosyanın karakter kodlaması bozuk") from None


def _content_spans(text: str, fmt: str) -> list[tuple[int, int]]:
    """Taranacak bölümler (başlangıç, bitiş)."""
    if fmt != "xml":
        return [(0, len(text))]
    spans: list[tuple[int, int]] = []
    pos = 0
    for m in iter_tokens(_TOKEN, text):
        if m.start() > pos:
            spans.append((pos, m.start()))  # etiketler arasındaki metin
        if m.group("comment") is not None:
            spans.append(m.span("comment"))
        elif m.group("cdata") is not None:
            spans.append(m.span("cdata"))
        elif m.group("tag") is not None:
            base = m.start()
            for a in _ATTR_VALUE.finditer(m.group("tag")):
                if a.group("name") == "xmlns" or a.group("name").startswith("xmlns:"):
                    continue  # ad alanı bildirimi veri değildir; değişirse XML'in anlamı bozulur
                group = "dq" if a.group("dq") is not None else "sq"
                s, e = a.span(group)
                spans.append((base + s, base + e))
        pos = m.end()
    if pos < len(text):
        spans.append((pos, len(text)))
    return [(s, e) for s, e in spans if text[s:e].strip()]


def _csv_cells(text: str) -> list[tuple[int, int, int, int]]:
    """CSV hücreleri: (satır, sütun, içerik başı, içerik sonu); tırnaklı hücrede tırnak içi alınır.

    Ayraç ilk satırdan seçilir (, ; sekme |). Satır bölünmesi tırnağa duyarlıdır.
    """
    delim = max(",;\t|", key=text.split("\n", 1)[0].count)
    cells: list[tuple[int, int, int, int]] = []
    row = col = i = 0
    n = len(text)
    while True:
        start = i
        if i < n and text[i] == '"':
            j = i + 1
            while j < n and not (text[j] == '"' and text[j + 1:j + 2] != '"'):
                j += 2 if text[j] == '"' else 1
            cells.append((row, col, start + 1, min(j, n)))
            i = j + 1
            while i < n and text[i] not in (delim, "\n"):
                i += 1  # kapanış tırnağından sonraki artık karakterler
        else:
            while i < n and text[i] not in (delim, "\n"):
                i += 1
            end = i - 1 if i > start and text[i - 1] == "\r" and i < n and text[i] == "\n" else i
            cells.append((row, col, start, end))
        if i >= n:
            return cells
        if text[i] == delim:
            col += 1
        else:
            row, col = row + 1, 0
        i += 1


def _split_cell_findings(text: str, rules: Rules, encoding: str, existing: list["TextFinding"]) -> list["TextFinding"]:
    """Yan yana CSV hücrelerine bölünmüş TC/IBAN/telefon; her parça hücre kendi bulgusu olur."""
    rows: dict[int, list[tuple[int, int, int]]] = {}
    for r, c, s, e in _csv_cells(text):
        rows.setdefault(r, []).append((c, s, e))
    out: list[TextFinding] = []
    for cells in rows.values():
        run: list[tuple[int, int, int]] = []
        runs = []
        for cell in cells:
            if run and cell[0] != run[-1][0] + 1:
                runs.append(run)
                run = []
            run.append(cell)
        runs.append(run)
        for run in runs:
            if len(run) < 2:
                continue
            for kind, i, j, _conf in find_split_cells([text[s:e] for _c, s, e in run]):
                if not rules.types[kind].enabled:
                    continue
                for _c, s, e in run[i : j + 1]:
                    if any(f.finding.start < e and s < f.finding.end for f in existing + out):
                        continue
                    f = Finding(kind, s, e, text[s:e], MEDIUM, "hücreler arası bölünmüş değer")
                    out.append(TextFinding(f"t:{s}:{e}", f, _text_replacement(f, rules, "csv", encoding)))
    return out


def _column_findings(text: str, rules: Rules, encoding: str) -> list[TextFinding]:
    """Başlığı bir sütun kuralıyla eşleşen sütunların dolu hücreleri, içeriğe bakılmadan o türden bulgu olur."""
    cells = _csv_cells(text)
    kinds = {c: rules.column_type(text[s:e].replace('""', '"')) for r, c, s, e in cells if r == 0}
    out: list[TextFinding] = []
    for r, c, s, e in cells:
        kind = kinds.get(c)
        if r == 0 or not kind or not text[s:e].strip():
            continue
        f = Finding(kind, s, e, text[s:e], HIGH, "sütun")
        out.append(TextFinding(f"t:{s}:{e}", f, _text_replacement(f, rules, "csv", encoding)))
    return out


def _table_actions(text: str, rules: Rules, encoding: str) -> tuple[list[TextFinding], str | None]:
    """Yaş üstten kodlama ve tarih kaydırma bulguları ile k-anonimlik uyarısı (başlığa göre eylemler).

    Tür kuralı olan sütunda eylem uygulanmaz. Bulgu türü "dogum_tarihi"dir (kaynak "sütun-yas" /
    "sütun-tarih"); yerine yazılan metin burada hesaplanır.
    """
    from . import tablo

    cells = _csv_cells(text)
    heads = {c: text[s:e].replace('""', '"') for r, c, s, e in cells if r == 0}
    acts = {c: rules.column_action(h) for c, h in heads.items() if not rules.column_type(h)}
    out: list[TextFinding] = []
    for r, c, s, e in cells:
        act = acts.get(c)
        value = text[s:e]
        if r == 0 or act not in (tablo.ACTION_AGE, tablo.ACTION_DATE) or not value.strip():
            continue
        if act == tablo.ACTION_AGE:
            new = tablo.top_code_age(value, rules.age_limit)
        else:
            new = tablo.shift_date(value, rules.shift_days())
        if new is None:
            continue
        f = Finding("dogum_tarihi", s, e, value, HIGH, "sütun-" + act)
        out.append(TextFinding(f"t:{s}:{e}", f, new))
    quasi = [c for c, a in acts.items() if a == tablo.ACTION_QUASI]
    warning = None
    if quasi:
        body: dict[int, dict[int, str]] = {}
        for r, c, s, e in cells:
            if r:
                body.setdefault(r, {})[c] = text[s:e]
        width = max(heads) + 1
        rows = [[row.get(c, "") for c in range(width)] for row in body.values() if any(v.strip() for v in row.values())]
        warning = tablo.k_anonymity_warning(rows, sorted(quasi), rules.k_threshold, [heads[c] for c in sorted(quasi)])
    return out, warning


def _text_replacement(f: Finding, rules: Rules, fmt: str, encoding: str) -> str:
    method = rules.method_for(f.type, f.source)
    if method in (BLACKOUT, BLUR):
        # Metinde bulanıklık olmaz; ikisi de sabit uzunlukta karartmadır (uzunluk sızmasın).
        out = _BLACKOUT_TEXT
        try:
            out.encode(encoding)
        except UnicodeEncodeError:
            out = _BLACKOUT_FALLBACK
    else:
        out = rules.replacement_for(f, ascii_only=False)
    return escape(out, quote=True) if fmt == "xml" else out


def _scan_text(text: str, fmt: str, encoding: str, rules: Rules) -> TextScan:
    if fmt == "xml" and _DOCTYPE.search(text):
        raise PdfError("DOCTYPE içeren XML güvenlik nedeniyle desteklenmiyor")
    findings: list[TextFinding] = []
    embedded: list[tuple[int, int]] = []
    spans = _content_spans(text, fmt)
    hints = (
        name_hints([text[a:b] for a, b in spans if not (fmt == "xml" and _BASE64.fullmatch(text[a:b]))])
        if rules.types["kisi_adi"].enabled
        else frozenset()
    )
    if fmt == "xml":
        from .efatura import is_ubl_xml, scan_ubl_xml

        if is_ubl_xml(text):
            raw_findings, embedded = scan_ubl_xml(text, rules, hints, lead=True)
            for moved in raw_findings:
                findings.append(
                    TextFinding(
                        id=f"t:{moved.start}:{moved.end}",
                        finding=moved,
                        replacement=_text_replacement(moved, rules, fmt, encoding),
                    )
                )
            spans = []  # UBL tarandı; aşağıdaki döngü çalışmaz.
    first = True
    for start, end in spans:
        segment = text[start:end]
        if fmt == "xml" and _BASE64.fullmatch(segment):
            embedded.append((start, end))
            continue
        lead, first = first, False
        for f in detect(segment, rules, hints, lead=lead):
            moved = Finding(f.type, f.start + start, f.end + start, f.value, f.confidence, f.source)
            findings.append(
                TextFinding(
                    id=f"t:{moved.start}:{moved.end}",
                    finding=moved,
                    replacement=_text_replacement(moved, rules, fmt, encoding),
                )
            )
    if fmt == "csv":
        findings = sorted(findings + _split_cell_findings(text, rules, encoding, findings), key=lambda f: f.finding.start)
    if fmt == "csv" and rules.column_rules:
        columns = _column_findings(text, rules, encoding)
        if columns:
            # Sütun kuralı hücrenin tamamını kapsar; hücre içinde bulunan parçalar ona karışır.
            def inside(f: TextFinding) -> bool:
                return any(c.finding.start <= f.finding.start and f.finding.end <= c.finding.end for c in columns)

            findings = sorted([f for f in findings if not inside(f)] + columns, key=lambda f: f.finding.start)
    warnings = []
    if fmt == "csv" and rules.column_actions:
        actions, k_warning = _table_actions(text, rules, encoding)
        if actions:
            def inside_action(f: TextFinding) -> bool:
                return any(a.finding.start <= f.finding.start and f.finding.end <= a.finding.end for a in actions)

            findings = sorted([f for f in findings if not inside_action(f)] + actions, key=lambda f: f.finding.start)
        if k_warning:
            warnings.append(k_warning)
    if embedded:
        warnings.append(
            f"Belgede {len(embedded)} gömülü dosya var (ör. e-Fatura PDF görünümü). "
            "İçerikleri taranamaz; maskeli kopyada silinir."
        )
    if fmt == "xml" and _CHAR_REF.search(text):
        warnings.append("XML'de karakter referansı (&#…;) ile yazılmış bölümler var; bunlar taranamaz, elle kontrol edin.")
    return TextScan(text, fmt, encoding, findings, warnings, embedded)


def scan_text_doc(path: str | os.PathLike, rules: Rules) -> TextScan:
    p = Path(path)
    text, encoding, _bom = _read(p)
    return _scan_text(text, p.suffix.lower().lstrip("."), encoding, rules)


def mask_text_doc(
    source: str | os.PathLike,
    target: str | os.PathLike,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    make_dirs: bool = False,
    counts: dict[str, int] | None = None,
) -> tuple[str, int, list[str]]:
    """Maskeli kopyayı yazar; (hedef yol, maskelenen sayısı, uyarılar) döner.

    `counts`: verilirse maskelenenler tür bazında buraya sayılır.
    """
    excluded_ids = excluded_ids or set()
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

    text, encoding, bom = _read(src)
    scan = _scan_text(text, src.suffix.lower().lstrip("."), encoding, rules)
    included = [f for f in scan.findings if f.id not in excluded_ids]

    edits = [(f.finding.start, f.finding.end, f.replacement) for f in included]
    edits += [(s, e, "") for s, e in scan.embedded]
    out = text
    for start, end, new in sorted(edits, reverse=True):
        out = out[:start] + new + out[end:]

    _verify(out, scan, included)

    tmp_fd, tmp_name = tempfile.mkstemp(suffix=dst.suffix, dir=dst.parent)
    try:
        with os.fdopen(tmp_fd, "wb") as fh:
            fh.write(bom + out.encode(encoding))
        os.replace(tmp_name, dst)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise
    if counts is not None:
        count_types(counts, (f.finding.type for f in included))
    return str(dst), len(included), scan.warnings


def _verify(out: str, scan: TextScan, included: list[TextFinding]) -> None:
    """Çıktı bozuksa ya da işaretli bir değer hâlâ okunuyorsa durdurur."""
    readable = out
    if scan.fmt == "xml":
        try:
            # Güvenli ayrıştırıcı (XXE/varlık patlaması yok): dış varlık, ağ ve DTD yüklenmez.
            # DTD içindeki değerler çözülmez ama ham metin (readable) zaten aşağıda denetlenir.
            parser = ET.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, huge_tree=False)
            root = ET.fromstring(_as_utf8(out), parser)
        except ET.XMLSyntaxError:
            raise PdfError("Maskeleme XML yapısını bozacaktı; dosya yazılmadı") from None
        # Varlıklar (&amp; gibi) çözülmüş hâliyle de kontrol et.
        parts = [t for t in root.itertext() if isinstance(t, str)]
        parts += [v for el in root.iter() for v in el.attrib.values()]
        readable += "".join(parts)
    text = _normalize(readable)
    included_ids = {f.id for f in included}
    kept = {_normalize(f.finding.value) for f in scan.findings if f.id not in included_ids}
    # Yerine yazılan metin değeri zaten içeriyorsa (genelleştirmede olabilir) kaçak sayılmaz.
    # Tablo eylemleri (yaş/tarih) hücre konumuyla yapılır; kaydırılmış değer başka satırın özgün değeriyle
    # çakışabileceği için bu denetime girmez.
    # Çıktı ham biçimiyle (XML etiketleri, JSON anahtarları dahil) okunur; 1-2 karakterlik değerler (bina no "5")
    # orada rastlantıyla geçer ve gerçek kaçak olmadan kaydı engellerdi.
    must_be_gone: dict[str, str] = {}
    for f in included:
        v = _normalize(f.finding.value)
        if len(v) >= 3 and v not in _normalize(f.replacement) and not f.finding.source.startswith("sütun-") and v not in kept:
            must_be_gone.setdefault(v, f.finding.type)
    leaked = [tur for v, tur in must_be_gone.items() if v in text]
    if leaked and not kacak_kabul(leaked):
        raise PdfError(kacak_iletisi(leaked))


def _as_utf8(out: str) -> bytes:
    # Bildirimdeki kodlama ne olursa olsun bellekteki metin UTF-8'e çevrilerek denetlenir.
    return re.sub(r"^\s*<\?xml[^>]*\?>", '<?xml version="1.0" encoding="utf-8"?>', out, count=1).encode("utf-8")


def read_text_doc(path: str | os.PathLike) -> str:
    """Önizleme için dosyanın metni (taramadan önce, yalnızca bellekte gösterilir)."""
    text, _encoding, _bom = _read(Path(path))
    return text
