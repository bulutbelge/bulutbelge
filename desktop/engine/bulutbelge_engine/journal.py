"""İşlem günlüğü: motorun okuma ve maskeleme işlemlerini çekirdeğin hash zincirli
günlüğüne yazar. Günlük veri klasöründedir (BULUTBELGE_DATA_DIR).

Kural: günlük yazılamıyorsa işlem yapılmaz. İşlemden önce günlüğün yazılabildiği
denetlenir; işlem bittikten sonra kayıt eklenemezse sonuç döndürülmez, maskeli
kopya yazıldıysa silinir (kaydı olmayan kopya kalmaz).

Günlüğe yol, dosya özeti, tür bazında sayı, profil adı, çağıran ve sonuç girer;
bulguların değeri, belge içeriği ve hata mesajı girmez (hata yalnızca koduyla).
"""

from __future__ import annotations

from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable

from bulutbelge_core.audit import AuditError, AuditLog, file_sha256, filter_records, to_csv

from . import settings
from .protocol import EngineError

LOG_FILE = "islem-gunlugu.jsonl"

# Kim çağırıyor: masaüstü arayüzü ("kullanici") ya da ajan komutu ("ajan", ad).
CALLER: ContextVar[tuple[str, str | None]] = ContextVar("bulutbelge_caller", default=("kullanici", None))

UNWRITABLE = "İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı"


def log() -> AuditLog:
    return AuditLog(settings.data_dir() / LOG_FILE)


def _preflight() -> AuditLog:
    try:
        lg = log()
        lg.check_writable()
        return lg
    except EngineError as exc:
        raise EngineError("log_unwritable", f"{UNWRITABLE} ({exc.message})") from None
    except AuditError as exc:
        raise EngineError("log_unwritable", f"{UNWRITABLE} ({exc})") from None


def profile_of(params: dict[str, Any]) -> str | None:
    rules = params.get("rules")
    if isinstance(rules, dict) and isinstance(rules.get("profile_name"), str):
        return rules["profile_name"]
    return params.get("profile") if isinstance(params.get("profile"), str) else None


def count_findings(findings: list[dict[str, Any]]) -> dict[str, int]:
    return dict(Counter(f["type"] for f in findings if isinstance(f, dict) and "type" in f))


def run(
    op: str,
    fn: Callable[[], dict[str, Any]],
    *,
    source: str | None,
    profile: str | None,
    counts_of: Callable[[dict[str, Any]], dict[str, int]],
    target_of: Callable[[dict[str, Any]], str | None] = lambda _r: None,
    hash_source: bool = True,
    purpose: str | None = None,
) -> dict[str, Any]:
    """`fn`i çalıştırır, sonucu (başarılı ya da hata) günlüğe yazar. `purpose`: işlemin gerekçesi."""
    lg = _preflight()
    caller, agent = CALLER.get()
    src_hash = file_sha256(source) if source and hash_source else None
    base = {"caller": caller, "agent": agent, "source": source, "source_sha256": src_hash, "profile": profile, "purpose": purpose}
    try:
        result = fn()
    except EngineError as exc:
        _append_failure(lg, op, base, "reddedildi" if exc.code in REFUSALS else "hata", exc.code)
        raise
    except Exception as exc:
        _append_failure(lg, op, base, "hata", type(exc).__name__)
        raise

    target = target_of(result)
    try:
        lg.append(
            op,
            result="basarili",
            target=target,
            target_sha256=file_sha256(target) if target else None,
            counts=counts_of(result),
            **base,
        )
    except AuditError as exc:
        if target:
            Path(target).unlink(missing_ok=True)  # kaydı olmayan kopya kalmasın
        raise EngineError("log_unwritable", f"{UNWRITABLE} ({exc})") from None
    return result


# Önizlemesi günlüğe yazılmış dosyalar (yol, boyut, değişme zamanı): motor açık kaldıkça aynı
# dosyanın her sayfası ya da yeniden çizimi ayrı kayıt olmasın. Dosya değişirse yeniden yazılır.
_PREVIEWED: set[tuple[str, int, int]] = set()


def _file_key(path: str) -> tuple[str, int, int] | None:
    try:
        st = Path(path).stat()
    except OSError:
        return None
    return (str(Path(path).resolve()).casefold(), st.st_size, st.st_mtime_ns)


