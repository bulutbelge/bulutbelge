"""E-posta dosyaları (.eml): başlıklar, gövde ve ekler.

Yalnızca standart kütüphane (`email`) kullanılır. `.msg` (Outlook, OLE) kapsam dışıdır.

- Başlıklar (Kimden, Kime, Konu, Received…) ve metin/HTML gövdeler metin olarak taranır
  ve maskelenir; MIME yapısı korunur.
- Ekler kendi biçimlerinin motoruyla (PDF, görsel, Word, Excel, PowerPoint, XML/TXT/CSV)
  maskelenir; iç içe e-postalar (message/rfc822, .eml eki) özyinelemeli işlenir.
- Taranamayan ekler (bilinmeyen tür, bozuk, çok derin iç içelik) maskeli kopyada
  SİLİNİR; içerikleri kişisel veri taşıyabileceği için olduğu gibi bırakılmaz.
- Ek dosya adları kişi adı taşıyabilir; maskeli kopyada "ek_N.uzantı" olarak yazılır.
- Ekler işlenirken geçici dizin kullanılır (yalnızca bu kullanıcıya açık, iş bitince silinir).
- Çıktı yeniden ayrıştırılır; işaretli bir değer gövde ya da başlıkta hâlâ okunuyorsa
  dosya yazılmaz.
"""

from __future__ import annotations

import mimetypes
import os
import shutil
import tempfile
from dataclasses import dataclass, field
from email import encoders, message_from_bytes
from email.header import Header, decode_header, make_header
from email.message import Message
from pathlib import Path

from .gecici import klasor_ac
from .detect import Finding
from .pdf import PdfError, count_types, unique_path
from .rules import Rules
from .textdoc import _scan_text

EML_EXTS = {".eml"}
MAX_BYTES = 50 * 1024 * 1024
MAX_DEPTH = 4

# Taranmayan başlıklar: yapı bilgisi, kişisel veri taşımaz.
_SKIP_HEADERS = {
    "mime-version",
    "content-type",
    "content-transfer-encoding",
    "content-disposition",
    "content-id",
    "content-length",
    "date",
}


@dataclass
class EmlFinding:
    id: str
    finding: Finding
    replacement: str
    span: tuple[int, int] | None = None  # önizleme metnindeki aralık; eklerde None


@dataclass
class EmlScan:
    text: str  # önizleme: başlıklar + metin gövdeler (yalnızca bellekte)
    findings: list[EmlFinding]
    warnings: list[str] = field(default_factory=list)


def is_eml(path: str | os.PathLike) -> bool:
    return Path(path).suffix.lower() in EML_EXTS


def _load(raw: bytes) -> Message:
    if len(raw) > MAX_BYTES:
        raise PdfError(f"Dosya çok büyük; en fazla {MAX_BYTES // (1024 * 1024)} MB")
    msg = message_from_bytes(raw)
    if not msg.keys() and not msg.get_payload():
        raise PdfError("Geçerli bir e-posta dosyası değil")
    return msg


def _read(path: Path) -> Message:
    if not path.is_file():
        raise PdfError("Dosya bulunamadı")
    return _load(path.read_bytes())


def _header_text(value: object) -> str:
    try:
        return str(make_header(decode_header(str(value))))
    except Exception:
        return str(value)


def _body_text(part: Message) -> str | None:
    payload = part.get_payload(decode=True)
    if payload is None:
        return None
    charsets = [part.get_content_charset() or "utf-8", "utf-8", "cp1254"]
    for cs in charsets:
        try:
            return payload.decode(cs)
        except (UnicodeDecodeError, LookupError):
            continue
    return None


def _is_attachment(part: Message) -> bool:
    if part.get_filename() is not None or part.get_content_disposition() == "attachment":
        return True
    return part.get_content_type() not in ("text/plain", "text/html") and not part.get_content_type().startswith(
        ("multipart/", "message/")
    )


