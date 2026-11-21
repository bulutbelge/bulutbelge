"""Belge komutları: çekirdek kütüphaneyi protokole bağlar.

Bulguların orijinal değerleri arayüze yalnızca bellekte gösterilmek için
döner; diske ya da günlüğe yazılmaz. Maskeleme sırasında değerler arayüzden
geri alınmaz: motor belgeyi aynı kurallarla yeniden tarar ve kullanıcının
dışarıda bıraktığı bulguları kimlikleriyle eler.
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Any

from bulutbelge_core import amac
from bulutbelge_core.audit import file_sha256
from bulutbelge_core.cleanup import cleanup_summary
from bulutbelge_core.archive import ARCHIVE_EXTS, mask_archive, read_archive_text, scan_archive
from bulutbelge_core.batch import default_target_dir, plan_folder
from bulutbelge_core.dosya_adi import has_person_name, suggest_masked_name
from bulutbelge_core.documents import SUPPORTED_EXTS, kind_of
from bulutbelge_core.eposta import EML_EXTS, mask_eml, preview_text, scan_eml
from bulutbelge_core.image import IMAGE_EXTS
from bulutbelge_core.ocr import ocr_available
from bulutbelge_core.baglanabilirlik import analyze_documents
from bulutbelge_core.tanima import scan_document as tanima_scan_document
from bulutbelge_core.ozel_nitelikli import scan_document, scan_special, special_warnings
from bulutbelge_core.paste import scan_paste
from bulutbelge_core.report import write_report, report_path
from bulutbelge_core.pdf import PdfError, default_target, mask_pdf, render_page, scan_pdf
from bulutbelge_core.udf import UDF_EXTS, mask_udf, preview_text as udf_preview, scan_udf
from bulutbelge_core.textdoc import TEXT_EXTS, mask_text_doc, read_text_doc, scan_text_doc
from bulutbelge_core import office
from bulutbelge_core.slides import slide_of_part, slide_preview
from bulutbelge_core.word import MAX_BYTES as WORD_MAX_BYTES, WORD_EXTS
from bulutbelge_core.detect import PatternTimeout, detect
from bulutbelge_core.pseudonym import Pseudonyms
from bulutbelge_core.rules import DATA_TYPES, RuleError, Rules, describe_types

from . import journal, settings
from .protocol import EngineError

# Metin düzeyinde maskelenen biçimler: (kaynak, hedef, kurallar, dışlananlar, make_dirs) → (yol, sayı, uyarılar)
OFFICE_KINDS = {"word": office.WORD, "sunum": office.POWERPOINT, "tablo": office.EXCEL}


def _office_masker(fmt: office.OfficeFormat):
    def run(source, target, rules, excluded, make_dirs=False, counts=None, manual_cells=None, options=None):
        return office.mask(
            source, target, fmt, rules, excluded, make_dirs, counts=counts, manual_cells=manual_cells, options=options
        )

    return run


DOC_MASKERS = {"metin": mask_text_doc, "eposta": mask_eml, "udf": mask_udf, "arsiv": mask_archive, **{k: _office_masker(f) for k, f in OFFICE_KINDS.items()}}


def _require_str(params: dict[str, Any], key: str) -> str:
    value = params.get(key)
    if not isinstance(value, str) or not value:
        raise EngineError("invalid_params", f"'{key}' gerekli")
    return value


def _rules(params: dict[str, Any]) -> Rules:
    try:
        rules = Rules.from_dict(params.get("rules"))
    except RuleError as exc:
        raise EngineError("invalid_rules", str(exc)) from None
    if rules.uses_pseudonyms():
        # Takma ad tablosu kasadadır; kasa kilitliyse takma ad yöntemi çalışmaz.
        if not settings.VAULT.unlocked:
            raise EngineError("vault_locked", "Takma ad yöntemi için önce özel ifade kasasının kilidini açın")
        rules.pseudonyms = Pseudonyms(settings.VAULT.pseudonyms, rules.pseudonym_per_document)
    rules.allow = settings.allow_matcher()
    return rules


def _keep_pseudonyms(rules: Rules) -> None:
    """Maskeleme başarılıysa yeni takma adları kasaya yazar (taramada yazılmaz)."""
    if rules.pseudonyms is not None and rules.pseudonyms.changed:
        settings.VAULT.save_pseudonyms(rules.pseudonyms.table)


def _previewed(fn):
    """Önizleme komutları işlem günlüğüne "onizleme" olarak girer (dosya başına bir kez)."""

    def wrapper(params: dict[str, Any]) -> Any:
        path = _require_str(params, "path")
        return journal.preview(path, lambda: fn(params))

    wrapper.__doc__ = fn.__doc__
    return wrapper


def _user_errors(fn):
    def wrapper(params: dict[str, Any]) -> Any:
        try:
            return fn(params)
        except (PdfError, PatternTimeout) as exc:
            raise EngineError("document", str(exc)) from None
        except RuleError as exc:
            raise EngineError("invalid_rules", str(exc)) from None

    return wrapper


def rules_types(_params: dict[str, Any]) -> list[dict[str, Any]]:
    return describe_types()


def doc_formats(_params: dict[str, Any]) -> dict[str, Any]:
    """Desteklenen uzantılar (dosya seçme penceresi için) ve OCR durumu."""
    return {
        "pdf": ["pdf"],
        "gorsel": sorted(e.lstrip(".") for e in IMAGE_EXTS),
        "metin": sorted(e.lstrip(".") for e in TEXT_EXTS),
        "eposta": sorted(e.lstrip(".") for e in EML_EXTS),
        "udf": sorted(e.lstrip(".") for e in UDF_EXTS),
        "word": sorted(e.lstrip(".") for e in WORD_EXTS),
        "sunum": sorted(e.lstrip(".") for e in office.POWERPOINT.exts),
        "tablo": sorted(e.lstrip(".") for e in office.EXCEL.exts),
        "arsiv": sorted(e.lstrip(".") for e in ARCHIVE_EXTS),
        "all": sorted(e.lstrip(".") for e in SUPPORTED_EXTS),
        "ocr": ocr_available(),
    }


def _finding_json(id_: str, f: Any, replacement: str) -> dict[str, Any]:
    return {
        "id": id_,
        "type": f.type,
        "type_label": DATA_TYPES[f.type].label,
        "source": f.source,
        "value": f.value,
        "replacement": replacement,
        "confidence": f.confidence,
    }


def doc_scan(params: dict[str, Any]) -> dict[str, Any]:
    """Belgeyi tarar; işlem günlüğüne "okuma" olarak girer (TAKIP 1.38)."""
    path = _require_str(params, "path")
    return journal.run(
        "okuma",
        lambda: _doc_scan(params),
        source=path,
        profile=journal.profile_of(params),
        counts_of=lambda r: journal.count_findings(r["findings"]),
    )


@_user_errors
def _doc_scan(params: dict[str, Any]) -> dict[str, Any]:
    path = _require_str(params, "path")
    result = _doc_scan_body(params, path)
    # KVKK m.6 özel nitelikli veri uyarısı: bulgu değil, uyarı (TAKIP 1.46).
    result["warnings"] = [*result["warnings"], *special_warnings(scan_document(path))]
    # Dosya adı hijyeni (TAKIP 1.60): ad kişi adı taşıyorsa uyarı ve adsız çıktı adı önerisi.
    suggested = suggest_masked_name(path)
    if suggested:
        result["warnings"] = [
            *result["warnings"],
            "Dosya adı kişi adı taşıyor olabilir; maskeli kopyaya adsız bir ad önerildi (suggested_target)",
        ]
        result["suggested_target"] = suggested
    return result


def _doc_scan_body(params: dict[str, Any], path: str) -> dict[str, Any]:
    kind = kind_of(path)
    if kind == "metin":
        # Metin belgede önizleme metnin kendisidir; bulgular karakter aralığıyla döner.
        scan = scan_text_doc(path, _rules(params))
        return {
            "format": kind,
            "pages": 1,
            "warnings": scan.warnings,
            "default_target": default_target(path),
            "text": scan.text,
            "findings": [
                {
                    **_finding_json(t.id, t.finding, t.replacement),
                    "page": 1,
                    "locatable": True,
                    "kind": "metin",
                    "rects": [],
                    "span": [t.finding.start, t.finding.end],
                    "preview": None,
                }
                for t in scan.findings
            ],
        }
    if kind == "arsiv":
        scan = scan_archive(path, _rules(params))
        return {
            "format": kind,
            "pages": scan.entries,
            "warnings": scan.warnings,
            "default_target": default_target(path),
            "text": scan.text,
            "findings": [
                {
                    **_finding_json(a.id, a.finding, a.replacement),
                    "page": a.page,
                    "locatable": True,
                    "kind": "metin",
                    "rects": [],
                    "span": [a.start, a.end],
                    "preview": None,
                }
                for a in scan.findings
            ],
        }
    if kind == "udf":
        # UYAP belgesi: önizleme metin belge gibidir ("format": "metin"); metin uzunluğu korunarak maskelenir.
        scan = scan_udf(path, _rules(params))
        return {
            "format": "metin",
            "pages": 1,
            "warnings": scan.warnings,
            "default_target": default_target(path),
            "text": scan.text,
            "findings": [
                {
                    **_finding_json(u.id, u.finding, u.replacement),
                    "page": 1,
                    "locatable": True,
                    "kind": "metin",
                    "rects": [],
                    "span": [u.finding.start, u.finding.end],
                    "preview": None,
                }
                for u in scan.findings
            ],
        }
    if kind == "eposta":
        # Önizleme: başlıklar + gövde metni, metin belge gibi gösterilir ("format": "metin");
        # ek bulguları önizlemede konumlanmaz (span yok) ama listede yer alır ve maskelenir.
        scan = scan_eml(path, _rules(params))
        return {
            "format": "metin",
            "pages": 1,
            "warnings": scan.warnings,
            "default_target": default_target(path),
            "text": scan.text,
            "findings": [
                {
                    **_finding_json(e.id, e.finding, e.replacement),
                    "page": 1,
                    "locatable": True,
                    "kind": "metin",
                    "rects": [],
                    **({"span": list(e.span)} if e.span else {}),
                    "preview": None,
                }
                for e in scan.findings
            ],
        }
    if kind in OFFICE_KINDS:
        # Önizleme: Word belgenin kendisi (doc.bytes), sunum slayt tarifi (doc.slides), tablo ızgarası
        # (doc.sheets). Bulgular "birim" anahtarı ve birim içindeki karakter aralığıyla eşleşir.
        scan = office.scan(path, OFFICE_KINDS[kind], _rules(params))
        pages = slide_of_part(path) if kind == "sunum" else {}
        return {
            "format": kind,
            "pages": max(pages.values(), default=1),
            "warnings": scan.warnings,
            "default_target": default_target(path),
            "findings": [
                {
                    **_finding_json(o.id, o.finding, o.replacement),
                    "page": pages.get(o.part, 1),
                    "locatable": True,
                    "kind": "metin",
                    "rects": [],
                    "unit": f"{o.part}:{o.unit}",
                    "span": [o.finding.start, o.finding.end],
                    "preview": None,
                }
                for o in scan.findings
            ],
        }
    result = scan_pdf(path, _rules(params), previews=True, flatten=bool(params.get("flatten")))
    return {
        "format": kind,
        "ocr_pages": result.ocr_pages,
        "pages": result.pages,
        "warnings": result.warnings,
        "default_target": default_target(path),
        "findings": [
            {
                **_finding_json(f.id, f.finding, f.replacement),
                "page": f.page,
                "locatable": f.locatable,
                "kind": f.kind,
                "rects": [[round(v, 2) for v in r] for r in f.rects],
                "preview": "data:image/png;base64," + base64.b64encode(f.preview).decode() if f.preview else None,
            }
            for f in result.findings
        ],
    }


def doc_mask(params: dict[str, Any]) -> dict[str, Any]:
    """Maskeli kopyayı yerelde üretir ve günlüğe yazar."""
    source = _require_str(params, "source")
    purpose = _purpose(params)
    result = journal.run(
        "maskeleme",
        lambda: _doc_mask_checked(params),
        source=source,
        profile=journal.profile_of(params),
        counts_of=lambda r: r.get("counts") or {},
        target_of=lambda r: r["target"],
        purpose=purpose,
    )
    if params.get("report"):
        result["report"] = _write_report(params, source, purpose, result)
    return result


def _purpose(params: dict[str, Any]) -> str | None:
    """Gizleme gerekçesi: günlüğe ve rapora yazılır, boşsa yazılmaz (TAKIP 1.44)."""
    raw = params.get("purpose")
    if raw is not None and not isinstance(raw, str):
        raise EngineError("invalid_params", "'purpose' metin olmalı")
    text = (raw or "").strip()
    pid = params.get("purpose_id")
    if pid is not None:
        found = amac.find(pid)
        if found is None:
            raise EngineError("invalid_params", "'purpose_id' bilinen bir amaç değil")
        text = f"{found['name']} — {text}" if text else found["name"]
    return text[:200] or None


def purposes_list(_params: dict[str, Any]) -> list[dict[str, str]]:
    """Amaç listesi ve her biri için önerilen profil kimliği (TAKIP 1.29)."""
    return amac.purposes()


def _watermark(params: dict[str, Any], source: str) -> bool:
    """Filigran yalnızca PDF ve görselde uygulanır (diğer biçimlerde sessizce yok sayılır)."""
    return bool(params.get("watermark")) and kind_of(source) not in DOC_MASKERS


def _write_report(params: dict[str, Any], source: str, purpose: str | None, result: dict[str, Any]) -> str:
    """Değersiz gizleme raporunu maskeli kopyanın yanına yazar (TAKIP 1.66)."""
    target = result["target"]
    try:
        return write_report(
            report_path(target),
            source=source,
            source_sha256=file_sha256(source),
            target=target,
            target_sha256=file_sha256(target),
            counts=result.get("counts") or {},
            rules=Rules.from_dict(params.get("rules")),
            purpose=purpose,
            profile=journal.profile_of(params),
            watermark=_watermark(params, source),
            special=scan_document(source),
            cleanup=cleanup_summary(source),
            recognizability=tanima_scan_document(target),
        )
    except OSError:
        raise EngineError("write_failed", "Gizleme raporu yazılamadı") from None


@_user_errors
def _doc_mask_checked(params: dict[str, Any]) -> dict[str, Any]:
    target = _require_str(params, "target")
    try:
        result = _doc_mask(params)
    except PermissionError:
        raise EngineError(
            "permission",
            "Bu klasöre yazma izni yok. Başka bir klasör seçin. Mac'te: Sistem Ayarları › Gizlilik ve "
            "Güvenlik › Dosyalar ve Klasörler bölümünden BulutBelge'ye izin verin.",
        ) from None
    out = Path(result["target"])
    # Yazıldığı söylenen dosya gerçekten orada mı (Mac'te "seçilen yere kaydedilmedi" bildirimi, TAKIP 1.36).
    if not out.is_file():
        raise EngineError("write_failed", "Kopya kaydedilemedi: dosya hedef klasörde bulunamadı")
    result["target"] = str(out)
    result["changed"] = _target_change(Path(target), out)
    return result


def _target_change(requested: Path, written: Path) -> str | None:
    """Kaydedilen yol, kullanıcının seçtiğinden farklıysa nedenini söyler (yoksa None)."""
    req, out = requested.resolve(), written.resolve()
    if req == out:
        return None
    if req.parent != out.parent:
        return "Kopya seçtiğiniz klasöre değil, başka bir yere kaydedildi"
    if req.suffix.lower() != out.suffix.lower():
        return f"Kopya kaynak belgeyle aynı biçimde kalsın diye {out.suffix} uzantısıyla kaydedildi"
    return "Seçtiğiniz adda bir dosya vardı; o dosyanın üzerine yazılmadı, kopya yeni bir adla kaydedildi"


def _doc_mask(params: dict[str, Any]) -> dict[str, Any]:
    source = _require_str(params, "source")
    target = _require_str(params, "target")
    excluded = params.get("excluded_ids") or []
    if not isinstance(excluded, list):
        raise EngineError("invalid_params", "'excluded_ids' liste olmalı")
    rules = _rules(params)
    kind = kind_of(source)
    cells = _manual_cells(params.get("manual_cells"))
    if cells and kind != "tablo":
        raise EngineError("invalid_params", "Satır ve sütun seçimi yalnızca Excel için")
    _line_pseudonyms(rules, cells)
    if kind in DOC_MASKERS:
        if params.get("password"):
            raise EngineError("invalid_params", "Parolayla koruma yalnızca PDF için")
        counts: dict[str, int] = {}
        extra = {"manual_cells": cells} if cells else {}
        raw_excel = params.get("excel_options")
        if kind == "tablo" and isinstance(raw_excel, dict):
            # İsteğe bağlı Excel güvenli temizlik: gizli sayfaları görünür yap, formülleri düzleştir, yorum/grafik içini sil.
            extra["options"] = {
                k: bool(raw_excel.get(k)) for k in ("unhide_sheets", "flatten_formulas", "strip_comments", "strip_charts")
            }
        out, masked, warnings = DOC_MASKERS[kind](
            source, target, rules, {str(x) for x in excluded}, make_dirs=bool(params.get("make_dirs")), counts=counts, **extra
        )
        _keep_pseudonyms(rules)
        return {"target": out, "masked": masked, "warnings": warnings, "counts": counts}
    counts: dict[str, int] = {}
    result = mask_pdf(
        source,
        target,
        rules,
        {str(x) for x in excluded},
        manual_areas=_manual_areas(params.get("manual_areas")),
        make_dirs=bool(params.get("make_dirs")),
        drop_pages=_drop_pages(params.get("drop_pages")),
        password=_password(params.get("password")),
        counts=counts,
        watermark=_watermark(params, source),
        flatten=bool(params.get("flatten")),
        mask_pages=_page_spec(params.get("mask_pages"), "mask_pages"),
        exclude_pages=_page_spec(params.get("exclude_pages"), "exclude_pages"),
        strip_bookmarks=params.get("strip_bookmarks", True) is not False,
    )
    _keep_pseudonyms(rules)
    return {
        "flattened": result.flattened,
        "counts": counts,
        "target": result.target,
        "masked": result.masked,
        "warnings": result.warnings,
        "dropped": result.dropped,
        "encrypted": result.encrypted,
    }


def _manual_cells(raw: Any) -> list[tuple[str, str, int]]:
    """Excel'de elle seçilen satır ve sütunlar: [{"sheet": ad, "axis": "row"|"col", "index": n}]."""
    if not raw:
        return []
    if not isinstance(raw, list):
        raise EngineError("invalid_params", "'manual_cells' liste olmalı")
    out = []
    for c in raw:
        try:
            sheet, axis, index = str(c["sheet"]), str(c["axis"]), c["index"]
        except (KeyError, TypeError):
            raise EngineError("invalid_params", "Satır/sütun seçimi biçimi geçersiz") from None
        if axis not in ("row", "col") or not isinstance(index, int) or index < (1 if axis == "row" else 0):
            raise EngineError("invalid_params", "Satır/sütun seçimi biçimi geçersiz")
        method = c.get("method")
        if method is not None and method not in office.LINE_METHODS:
            raise EngineError("invalid_params", f"Satır/sütun için geçersiz yöntem: {method}")
        out.append((sheet, axis, index, method) if method else (sheet, axis, index))
    return out


