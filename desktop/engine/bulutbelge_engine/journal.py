"""İşlem günlüğü: motorun okuma ve maskeleme işlemlerini çekirdeğin hash zincirli
günlüğüne yazar. Günlük veri klasöründedir (BULUTBELGE_DATA_DIR).

Kural: günlük yazılamıyorsa işlem yapılmaz. İşlemden önce günlüğün yazılabildiği
denetlenir; işlem bittikten sonra kayıt eklenemezse sonuç döndürülmez, maskeli
kopya yazıldıysa silinir (kaydı olmayan kopya kalmaz).

Günlüğe yol, dosya özeti, tür bazında sayı, profil adı, çağıran ve sonuç girer;
bulguların değeri, belge içeriği ve hata mesajı girmez (hata yalnızca koduyla).
Yol ve amaç yazılmadan önce çekirdekle taranır: klasör ve dosya adlarındaki kişi adı ve
diğer kişisel veriler etikete çevrilir (bağımsız inceleme bulgu 17; sunucudaki 2.18 ile aynı yaklaşım).

Anahtarlı mühür (bulgu 22): her kayıt, günlükten ayrı bir dosyada duran rastgele 32 baytlık
anahtarla HMAC-SHA256 ile mühürlenir (`gunluk-anahtari.json`, izinleri yalnızca kullanıcıya açık;
`BULUTBELGE_JOURNAL_KEY_FILE` ile başka bir yere, ör. ayrı bir birime konabilir). Günlüğü
değiştirip zinciri baştan hesaplayan ama anahtarı okuyamayan biri mührü tutturamaz. Anahtar ilk
kullanımda üretilir; o ana kadarki eski kayıtlar mühürsüz kalır ve okunur, sonrakiler mühürsüz
kabul edilmez. Anahtar dosyası kaybolmuşken günlükte mühürlü kayıt varsa yeni anahtar üretilmez:
günlük yazılamaz sayılır (şüphede reddet). Karar: docs/kararlar/2026-11-23-denetim-zinciri-sabit-nokta.md.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
from collections import Counter
from contextvars import ContextVar
from pathlib import Path
from typing import Any, Callable

from bulutbelge_core.audit import AuditError, AuditLog, _last_line, _locked, file_sha256, filter_records, to_csv
from bulutbelge_core.dosya_adi import mask_log_text

from . import settings
from .protocol import EngineError

LOG_FILE = "islem-gunlugu.jsonl"
KEY_FILE = "gunluk-anahtari.json"
KEY_ENV = "BULUTBELGE_JOURNAL_KEY_FILE"
_KEY_KIND = "bulutbelge-gunluk-muhur"

# Kim çağırıyor: masaüstü arayüzü ("kullanici") ya da ajan komutu ("ajan", ad).
CALLER: ContextVar[tuple[str, str | None]] = ContextVar("bulutbelge_caller", default=("kullanici", None))

UNWRITABLE = "İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı"


def mask_path(path: str | None) -> str | None:
    """Yolun her parçasını (klasör ve dosya adı) `mask_log_text` ile temizler; ayraçlar ve uzantı korunur."""
    if not path:
        return path
    parts = re.split(r"([/\\])", str(path))
    for i, part in enumerate(parts):
        if part in ("/", "\\") or not part:
            continue
        if i == 0 and re.fullmatch(r"[A-Za-z]:", part):
            continue  # Windows sürücü harfi
        parts[i] = mask_log_text(part, filename=True) or part
    return "".join(parts)


class _MaskedLog(AuditLog):
    """Kaynak/hedef yolu ve amaç yazılmadan önce maskelenir; zincir ve satır biçimi AuditLog ile aynı."""

    def append(self, op: str, **kw: Any) -> dict[str, Any]:
        for key in ("source", "target"):
            if kw.get(key):
                kw[key] = mask_path(kw[key])
        if kw.get("purpose"):
            kw["purpose"] = mask_log_text(kw["purpose"])[:200]
        return super().append(op, **kw)


def key_path() -> Path:
    """Mühür anahtarının yolu: `BULUTBELGE_JOURNAL_KEY_FILE` ya da veri klasöründe günlükten ayrı dosya."""
    raw = os.environ.get(KEY_ENV)
    return Path(raw) if raw else settings.data_dir() / KEY_FILE


def _read_key(path: Path) -> tuple[bytes, int]:
    try:
        obj = json.loads(path.read_text(encoding="utf-8"))
        key = base64.b64decode(obj["anahtar"], validate=True)
        since = obj["zorunlu_sira"]
    except (OSError, ValueError, KeyError, TypeError):
        raise AuditError("Günlük mühür anahtarı okunamadı") from None
    if obj.get("tur") != _KEY_KIND or len(key) != 32 or not isinstance(since, int) or since < 1:
        raise AuditError("Günlük mühür anahtarı geçersiz")
    return key, since


def _restrict(path: Path) -> None:
    """Dosyayı yalnızca sahibine açar (POSIX 0600). Windows'ta veri klasörü (%APPDATA%) zaten kullanıcıya özeldir."""
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _tail_info(log_path: Path) -> tuple[int, bool]:
    """Günlüğün son kaydının sırası ve mühürlü olup olmadığı (masaüstü günlüğü şifresizdir)."""
    line = _last_line(log_path)
    if line is None:
        return 0, False
    try:
        rec = json.loads(line)
        if rec.get("tur") == "kontrol_noktasi":
            return int(rec["son_seq"]), "mac" in rec
        return int(rec["seq"]), "mac" in rec
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AuditError("Günlüğün son kaydı okunamadı") from None