def preview(path: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Önizleme okuması: dosya başına bir "onizleme" kaydı. Günlük yazılamazsa önizleme de verilmez."""
    key = _file_key(path)
    if key is not None and key in _PREVIEWED:
        return fn()
    result = run("onizleme", fn, source=path, profile=None, counts_of=lambda _r: {})
    if key is not None:
        _PREVIEWED.add(key)
    return result


def unmask(label: Any, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Takma adın gerçek değere çevrilmesi. Takma ad ve değer yazılmaz; yalnızca türü sayılır."""
    return run(
        "maske_kaldirma",
        fn,
        source=None,
        profile=None,
        counts_of=lambda r: {str(r.get("type")): 1} if r.get("type") else {},
    )


def unmask_text(fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Metindeki takma adların geri çevrilmesi. Metin ve değerler yazılmaz; yalnızca çevrilen sayı."""
    return run(
        "maske_kaldirma",
        fn,
        source=None,
        profile=None,
        counts_of=lambda r: {"takma_ad": int(r.get("count") or 0)} if r.get("count") else {},
    )


# Kullanıcının ya da iznin reddettiği işlemler (hata değil).
REFUSALS = {"not_allowed", "vault_locked", "write_not_allowed", "terms_unavailable", "profile_not_allowed"}


def _append_failure(lg: AuditLog, op: str, base: dict[str, Any], result: str, code: str) -> None:
    try:
        lg.append(op, result=result, error=code, **base)
    except AuditError:
        pass  # asıl hata kullanıcıya dönsün; işlem zaten yapılmadı


def refuse(op: str, code: str, message: str, *, source: str | None = None, profile: str | None = None) -> None:
    """İzin dışı istek: işlem yapılmadan önce reddedildiği günlüğe yazılır, sonra hata verilir."""
    lg = _preflight()
    caller, agent = CALLER.get()
    lg.append(op, caller=caller, agent=agent, source=source, profile=profile, result="reddedildi", error=code)
    raise EngineError(code, message)


# ---------- Arayüz komutları ----------

_FILTER_KEYS = ("date_from", "date_to", "file", "op", "caller")


def _filters(params: dict[str, Any]) -> dict[str, str | None]:
    return {k: (str(params[k]) if params.get(k) else None) for k in _FILTER_KEYS}


def _records() -> list[dict[str, Any]]:
    try:
        return log().records()
    except AuditError as exc:
        raise EngineError("log_unreadable", f"İşlem günlüğü okunamadı ({exc})") from None


def log_list(params: dict[str, Any]) -> dict[str, Any]:
    """Süzülmüş kayıtlar, yeniden eskiye. `limit` en fazla 1000."""
    items = filter_records(_records(), **_filters(params))
    limit = params.get("limit")
    limit = max(1, min(int(limit), 1000)) if isinstance(limit, int) else 200
    return {"total": len(items), "items": list(reversed(items))[:limit]}


def log_verify(_params: dict[str, Any]) -> dict[str, Any]:
    v = log().verify()
    return {"ok": v.ok, "count": v.count, "broken_at": v.broken_at, "reason": v.reason, "last_hash": v.last_hash}


def log_export(params: dict[str, Any]) -> dict[str, Any]:
    """Süzülmüş kayıtları CSV olarak yazar (Excel için BOM'lu UTF-8). Dışa aktarma da günlüğe girer."""
    target = params.get("target")
    if not isinstance(target, str) or not target:
        raise EngineError("invalid_params", "'target' gerekli")
    out = Path(target)
    if out.suffix.lower() != ".csv":
        out = out.with_suffix(".csv")
    if out.resolve().parent == settings.data_dir().resolve():
        raise EngineError("invalid_params", "Dışa aktarma ayar klasörüne yazılamaz")
    items = filter_records(_records(), **_filters(params))

    def write() -> dict[str, Any]:
        if not out.parent.is_dir():
            raise EngineError("document", "Hedef klasör bulunamadı")
        out.write_text("﻿" + to_csv(items), encoding="utf-8", newline="")
        return {"target": str(out), "count": len(items)}

    return run(
        "disa_aktarma",
        write,
        source=None,
        profile=None,
        counts_of=lambda _r: {},
        target_of=lambda r: r["target"],
    )