def _line_pseudonyms(rules: Rules, cells: list[tuple]) -> None:
    """Satır/sütunda takma ad seçildiyse kasa açık olmalı; eşleme tablosu kasadan gelir."""
    if any(len(c) > 3 and c[3] == "takma_ad" for c in cells) and rules.pseudonyms is None:
        if not settings.VAULT.unlocked:
            raise EngineError("vault_locked", "Takma ad yöntemi için önce özel ifade kasasının kilidini açın")
        rules.pseudonyms = Pseudonyms(settings.VAULT.pseudonyms, rules.pseudonym_per_document)


def _password(raw: Any) -> str | None:
    """Kopyanın parolası; yalnızca bu çağrıda bellekte kalır, hiçbir yere yazılmaz."""
    if raw in (None, ""):
        return None
    if not isinstance(raw, str):
        raise EngineError("invalid_params", "'password' metin olmalı")
    return raw


def _drop_pages(raw: Any) -> list[int]:
    if not raw:
        return []
    if not isinstance(raw, list) or not all(isinstance(x, int) for x in raw):
        raise EngineError("invalid_params", "'drop_pages' sayı listesi olmalı")
    return raw


def _page_spec(raw: Any, name: str) -> str | list[int] | None:
    """Sayfa aralığı: metin ("4-6", "1, 4-5, 7", "tek") ya da sayı listesi; boşsa None (hepsi)."""
    if raw in (None, "", []):
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list) and all(isinstance(x, int) and not isinstance(x, bool) for x in raw):
        return raw
    raise EngineError("invalid_params", f"'{name}' sayfa aralığı metni (ör. 4-6) veya sayı listesi olmalı")