def journal_key(log_path: Path) -> tuple[bytes, int]:
    """(anahtar, zorunlu_sira). Yoksa günlük kilidi altında üretilir; zorunlu sıra o anki son sıranın bir fazlası."""
    path = key_path()
    if path.is_file():
        return _read_key(path)
    try:
        with _locked(log_path.with_name(log_path.name + ".kilit")):
            if path.is_file():
                return _read_key(path)
            last_seq, sealed = _tail_info(log_path)
            if sealed:
                raise AuditError(
                    "Günlük mühür anahtarı bulunamadı; mühürlü kayıtlar doğrulanamaz. "
                    "Anahtarı geri koyun ya da eski günlüğü başka bir yere taşıyın"
                )
            key = secrets.token_bytes(32)
            data = {
                "v": 1,
                "tur": _KEY_KIND,
                "anahtar": base64.b64encode(key).decode("ascii"),
                "zorunlu_sira": last_seq + 1,
            }
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                    f.flush()
                    os.fsync(f.fileno())
                _restrict(tmp)
                os.replace(tmp, path)
            finally:
                tmp.unlink(missing_ok=True)
            _restrict(path)
            return key, last_seq + 1
    except AuditError:
        raise
    except OSError as exc:
        raise AuditError(f"Günlük mühür anahtarı yazılamadı ({type(exc).__name__})") from None


def log() -> AuditLog:
    path = settings.data_dir() / LOG_FILE
    key, since = journal_key(path)
    return _MaskedLog(path, mac_key=key, mac_from_seq=since)


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
    result_of: Callable[[dict[str, Any]], tuple[str, str | None]] = lambda _r: ("basarili", None),
) -> dict[str, Any]:
    """`fn`i çalıştırır, sonucu (başarılı ya da hata) günlüğe yazar. `purpose`: işlemin gerekçesi.
    `result_of`: başarılı sonucun günlükteki adı ve notu (ör. kaçağa rağmen kayıt: "kacakla", türler)."""
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
    outcome, note = result_of(result)
    try:
        lg.append(
            op,
            result=outcome,
            error=note,
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


def setting_change(what: str, fn: Callable[[], Any], counts: dict[str, int] | None = None) -> Any:
    """Güvenlik ayarı değişikliği (bulgu 18): "yonetim" kaydı. Değer, klasör yolu, terim, parola yazılmaz;
    yalnızca neyin değiştiği (`what`) ve sayılar. Günlük yazılamıyorsa değişiklik yapılmaz."""
    return run(
        "yonetim",
        fn,
        source=f"(ayar) {what}",
        profile=None,
        counts_of=lambda _r: dict(counts or {}),
        hash_source=False,
    )


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
    """Zinciri ve anahtarlı mührü denetler. `sealed`: mührü doğrulanan kayıt, `legacy`: mühürsüz eski kayıt sayısı."""
    try:
        v = log().verify()
    except AuditError as exc:
        return {"ok": False, "count": 0, "broken_at": None, "reason": str(exc), "last_hash": None, "sealed": 0, "legacy": 0}
    return {
        "ok": v.ok,
        "count": v.count,
        "broken_at": v.broken_at,
        "reason": v.reason,
        "last_hash": v.last_hash,
        "last_seq": v.last_seq,
        "sealed": v.mac_checked,
        "legacy": v.legacy,
    }


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