def _attachment_ext(part: Message) -> str:
    name = _header_text(part.get_filename() or "")
    ext = Path(name).suffix.lower()
    if not ext:
        ext = (mimetypes.guess_extension(part.get_content_type()) or "").lower()
    return ext


class _Walker:
    """Epostayı gezer; scan için bulgu toplar, mask için ayrıca değiştirir."""

    def __init__(self, rules: Rules, excluded: set[str], apply: bool, tmp: Path | None):
        self.rules = rules
        self.excluded = excluded
        self.apply = apply
        self.tmp = tmp
        self.findings: list[EmlFinding] = []
        self.included: list[EmlFinding] = []
        self.warnings: list[str] = []
        self.counts: dict[str, int] = {}
        self.preview: list[str] = []
        self._len = 0
        self._attach_n = 0
        self._verify: list[tuple[str, list[EmlFinding]]] = []  # (çıktı metni, ele alınanlar) kaçak denetimi

    # -- yardımcılar
    def _emit(self, text: str) -> int:
        base = self._len
        self.preview.append(text)
        self._len += len(text)
        return base

    def _text(self, text: str, pid: str, base: int | None) -> str:
        """Bir metni tarar; apply ise maskelenmiş metni döner."""
        scan = _scan_text(text, "txt", "utf-8", self.rules)
        items = []
        for t in scan.findings:
            span = None if base is None else (base + t.finding.start, base + t.finding.end)
            items.append(EmlFinding(f"{pid}:{t.id}", t.finding, t.replacement, span))
        self.findings.extend(items)
        if not self.apply:
            return text
        inc = [i for i in items if i.id not in self.excluded]
        self.included.extend(inc)
        out = text
        for i in sorted(inc, key=lambda x: x.finding.start, reverse=True):
            out = out[: i.finding.start] + i.replacement + out[i.finding.end :]
        self._verify.append((out, inc))
        return out

    # -- gezinme
    def walk(self, msg: Message, pid: str, depth: int) -> None:
        self._headers(msg, pid)
        self._part(msg, pid, depth)

    def _headers(self, msg: Message, pid: str) -> None:
        names = []
        for name in msg.keys():
            if name not in names:
                names.append(name)
        for name in names:
            if name.lower() in _SKIP_HEADERS:
                continue
            values = msg.get_all(name) or []
            new_values = []
            changed = False
            for n, raw in enumerate(values):
                text = _header_text(raw)
                line = f"{name}: "
                base = self._emit(line) + len(line)
                self._emit(text + "\n")
                out = self._text(text, f"h{pid}.{name.lower()}{n}", base)
                new_values.append(out)
                changed = changed or out != text
            if self.apply and changed:
                del msg[name]
                for v in new_values:
                    msg[name] = Header(v, "utf-8").encode()

    def _part(self, msg: Message, pid: str, depth: int) -> None:
        ctype = msg.get_content_type()
        if ctype == "message/rfc822":
            self._nested_message(msg, pid, depth)
            return
        if msg.is_multipart():
            for i, child in enumerate(msg.get_payload()):
                if isinstance(child, Message):
                    self._part(child, f"{pid}.{i}", depth)
            return
        if _is_attachment(msg):
            self._attachment(msg, pid, depth)
            return
        text = _body_text(msg)
        if text is None:
            self.warnings.append("Okunamayan bir gövde bölümü maskeli kopyada silindi")
            if self.apply:
                msg.set_payload("")
            return
        if ctype == "text/html":
            self.warnings.append("HTML gövde düz metin olarak tarandı; &#…; ile yazılmış bölümleri elle kontrol edin")
        base = self._emit(text + "\n")
        out = self._text(text, f"b{pid}", base)
        if self.apply and out != text:
            del msg["Content-Transfer-Encoding"]
            msg.set_payload(out, "utf-8")

    def _nested_message(self, part: Message, pid: str, depth: int) -> None:
        if depth >= MAX_DEPTH:
            self._drop(part, "İç içe e-posta çok derin; maskeli kopyada silindi")
            return
        inner = part.get_payload()
        for i, m in enumerate(inner if isinstance(inner, list) else []):
            if isinstance(m, Message):
                self.walk(m, f"{pid}.{i}", depth + 1)

    def _drop(self, part: Message, warning: str) -> None:
        self.warnings.append(warning)
        if self.apply:
            part.set_payload("")
            del part["Content-Transfer-Encoding"]

    def _attachment(self, part: Message, pid: str, depth: int) -> None:
        self._attach_n += 1
        n = self._attach_n
        ext = _attachment_ext(part)
        payload = part.get_payload(decode=True) or b""
        new_name = f"ek_{n}{ext}"
        if ext in EML_EXTS:
            if depth >= MAX_DEPTH:
                self._drop(part, f"Ek {n}: iç içe e-posta çok derin; maskeli kopyada silindi")
                return
            try:
                inner = _load(payload)
            except PdfError:
                self._drop(part, f"Ek {n}: e-posta okunamadı; maskeli kopyada silindi")
                return
            prefix = f"n{pid}:"
            sub = _Walker(self.rules, {i[len(prefix):] for i in self.excluded if i.startswith(prefix)}, self.apply, self.tmp)
            sub.walk(inner, f"{pid}.e", depth + 1)
            self._merge_attachment(sub, pid)
            if self.apply:
                del part["Content-Transfer-Encoding"]
                part.set_payload(inner.as_bytes())
                encoders.encode_base64(part)
                self._rename(part, new_name)
            return
        kind = _kind_by_ext(ext)
        if kind is None or not payload or self.tmp is None:
            self._drop(part, f"Ek {n} ({ext or 'türsüz'}) taranamadı; maskeli kopyada silindi")
            self._rename(part, new_name)
            return
        src = self.tmp / f"ek{n}{ext}"
        src.write_bytes(payload)
        try:
            if not self.apply:
                for iid, f, repl in _scan_attachment(src, kind, self.rules):
                    self.findings.append(EmlFinding(f"a{pid}:{iid}", f, repl, None))
                self.warnings.append(f"Ek {n} ({ext}) kendi biçimiyle işlendi; bulguları önizlemede konumlanmaz")
                return
            prefix = f"a{pid}:"
            excl = {i[len(prefix):] for i in self.excluded if i.startswith(prefix)}
            cnt: dict[str, int] = {}
            out, _masked, warns = _mask_attachment(src, self.tmp / f"ek{n}_maskeli{ext}", kind, self.rules, excl, cnt)
            data = Path(out).read_bytes()
            Path(out).unlink(missing_ok=True)
        except Exception:
            self._drop(part, f"Ek {n} ({ext}) işlenemedi; maskeli kopyada silindi")
            self._rename(part, new_name)
            return
        finally:
            src.unlink(missing_ok=True)
        for k, v in cnt.items():
            self.counts[k] = self.counts.get(k, 0) + v
        self.warnings.extend(f"Ek {n}: {w}" for w in warns)
        del part["Content-Transfer-Encoding"]
        part.set_payload(data)
        encoders.encode_base64(part)
        self._rename(part, new_name)

    def _merge_attachment(self, sub: "_Walker", pid: str) -> None:
        self.findings.extend(
            EmlFinding(f"n{pid}:{f.id}", f.finding, f.replacement, None) for f in sub.findings
        )
        self.included.extend(sub.included)
        self.warnings.extend(sub.warnings)
        for k, v in sub.counts.items():
            self.counts[k] = self.counts.get(k, 0) + v
        self._verify.extend(sub._verify)

    def _rename(self, part: Message, name: str) -> None:
        if not self.apply:
            return
        if part.get_filename() is not None:
            part.set_param("filename", name, header="Content-Disposition")
        part.del_param("name")


