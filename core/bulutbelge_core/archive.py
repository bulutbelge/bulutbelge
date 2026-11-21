"""ZIP arşivi desteği (e-Fatura UBL XML paketleri ve karışık belge arşivleri).

Güvenlik kuralları:
- Yalnızca düz veya göreli yollu girdiler açılır (`../`, mutlak yol, sembolik bağ reddedilir).
- Zip bombasına karşı arşiv boyutu, dosya sayısı ve açılmış toplam bayt sınırları zorunludur.
- Maskeli arşiv çıktısına yalnızca desteklenen ve başarıyla maskelenen belgeler yazılır;
  içindeki desteklenmeyen dosyalar sızıntı riskine karşı kopyaya alınmaz ve kullanıcı uyarılır.
- İç dosya adları (ör. ETTN UUID veya kişi adı taşıyan adlar) da maskelenir.
"""

from __future__ import annotations

import dataclasses
import os
import re
import stat
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from . import office
from .gecici import gecici_klasor
from .detect import Finding
from .paste import mask_filename
from .pdf import PdfError, count_types, mask_pdf, scan_pdf, unique_path
from .rules import DATA_TYPES, Rules
from .textdoc import mask_text_doc, scan_text_doc

ARCHIVE_EXTS = {".zip"}
MAX_ZIP_BYTES = 50 * 1024 * 1024
MAX_ENTRY_COUNT = 50
MAX_UNCOMPRESSED_BYTES = 100 * 1024 * 1024

_UUID_RE = re.compile(
    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
    re.IGNORECASE,
)


@dataclass
class ArchiveFinding:
    id: str
    entry_index: int
    entry_label: str
    page: int
    finding: Finding
    replacement: str
    start: int = 0
    end: int = 0


@dataclass
class ArchiveScan:
    entries: int
    text: str
    findings: list[ArchiveFinding]
    warnings: list[str] = field(default_factory=list)
    entry_summaries: list[dict[str, Any]] = field(default_factory=list)


def _safe_rel_path(raw_name: str) -> PurePosixPath:
    norm = raw_name.replace("\\", "/")
    p = PurePosixPath(norm)
    if not norm or p.is_absolute() or ".." in p.parts or (p.parts and ":" in p.parts[0]):
        raise PdfError("Arşivde güvensiz dosya yolu bulundu")
    return p


_KIMLIK_MASK_TIPLERI = ("kisi_adi", "tc_kimlik", "vkn", "iban", "telefon", "eposta", "ettn", "mersis", "kredi_karti")


def _ad_kurallari(rules: Rules) -> Rules:
    """Dosya ve klasör adlarında kişisel veri sızıntısını önlemek için kimlik kurallarını açık tutar."""
    return dataclasses.replace(
        rules,
        types={
            k: (dataclasses.replace(r, enabled=True) if k in _KIMLIK_MASK_TIPLERI else r)
            for k, r in rules.types.items()
        },
    )


def _mask_rel_part(part: str, ad_kurallari: Rules) -> str:
    part = _UUID_RE.sub(DATA_TYPES["ettn"].tag.strip("[]"), part)
    masked = mask_filename(f"{part}.txt", ad_kurallari)
    if masked.endswith(".txt"):
        masked = masked[:-4]
    return masked.strip("/ ")


def _masked_entry_name(rel: PurePosixPath, index: int, rules: Rules) -> str:
    ad_kurallari = _ad_kurallari(rules)
    stem = rel.stem
    if ad_kurallari.types.get("ettn") and ad_kurallari.types["ettn"].enabled:
        stem = _UUID_RE.sub(DATA_TYPES["ettn"].tag.strip("[]"), stem)
    masked_leaf = mask_filename(f"{stem}{rel.suffix}", ad_kurallari)
    clean_leaf = masked_leaf or f"belge-{index + 1}{rel.suffix.lower()}"
    masked_dirs = [p for p in (_mask_rel_part(seg, ad_kurallari) for seg in rel.parent.parts if seg not in ("", ".")) if p]
    return "/".join([*masked_dirs, clean_leaf])