@_previewed
@_user_errors
def doc_bytes(params: dict[str, Any]) -> dict[str, Any]:
    """Word belgesinin kendisi (base64); arayüz belgeyi Word'deki gibi çizer. Yalnızca bellekte."""
    path = _require_str(params, "path")
    if kind_of(path) != "word":
        raise EngineError("invalid_params", "Yalnızca Word belgeleri için")
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        raise EngineError("document", "Dosya bulunamadı")
    if p.stat().st_size > WORD_MAX_BYTES:
        raise EngineError("document", "Dosya önizleme için çok büyük")
    return {"data": base64.b64encode(p.read_bytes()).decode()}


@_previewed
@_user_errors
def doc_slides(params: dict[str, Any]) -> dict[str, Any]:
    """PowerPoint önizlemesi: slaytlardaki kutular, metin, görsel ve notlar (yalnızca bellekte)."""
    path = _require_str(params, "path")
    if kind_of(path) != "sunum":
        raise EngineError("invalid_params", "Yalnızca PowerPoint sunumları için")
    return slide_preview(path)


@_previewed
@_user_errors
def doc_sheets(params: dict[str, Any]) -> dict[str, Any]:
    """Excel önizlemesi: sayfalar ve hücre ızgarası (yalnızca bellekte)."""
    path = _require_str(params, "path")
    if kind_of(path) != "tablo":
        raise EngineError("invalid_params", "Yalnızca Excel dosyaları için")
    return {"sheets": office.sheet_preview(path)}