def _kind_by_ext(ext: str) -> str | None:
    from .documents import SUPPORTED_EXTS, kind_of

    if ext not in SUPPORTED_EXTS or ext in EML_EXTS:
        return None
    return kind_of(f"x{ext}")


def _scan_attachment(path: Path, kind: str, rules: Rules) -> list[tuple[str, Finding, str]]:
    from . import office
    from .pdf import scan_pdf
    from .textdoc import scan_text_doc

    if kind == "metin":
        return [(t.id, t.finding, t.replacement) for t in scan_text_doc(path, rules).findings]
    fmt = office.format_of(path)
    if kind in ("word", "sunum", "tablo") and fmt is not None:
        return [(o.id, o.finding, o.replacement) for o in office.scan(path, fmt, rules).findings]
    return [(f.id, f.finding, f.replacement) for f in scan_pdf(path, rules).findings]


def _mask_attachment(
    src: Path, dst: Path, kind: str, rules: Rules, excluded: set[str], counts: dict[str, int]
) -> tuple[str, int, list[str]]:
    from . import office
    from .pdf import mask_pdf
    from .textdoc import mask_text_doc

    if kind == "metin":
        return mask_text_doc(src, dst, rules, excluded, counts=counts)
    fmt = office.format_of(src)
    if kind in ("word", "sunum", "tablo") and fmt is not None:
        return office.mask(src, dst, fmt, rules, excluded, counts=counts)
    res = mask_pdf(src, dst, rules, excluded, counts=counts)
    return res.target, res.masked, res.warnings