def _extract_supported(src: Path, workdir: Path, rules: Rules) -> tuple[list[tuple[int, str, str, Path, str]], list[str]]:
    from .documents import kind_of

    if not src.is_file():
        raise PdfError("Dosya bulunamadı")
    if src.stat().st_size > MAX_ZIP_BYTES:
        raise PdfError(f"ZIP arşivi çok büyük; en fazla {MAX_ZIP_BYTES // (1024 * 1024)} MB")
    if not zipfile.is_zipfile(src):
        raise PdfError("Geçersiz veya bozuk ZIP dosyası")

    extracted: list[tuple[int, str, str, Path, str]] = []
    skipped = 0
    total_bytes = 0

    try:
        with zipfile.ZipFile(src, "r") as zf:
            infos = [info for info in zf.infolist() if not info.is_dir()]
            if len(infos) > MAX_ENTRY_COUNT:
                raise PdfError(f"Arşivde çok fazla dosya var; en fazla {MAX_ENTRY_COUNT}")
            for idx, info in enumerate(infos):
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise PdfError("Arşivde sembolik bağa izin verilmiyor")
                rel = _safe_rel_path(info.filename)
                ext = rel.suffix.lower()
                if ext in ARCHIVE_EXTS:
                    skipped += 1
                    continue
                try:
                    kind = kind_of(f"dosya{ext}")
                except PdfError:
                    skipped += 1
                    continue
                if info.file_size > MAX_UNCOMPRESSED_BYTES:
                    raise PdfError("Arşiv içindeki dosya boyutu sınırı aşıyor")

                dest = workdir / f"entry_{idx}{ext}"
                with zf.open(info, "r") as zin, dest.open("wb") as zout:
                    while True:
                        chunk = zin.read(65536)
                        if not chunk:
                            break
                        total_bytes += len(chunk)
                        if total_bytes > MAX_UNCOMPRESSED_BYTES:
                            raise PdfError("Arşivin açılmış boyutu izin verilen sınırı aşıyor")
                        zout.write(chunk)
                masked_rel = _masked_entry_name(rel, len(extracted), rules)
                extracted.append((len(extracted), rel.as_posix(), masked_rel, dest, kind))
    except zipfile.BadZipFile:
        raise PdfError("Geçersiz veya bozuk ZIP dosyası") from None
    except NotImplementedError:
        raise PdfError("Bu ZIP sıkıştırma yöntemi veya şifreli ZIP desteklenmiyor") from None
    except RuntimeError as exc:
        if "encrypted" in str(exc).lower() or "password" in str(exc).lower():
            raise PdfError("Parolalı ZIP dosyaları açılamaz; önce şifreyi kaldırın") from None
        raise PdfError(f"ZIP okunamadı: {exc}") from None

    if not extracted:
        raise PdfError("Arşivde desteklenen belge bulunamadı (PDF, XML, Office, metin, CSV, görsel)")
    warnings: list[str] = []
    if skipped:
        warnings.append(f"Arşivdeki {skipped} desteklenmeyen girdi güvenlik nedeniyle atlandı.")
    return extracted, warnings


def scan_archive(path: str | os.PathLike, rules: Rules) -> ArchiveScan:
    """ZIP arşivindeki tüm desteklenen belgeleri tarar."""
    src = Path(path).resolve()
    findings: list[ArchiveFinding] = []
    text_parts: list[str] = []
    entry_summaries: list[dict[str, Any]] = []
    offset = 0

    with gecici_klasor("bb-zip-") as tmp:
        entries, warnings = _extract_supported(src, Path(tmp), rules)
        for idx, _raw_rel, masked_rel, ep, kind in entries:
            header = f"=== [{idx + 1}/{len(entries)}] {masked_rel} ===\n"
            text_parts.append(header)
            offset += len(header)
            label = f"Arşiv #{idx + 1} ({Path(masked_rel).suffix.lstrip('.').upper()})"
            ext_low = ep.suffix.lower()
            entry_pages = 1

            if kind == "metin":
                s = scan_text_doc(ep, rules)
                warnings.extend(w for w in s.warnings if w not in warnings)
                body = s.text
                for f in s.findings:
                    moved = dataclasses.replace(f.finding, start=offset + f.finding.start, end=offset + f.finding.end)
                    findings.append(ArchiveFinding(f"a:{idx}:{f.id}", idx, label, 1, moved, f.replacement, moved.start, moved.end))
                entry_findings = [f.finding for f in s.findings]
                text_parts.append(body)
                offset += len(body)
            elif kind in ("word", "sunum", "tablo"):
                s = office.scan(ep, office.format_of(ep), rules)
                warnings.extend(w for w in s.warnings if w not in warnings)
                body = f"[{masked_rel}: {len(s.findings)} bulgu]"
                for f in s.findings:
                    findings.append(ArchiveFinding(f"a:{idx}:{f.id}", idx, label, 1, f.finding, f.replacement, offset, offset + len(body)))
                entry_findings = [f.finding for f in s.findings]
                text_parts.append(body)
                offset += len(body)
            else:
                s = scan_pdf(ep, rules)
                warnings.extend(w for w in s.warnings if w not in warnings)
                entry_pages = max(1, int(s.pages or 1))
                body = f"[{masked_rel}: {s.pages} sayfa, {len(s.findings)} bulgu]"
                for f in s.findings:
                    findings.append(ArchiveFinding(f"a:{idx}:{f.id}", idx, label, f.page, f.finding, f.replacement, offset, offset + len(body)))
                entry_findings = [f.finding for f in s.findings]
                text_parts.append(body)
                offset += len(body)
            entry_counts: dict[str, int] = {}
            count_types(entry_counts, (f.type for f in entry_findings))
            entry_summaries.append(
                {
                    "sira": idx + 1,
                    "ad": masked_rel,
                    "uzanti": ext_low,
                    "etiket": label,
                    "sayfa_sayisi": entry_pages,
                    "bulgu_sayisi": len(entry_findings),
                    "sayilar": entry_counts,
                }
            )
            text_parts.append("\n\n")
            offset += 2

    return ArchiveScan(
        entries=len(entries),
        text="".join(text_parts),
        findings=findings,
        warnings=warnings,
        entry_summaries=entry_summaries,
    )