@_previewed
@_user_errors
def doc_text(params: dict[str, Any]) -> dict[str, Any]:
    """Metin belgenin (XML, TXT, CSV) ya da ZIP arşivinin içeriği; taramadan önce önizleme için."""
    path = _require_str(params, "path")
    kind = kind_of(path)
    if kind == "arsiv":
        return {"text": read_archive_text(path)}
    if kind == "eposta":
        return {"text": preview_text(path)}
    if kind == "udf":
        return {"text": udf_preview(path)}
    if kind != "metin":
        raise EngineError("invalid_params", "Yalnızca XML, TXT, CSV, ZIP ve e-posta için")
    return {"text": read_text_doc(path)}


@_previewed
@_user_errors
def doc_page(params: dict[str, Any]) -> dict[str, Any]:
    """Önizleme için sayfa görüntüsü (yalnızca bellekte, diske yazılmaz)."""
    page = params.get("page")
    if not isinstance(page, int):
        raise EngineError("invalid_params", "'page' gerekli")
    width = params.get("width")
    png, w, h, count = render_page(_require_str(params, "path"), page, int(width) if isinstance(width, int) else 900)
    return {
        "image": "data:image/png;base64," + base64.b64encode(png).decode(),
        "width": w,
        "height": h,
        "pages": count,
    }