def scan_eml(path: str | os.PathLike, rules: Rules) -> EmlScan:
    msg = _read(Path(path))
    tmp = klasor_ac("bulutbelge-eposta-")
    try:
        w = _Walker(rules, set(), False, tmp)
        w.walk(msg, "0", 0)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return EmlScan("".join(w.preview), w.findings, list(dict.fromkeys(w.warnings)))


def mask_eml(
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

    msg = _read(src)
    tmp = klasor_ac("bulutbelge-eposta-")
    try:
        # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions -- 0o700 yalnızca sahibine açık geçici klasör
        os.chmod(tmp, 0o700)
        w = _Walker(rules, excluded, True, tmp)
        w.walk(msg, "0", 0)
        data = msg.as_bytes()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    _verify_output(data, w)

    fd, name = tempfile.mkstemp(suffix=dst.suffix, dir=dst.parent)
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.replace(name, dst)
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    total = counts if counts is not None else {}
    count_types(total, (f.finding.type for f in w.included))
    for k, v in w.counts.items():
        total[k] = total.get(k, 0) + v
    attachments = sum(w.counts.values())
    return str(dst), len(w.included) + attachments, list(dict.fromkeys(w.warnings))


def _verify_output(data: bytes, w: _Walker) -> None:
    """Çıktıyı yeniden okur; maskelenmesi gereken bir değer hâlâ görünüyorsa durdurur."""
    from .pdf import _normalize

    hay = _normalize("\n".join(_visible_texts(_load(data))))
    leaked = 0
    for _text, inc in w._verify:
        for f in inc:
            v = _normalize(f.finding.value)
            if v and v not in _normalize(f.replacement) and v in hay:
                leaked += 1
    if leaked:
        raise PdfError(f"Kaçak tespiti: maskelenmesi gereken {leaked} değer çıktıda hâlâ okunuyor. Dosya yazılmadı.")


def _visible_texts(msg: Message) -> list[str]:
    """Başlık değerleri ve metin gövdeler (ekler hariç)."""
    texts = [_header_text(msg[n]) for n in msg.keys() if n.lower() not in _SKIP_HEADERS]
    if msg.is_multipart():
        for c in msg.get_payload():
            if isinstance(c, Message):
                texts += _visible_texts(c)
    elif not _is_attachment(msg):
        t = _body_text(msg)
        if t:
            texts.append(t)
    return texts


def preview_text(path: str | os.PathLike) -> str:
    """Başlıklar ve gövde metni (yalnızca bellekte); ekler dahil değildir."""
    return "\n".join(_visible_texts(_read(Path(path))))