def mask_archive(
    source: str | os.PathLike,
    target: str | os.PathLike,
    rules: Rules,
    excluded_ids: set[str] | None = None,
    make_dirs: bool = False,
    counts: dict[str, int] | None = None,
    entry_details: list[dict[str, Any]] | None = None,
) -> tuple[str, int, list[str]]:
    """ZIP arşivindeki desteklenen belgeleri maskeler ve yeni ZIP yazar."""
    excluded_ids = excluded_ids or set()
    src = Path(source).resolve()
    dst = Path(target).resolve()
    if src == dst:
        raise PdfError("Hedef, kaynak dosyanın kendisi olamaz")
    if dst.suffix.lower() != ".zip":
        dst = dst.with_suffix(".zip")
    if make_dirs:
        dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.parent.is_dir():
        raise PdfError("Hedef klasör bulunamadı")
    dst = unique_path(dst)

    total_masked = 0
    local_counts: dict[str, int] = {}

    with gecici_klasor("bb-zip-") as tmp:
        gp = Path(tmp)
        entries, warnings = _extract_supported(src, gp, rules)
        masked_outputs: list[tuple[str, Path]] = []

        for idx, _raw_rel, masked_rel, ep, kind in entries:
            prefix = f"a:{idx}:"
            entry_excluded = {x[len(prefix):] for x in excluded_ids if x.startswith(prefix)}
            out_path = gp / f"masked_{idx}{ep.suffix}"
            entry_counts: dict[str, int] = {}
            entry_pages = 1

            if kind == "metin":
                written, n, wlist = mask_text_doc(ep, out_path, rules, excluded_ids=entry_excluded, counts=entry_counts)
            elif kind in ("word", "sunum", "tablo"):
                written, n, wlist = office.mask(
                    ep, out_path, office.format_of(ep), rules, excluded_ids=entry_excluded, counts=entry_counts
                )
            else:
                if ep.suffix.lower() == ".pdf":
                    import pymupdf

                    with pymupdf.open(ep) as d_pdf:
                        entry_pages = max(1, d_pdf.page_count)
                res = mask_pdf(ep, out_path, rules, excluded_ids=entry_excluded, counts=entry_counts)
                written, n, wlist = res.target, res.masked, res.warnings

            total_masked += n
            for k, v in entry_counts.items():
                local_counts[k] = local_counts.get(k, 0) + v
            warnings.extend(w for w in wlist if w not in warnings)
            masked_outputs.append((masked_rel, Path(written)))
            if entry_details is not None:
                entry_details.append(
                    {
                        "sira": idx + 1,
                        "ad": masked_rel,
                        "uzanti": ep.suffix.lower(),
                        "etiket": f"Arşiv #{idx + 1} ({ep.suffix.lstrip('.').upper()})",
                        "sayfa_sayisi": entry_pages,
                        "gizlenecek_sayisi": n,
                        "sayilar": dict(entry_counts),
                    }
                )

        tmp_fd, tmp_name = tempfile.mkstemp(suffix=".zip", dir=dst.parent)
        os.close(tmp_fd)
        try:
            with zipfile.ZipFile(tmp_name, "w", compression=zipfile.ZIP_DEFLATED) as zout:
                seen_names: set[str] = set()
                for arcname, file_path in masked_outputs:
                    final_name = arcname
                    if final_name in seen_names:
                        p = PurePosixPath(arcname)
                        final_name = f"{p.parent.as_posix() + '/' if p.parent.as_posix() != '.' else ''}{p.stem}_{len(seen_names) + 1}{p.suffix}"
                    seen_names.add(final_name)
                    zout.write(file_path, arcname=final_name)
            os.replace(tmp_name, dst)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise

    if counts is not None:
        for k, v in local_counts.items():
            counts[k] = counts.get(k, 0) + v
    return str(dst), total_masked, warnings


def read_archive_text(path: str | os.PathLike) -> str:
    """Önizleme için ZIP arşivi içindeki belge özet/metnini okur."""
    from .textdoc import read_text_doc

    src = Path(path).resolve()
    parts: list[str] = []
    with gecici_klasor("bb-zip-prev-") as tmp:
        entries, _ = _extract_supported(src, Path(tmp), Rules.default())
        for idx, raw_rel, _masked_rel, ep, kind in entries:
            parts.append(f"=== [{idx + 1}/{len(entries)}] {raw_rel} ===\n")
            if kind == "metin":
                parts.append(read_text_doc(ep))
            else:
                parts.append(f"[{raw_rel} ({kind.upper()})]")
            parts.append("\n\n")
    return "".join(parts)