def _manual_areas(raw: Any) -> list[tuple]:
    if not raw:
        return []
    if not isinstance(raw, list):
        raise EngineError("invalid_params", "'manual_areas' liste olmalı")
    out = []
    for a in raw:
        try:
            x0, y0, x1, y1 = (float(v) for v in a["rect"])
            reason = a.get("reason")
            if isinstance(reason, str) and reason.strip():
                out.append((int(a["page"]), (x0, y0, x1, y1), reason.strip()[:40]))  # "[gerekçe]" etiketi yazılır
            else:
                out.append((int(a["page"]), (x0, y0, x1, y1)))
        except (KeyError, TypeError, ValueError):
            raise EngineError("invalid_params", "Elle seçilen alan biçimi geçersiz") from None
    return out


@_user_errors
def batch_plan(params: dict[str, Any]) -> dict[str, Any]:
    """Klasördeki desteklenen belgeleri ve her birinin hedef yolunu listeler; dosyalara dokunmaz."""
    source = _require_str(params, "source_dir")
    target = params.get("target_dir") or default_target_dir(source)
    files = plan_folder(source, target, recursive=params.get("recursive", True) is not False)
    return {
        "target_dir": target,
        "files": [{"source": f.source, "target": f.target, "relative": f.relative, "size": f.size} for f in files],
    }


@_user_errors
def batch_linkability(params: dict[str, Any]) -> dict[str, Any]:
    """Aynı işte maskelenen kopyalar arasında ortak kalan dolaylı tanımlayıcı/takma ad uyarısı (TAKIP 1.71).

    Yalnızca tür adı ve sayı döner; değer dönmez. Tek belgede ya da risk yokken uyarı listesi boştur.
    """
    paths = params.get("paths")
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        raise EngineError("invalid_params", "'paths' metin listesi olmalı")
    r = analyze_documents(paths)
    if r is None:
        return {"duzey": "Yok", "uyari": []}
    return r


@_user_errors
def rules_test(params: dict[str, Any]) -> list[dict[str, Any]]:
    """Ayarlar sayfasında kuralları örnek bir metin üzerinde dener."""
    text = params.get("text")
    if not isinstance(text, str):
        raise EngineError("invalid_params", "'text' gerekli")
    return [
        {"start": f.start, "end": f.end, "type": f.type, "type_label": DATA_TYPES[f.type].label}
        for f in detect(text[:20000], _rules(params))
    ]


def text_scan(params: dict[str, Any]) -> dict[str, Any]:
    """Yapıştırılan metin taraması; günlüğe kaynaksız "okuma" olarak girer (metnin özeti de yazılmaz:
    kısa bir metnin özeti, ör. tek bir numara, denenerek bulunabilir)."""
    return journal.run(
        "okuma",
        lambda: _text_scan(params),
        source="(yapıştırılan metin)",
        hash_source=False,
        profile=journal.profile_of(params),
        counts_of=lambda r: journal.count_findings(r["findings"]),
    )


@_user_errors
def _text_scan(params: dict[str, Any]) -> dict[str, Any]:
    """Yapıştırılan metni tarar (yalnızca bellekte). Temizlenmiş metni arayüz kurar.

    Takma ad yönteminde yeni takma adlar hemen kasaya yazılır: temizlenmiş metin
    kullanıcı kopyaladığı anda dışarı çıkabilir, eşlemenin kaybolmaması gerekir.
    """
    text = params.get("text")
    if not isinstance(text, str):
        raise EngineError("invalid_params", "'text' gerekli")
    rules = _rules(params)
    found = scan_paste(text, rules)
    _keep_pseudonyms(rules)
    return {
        "findings": [
            {
                **_finding_json(p.id, p.finding, p.replacement),
                "page": 1,
                "locatable": True,
                "kind": "metin",
                "rects": [],
                "span": [p.finding.start, p.finding.end],
                "preview": None,
            }
            for p in found
        ],
        # KVKK m.6 ipucu (TAKIP 1.46): yalnızca kategori ve sayı; eşleşen sözcük döndürülmez.
        "warnings": special_warnings(scan_special(text)),
    }


def allow_add(params: dict[str, Any]) -> list[dict[str, Any]]:
    """"Bunu bir daha hiç gizleme": değerin yalnızca özeti saklanır."""
    return settings.allow_add(params.get("values"), params.get("type"))


def allow_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.allow_list()


def allow_remove(params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.allow_remove(params.get("id"))


def history_list(_params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.history_list()


def history_add(params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.history_add(params)


def history_delete(params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.history_delete(params)


def history_clear(_params: dict[str, Any]) -> list[dict[str, Any]]:
    return settings.history_clear()


def settings_get(_params: dict[str, Any]) -> dict[str, Any]:
    return {**settings.load_settings(), "vault": settings.VAULT.status()}


def settings_save(params: dict[str, Any]) -> dict[str, Any]:
    return settings.save_settings(params)


def profiles_export(params: dict[str, Any]) -> dict[str, Any]:
    return settings.export_profiles(params)


def profiles_import(params: dict[str, Any]) -> dict[str, Any]:
    return settings.import_profiles(params)


def vault_create(params: dict[str, Any]) -> dict[str, Any]:
    return settings.VAULT.create(params.get("password"))


def vault_unlock(params: dict[str, Any]) -> dict[str, Any]:
    return settings.VAULT.unlock(_require_str(params, "password"))


def vault_save(params: dict[str, Any]) -> dict[str, Any]:
    return settings.VAULT.save(params.get("terms"))


def vault_change_password(params: dict[str, Any]) -> dict[str, bool]:
    return settings.VAULT.change_password(params.get("password"))


def vault_lock(_params: dict[str, Any]) -> dict[str, bool]:
    return settings.VAULT.lock()


def vault_pseudonyms(_params: dict[str, Any]) -> dict[str, Any]:
    return settings.VAULT.pseudonym_stats()


def vault_pseudonym_lookup(params: dict[str, Any]) -> dict[str, Any]:
    """Maske kaldırma: işlem günlüğüne "maske_kaldirma" olarak girer (değer ve takma ad yazılmaz)."""
    label = params.get("label")
    return journal.unmask(label, lambda: settings.VAULT.pseudonym_lookup(label))


def vault_pseudonym_restore_text(params: dict[str, Any]) -> dict[str, Any]:
    """Metin geri çevirme: günlüğe "maske_kaldirma" olarak girer (metin ve değerler yazılmaz, yalnızca sayı)."""
    text = params.get("text")
    return journal.unmask_text(lambda: settings.VAULT.pseudonym_restore_text(text))


def vault_pseudonym_clear(_params: dict[str, Any]) -> dict[str, Any]:
    return settings.VAULT.pseudonym_clear()


def vault_delete(_params: dict[str, Any]) -> dict[str, bool]:
    return settings.VAULT.delete()


def log_list(params: dict[str, Any]) -> dict[str, Any]:
    return journal.log_list(params)


def log_verify(params: dict[str, Any]) -> dict[str, Any]:
    return journal.log_verify(params)


def log_export(params: dict[str, Any]) -> dict[str, Any]:
    return journal.log_export(params)


def agent_get(_params: dict[str, Any]) -> dict[str, Any]:
    return settings.load_agent()


def agent_guide(_params: dict[str, Any]) -> dict[str, str]:
    """Ajana verilecek hazır yönerge (Ayarlar › Ajan erişimi'ndeki "Yönergeyi kopyala" düğmesi için)."""
    from . import kilavuz

    return {"prompt": kilavuz.guide_prompt(kilavuz.command_here()), "command": kilavuz.command_here()}


def agent_save(params: dict[str, Any]) -> dict[str, Any]:
    return settings.save_agent(params)
