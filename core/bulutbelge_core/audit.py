"""Hash zincirli işlem günlüğü (1.28 ile birleşik).

Her satır bir JSON kaydıdır. Kayıt, bir önceki kaydın özetini (`prev`) taşır ve
kendi özeti (`hash`) kaydın geri kalanının SHA-256'sıdır; aradaki bir kaydın
değiştirilmesi ya da silinmesi `verify` ile yakalanır.

Günlüğe yalnızca işlemin tarifi yazılır: zaman, işlem, yol, dosya özeti, tür
bazında bulgu sayısı, profil, çağıran ve sonuç. Orijinal değer, belge içeriği
ve hata mesajı (içerik taşıyabilir) yazılmaz; hata yalnızca koduyla girer.

Birden çok süreç (masaüstü motoru ve ajan komutu) aynı günlüğe yazabilir;
ekleme bir kilit dosyasıyla sıraya konur.

Sınır: dosyanın sonundan kayıt kesilirse zincir yine tutarlıdır. Bunu yakalamak
için son özetin dışarıda (ör. düzenli dışa aktarılan CSV) saklanması gerekir.

Saklama (TAKIP G.2, yalnızca sunucu çağırır): `prune` süresi dolan baştaki kayıtları
bir bütün hâlinde siler ve günlüğün ilk satırına bir kontrol noktası yazar (son silinen
kaydın özeti ve sırası). Kalan kayıtlar değişmez; `verify` zinciri kontrol noktasından
sürdürür. Karar: docs/kararlar/2026-11-21-g2-gunluk-saklama-kontrol-noktasi.md.
"""

from __future__ import annotations

import base64
import binascii
import csv
import hashlib
import io
import json
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterator

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

GENESIS = "0" * 64
VERSION = 1
ENCRYPTED_VERSION = 2
_AUDIT_AAD = b"bulutbelge-audit-v2"

# Kayıttaki alanlar ve sırası (CSV sütunları da bu sırayla).
FIELDS = (
    "seq",
    "at",
    "op",
    "source",
    "target",
    "source_sha256",
    "target_sha256",
    "counts",
    "profile",
    "purpose",
    "caller",
    "agent",
    "result",
    "error",
    "kanal",
    "calisan",
    "uygulama",
    "kayit",
    "alan",
    "prev",
    "hash",
)

# "onizleme": belgenin arayüzde gösterilmek için okunması (dosya başına bir kayıt);
# "maske_kaldirma": takma adın gerçek değere çevrilmesi (kasadan, kullanıcının isteğiyle).
# "yonetim": sunucu yönetim panelindeki değişiklik (API anahtarı, sunucu ayarı); belge yok.
# "erisim": panelde kim neye baktı (giriş, çıkış, sayfa, kayıt ayrıntısı, CSV); belge yok.
OPS = ("okuma", "maskeleme", "disa_aktarma", "onizleme", "maske_kaldirma", "yonetim", "erisim")
CALLERS = ("kullanici", "ajan")
RESULTS = ("basarili", "hata", "reddedildi")

_LOCK_TIMEOUT = 10.0

# Kontrol noktası kaydının türü. Olay kayıtlarında "tur" alanı yoktur; ayırt edici budur.
CHECKPOINT_KIND = "kontrol_noktasi"
_CHECKPOINT_KEYS = frozenset(
    {"v", "tur", "son_seq", "son_silinen_ozet", "silinen", "budama_sayisi", "budama_zamani", "esik", "saklama_gun", "hash"}
)


class AuditError(Exception):
    """Günlük okunamıyor ya da yazılamıyor: işlem yapılmamalı."""


@dataclass
class VerifyResult:
    ok: bool
    count: int  # doğrulanan olay kaydı sayısı (kontrol noktası sayılmaz)
    broken_at: int | None = None  # bozulan ilk kaydın satır sırası (1'den)
    reason: str = ""
    last_hash: str = GENESIS
    checkpoint: dict[str, Any] | None = None  # günlük budanmışsa geçerli kontrol noktası


@dataclass
class PruneResult:
    removed: int  # bu budamada silinen kayıt sayısı
    remaining: int  # kalan olay kaydı sayısı
    changed: bool  # dosya yeniden yazıldı mı
    checkpoint: dict[str, Any] | None = None  # budama sonrası kontrol noktası (yoksa None)


def is_checkpoint(record: Any) -> bool:
    return isinstance(record, dict) and record.get("tur") == CHECKPOINT_KIND


def _checkpoint_error(rec: dict[str, Any]) -> str | None:
    """Kontrol noktası biçim ve özet denetimi; sorun yoksa None."""
    if set(rec) != _CHECKPOINT_KEYS:
        return "Kontrol noktası biçimi geçersiz"
    son_seq, ozet, silinen = rec.get("son_seq"), rec.get("son_silinen_ozet"), rec.get("silinen")
    if not (isinstance(son_seq, int) and not isinstance(son_seq, bool) and son_seq >= 1):
        return "Kontrol noktası biçimi geçersiz"
    if not (isinstance(silinen, int) and not isinstance(silinen, bool) and 1 <= silinen <= son_seq):
        return "Kontrol noktası biçimi geçersiz"
    if not (isinstance(ozet, str) and len(ozet) == 64 and ozet != GENESIS):
        return "Kontrol noktası biçimi geçersiz"
    if record_hash(rec) != rec.get("hash"):
        return "Kontrol noktası sonradan değiştirilmiş"
    return None


def _parse_at(at: Any) -> datetime | None:
    """Kayıt zamanı (ISO 8601); okunamazsa None. Saat dilimi yoksa yerel saat sayılır."""
    if not isinstance(at, str) or not at:
        return None
    try:
        dt = datetime.fromisoformat(at)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.astimezone()


def file_sha256(path: str | os.PathLike) -> str | None:
    p = Path(path)
    if not p.is_file():
        return None
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def record_hash(record: dict[str, Any]) -> str:
    body = {k: v for k, v in record.items() if k != "hash"}
    data = json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _clean_counts(counts: Any) -> dict[str, int]:
    if not isinstance(counts, dict):
        return {}
    return {str(k): int(v) for k, v in sorted(counts.items()) if isinstance(v, int) and v > 0}


def _opt_str(value: Any, limit: int = 1024) -> str | None:
    if value in (None, ""):
        return None
    return str(value)[:limit]


@contextmanager
def _locked(lock_path: Path) -> Iterator[None]:
    """Süreçler arası kilit (Windows: msvcrt, diğerleri: fcntl)."""
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    try:
        deadline = time.monotonic() + _LOCK_TIMEOUT
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise AuditError("Günlük kilidi alınamadı") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def _last_line(path: Path) -> bytes | None:
    """Dosyanın son boş olmayan satırı (tamamını okumadan)."""
    if not path.exists() or path.stat().st_size == 0:
        return None
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        end = f.tell()
        block, data = 4096, b""
        pos = end
        while pos > 0:
            step = min(block, pos)
            pos -= step
            f.seek(pos)
            data = f.read(step) + data
            stripped = data.rstrip(b"\r\n")
            if b"\n" in stripped:
                return stripped.rsplit(b"\n", 1)[1]
        stripped = data.rstrip(b"\r\n")
        return stripped or None


def _fsync_dir(path: Path) -> None:
    """`os.replace` sonrası dizin girdisini diske yazar (POSIX); Windows'ta desteklenmez, atlanır."""
    if os.name == "nt":
        return
    try:
        fd = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _validate_cipher_key(cipher_key: bytes | None) -> bytes | None:
    if cipher_key is None:
        return None
    if not isinstance(cipher_key, (bytes, bytearray)) or len(cipher_key) != 32:
        raise ValueError("Günlük şifreleme anahtarı 32 bayt olmalı")
    return bytes(cipher_key)


def _seal_record(record: dict[str, Any], cipher_key: bytes | None) -> str:
    plain = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
    if cipher_key is None:
        return plain + "\n"
    nonce = os.urandom(12)
    ct = AESGCM(cipher_key).encrypt(nonce, plain.encode("utf-8"), _AUDIT_AAD)
    token = base64.urlsafe_b64encode(nonce + ct).decode("ascii")
    return json.dumps({"v": ENCRYPTED_VERSION, "enc": token}, separators=(",", ":")) + "\n"


def _open_record(raw: bytes | str, cipher_key: bytes | None) -> dict[str, Any]:
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError("Geçersiz kayıt")
    if obj.get("v") == ENCRYPTED_VERSION and "enc" in obj:
        if cipher_key is None:
            raise AuditError("Şifreli günlük kaydı için anahtar gerekli")
        enc = obj.get("enc")
        if not isinstance(enc, str):
            raise AuditError("Şifreli kayıt biçimi geçersiz")
        try:
            blob = base64.urlsafe_b64decode(enc.encode("ascii"))
            if len(blob) < 28:
                raise AuditError("Şifreli kayıt bozuk")
            plain = AESGCM(cipher_key).decrypt(blob[:12], blob[12:], _AUDIT_AAD)
            rec = json.loads(plain.decode("utf-8"))
        except (binascii.Error, InvalidTag, UnicodeDecodeError, ValueError):
            raise AuditError("Şifreli kayıt çözülemedi veya sonradan değiştirilmiş") from None
        if not isinstance(rec, dict):
            raise AuditError("Çözülen günlük kaydı geçersiz")
        return rec
    return obj


class AuditLog:
    def __init__(self, path: str | os.PathLike, cipher_key: bytes | None = None) -> None:
        self.path = Path(path)
        self.lock_path = self.path.with_name(self.path.name + ".kilit")
        self._cipher_key = _validate_cipher_key(cipher_key)

    def _tail(self) -> tuple[int, str]:
        line = _last_line(self.path)
        if line is None:
            return 0, GENESIS
        try:
            rec = _open_record(line, self._cipher_key)
            if is_checkpoint(rec):
                # Bütün kayıtlar budanmış: zincir kontrol noktasından sürer.
                return int(rec["son_seq"]), str(rec["son_silinen_ozet"])
            return int(rec["seq"]), str(rec["hash"])
        except AuditError:
            raise
        except (ValueError, KeyError, TypeError):
            raise AuditError("Günlüğün son kaydı okunamadı") from None

    def check_writable(self) -> None:
        """İşlemden önce: günlük açılıp sonuna eklenebiliyor mu."""
        try:
            with _locked(self.lock_path):
                self._tail()
                with self.path.open("ab"):
                    pass
        except AuditError:
            raise
        except OSError as exc:
            raise AuditError(f"Günlük yazılamıyor ({type(exc).__name__})") from None

    def append(
        self,
        op: str,
        *,
        caller: str,
        result: str,
        source: str | None = None,
        target: str | None = None,
        source_sha256: str | None = None,
        target_sha256: str | None = None,
        counts: dict[str, int] | None = None,
        profile: str | None = None,
        agent: str | None = None,
        error: str | None = None,
        purpose: str | None = None,
        at: str | None = None,
        kanal: str | None = None,
        calisan: str | None = None,
        paket: str | None = None,
        uygulama: str | None = None,
        kayit: str | None = None,
        alan: str | None = None,
    ) -> dict[str, Any]:
        """`at`: işlemin başka yerde (ör. masaüstünde) yapıldığı zaman; boşsa şimdi. Zincir sırası
        yazılma sırasıdır, `at` geriye dönük olabilir. `calisan`: sunucu uygulamasında işlemi yapan çalışanın kimliği (uygulama bildirir); verilmezse kayda girmez.
        `kanal`: isteğin geldiği yer (ör.
        "terminal_curl", "masaustu"); verilmezse kayda girmez (eski kayıtlarla aynı biçim)."""
        if op not in OPS:
            raise ValueError(f"Bilinmeyen işlem: {op}")
        if caller not in CALLERS:
            raise ValueError(f"Bilinmeyen çağıran: {caller}")
        if result not in RESULTS:
            raise ValueError(f"Bilinmeyen sonuç: {result}")
        try:
            with _locked(self.lock_path):
                seq, prev = self._tail()
                record: dict[str, Any] = {
                    "v": VERSION,
                    "seq": seq + 1,
                    "at": at or datetime.now().astimezone().isoformat(timespec="seconds"),
                    "op": op,
                    "source": _opt_str(source),
                    "target": _opt_str(target),
                    "source_sha256": _opt_str(source_sha256, 64),
                    "target_sha256": _opt_str(target_sha256, 64),
                    "counts": _clean_counts(counts),
                    "profile": _opt_str(profile, 60),
                    # İşlemin amacı (sunucuda zorunlu); masaüstünde boş kalabilir.
                    "purpose": _opt_str(purpose, 200),
                    "caller": caller,
                    "agent": _opt_str(agent, 60),
                    "result": result,
                    "error": _opt_str(error, 40),
                    "prev": prev,
                }
                if kanal:
                    record["kanal"] = _opt_str(kanal, 40)
                if calisan:
                    # API'yi çağıran uygulamanın bildirdiği çalışan kimliği (İ.10); doğrulaması uygulamaya aittir.
                    record["calisan"] = _opt_str(calisan, 64)
                # Tek alan görüntüleme: hangi uygulama (anahtar adı), uygulamadaki kayıt ve alan.
                # Değerin kendisi hiçbir zaman yazılmaz.
                if uygulama:
                    record["uygulama"] = _opt_str(uygulama, 60)
                if kayit:
                    record["kayit"] = _opt_str(kayit, 80)
                if alan:
                    record["alan"] = _opt_str(alan, 60)
                if paket:
                    record["paket"] = _opt_str(paket, 80)
                record["hash"] = record_hash(record)
                line = _seal_record(record, self._cipher_key)
                with self.path.open("ab") as f:
                    f.write(line.encode("utf-8"))
                    f.flush()
                    os.fsync(f.fileno())
                return record
        except AuditError:
            raise
        except OSError as exc:
            raise AuditError(f"Günlük yazılamıyor ({type(exc).__name__})") from None

    def _all_records(self) -> list[dict[str, Any]]:
        """Kontrol noktası dahil bütün kayıtlar, dosyadaki sırayla."""
        if not self.path.exists():
            return []
        out = []
        try:
            with self.path.open("rb") as f:
                for n, raw in enumerate(f, 1):
                    if not raw.strip():
                        continue
                    try:
                        out.append(_open_record(raw, self._cipher_key))
                    except AuditError:
                        raise
                    except ValueError:
                        raise AuditError(f"Günlüğün {n}. satırı okunamadı") from None
        except OSError as exc:
            raise AuditError(f"Günlük okunamıyor ({type(exc).__name__})") from None
        return out

    def records(self) -> list[dict[str, Any]]:
        """Bütün olay kayıtları, eskiden yeniye. Okunamayan satır atlanmaz: hata verir.

        Kontrol noktası bir olay değildir, burada dönmez (panel, CSV ve süzgeçler değişmeden çalışır);
        budama bilgisi için `checkpoint()`."""
        return [r for r in self._all_records() if not is_checkpoint(r)]

    def checkpoint(self) -> dict[str, Any] | None:
        """Günlük budanmışsa ilk satırdaki kontrol noktası; değilse None."""
        recs = self._all_records()
        return recs[0] if recs and is_checkpoint(recs[0]) else None

    def migrate_to_encrypted(self) -> int:
        """Eski şifresiz (v1) satırları mevcut hash zincirini bozmadan v2 AES-GCM satırına çevirir."""
        if self._cipher_key is None:
            raise ValueError("Günlük göçü için şifreleme anahtarı gerekli")
        if not self.path.exists():
            return 0
        try:
            with _locked(self.lock_path):
                raw_lines = self.path.read_bytes().splitlines()
                new_lines: list[str] = []
                migrated = 0
                for n, raw in enumerate(raw_lines, 1):
                    if not raw.strip():
                        continue
                    try:
                        obj = json.loads(raw)
                    except ValueError:
                        raise AuditError(f"Günlüğün {n}. satırı okunamadı") from None
                    if not isinstance(obj, dict):
                        raise AuditError(f"Günlüğün {n}. satırı okunamadı") from None
                    if obj.get("v") == ENCRYPTED_VERSION and "enc" in obj:
                        # Anahtarla açıldığını doğrula ve mevcut şifreli satırı koru.
                        _open_record(raw, self._cipher_key)
                        new_lines.append(raw.decode("utf-8") + "\n")
                    else:
                        new_lines.append(_seal_record(obj, self._cipher_key))
                        migrated += 1
                if migrated == 0:
                    return 0
                tmp = self.path.with_name(self.path.name + ".tmp")
                with tmp.open("wb") as f:
                    for line in new_lines:
                        f.write(line.encode("utf-8"))
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, self.path)
                return migrated
        except AuditError:
            raise
        except OSError as exc:
            raise AuditError(f"Günlük şifrelenemedi ({type(exc).__name__})") from None

    def verify(self) -> VerifyResult:
        """Zinciri baştan doğrular. İlk satır kontrol noktasıysa zincir oradan sürer: ilk kaydın `prev`
        değeri son silinen kaydın özeti, `seq` değeri son silinen sıranın bir fazlası olmalı."""
        if not self.path.exists():
            return VerifyResult(True, 0)
        with self.path.open("rb") as f:
            return self._verify_lines(enumerate(f, 1))

    def _verify_lines(self, lines: Any) -> VerifyResult:
        prev, seq, count = GENESIS, 0, 0
        checkpoint: dict[str, Any] | None = None
        first = True
        for n, raw in lines:
            if not raw.strip():
                continue
            try:
                rec = _open_record(raw, self._cipher_key)
            except AuditError as exc:
                return VerifyResult(False, count + 1, n, str(exc))
            except ValueError:
                return VerifyResult(False, count + 1, n, "Kayıt okunamıyor")
            if is_checkpoint(rec):
                if not first:
                    return VerifyResult(False, count + 1, n, "Kontrol noktası yalnızca günlüğün ilk kaydı olabilir")
                first = False
                err = _checkpoint_error(rec)
                if err:
                    return VerifyResult(False, count + 1, n, err)
                checkpoint = rec
                prev, seq = rec["son_silinen_ozet"], rec["son_seq"]
                continue
            first = False
            count += 1
            seq += 1
            if rec.get("prev") != prev:
                return VerifyResult(False, count, n, "Zincir kopuk: önceki kayıt silinmiş ya da değiştirilmiş")
            if rec.get("seq") != seq:
                return VerifyResult(False, count, n, "Sıra numarası beklenmeyen")
            if record_hash(rec) != rec.get("hash"):
                return VerifyResult(False, count, n, "Kayıt sonradan değiştirilmiş")
            prev = rec["hash"]
        return VerifyResult(True, count, last_hash=prev, checkpoint=checkpoint)

    def prune(
        self,
        days: int | None = None,
        *,
        older_than: datetime | None = None,
        now: datetime | None = None,
    ) -> PruneResult:
        """Zamanı `older_than`'dan (ya da `now - days`) eski olan baştaki kayıtları bir bütün hâlinde siler.

        Yalnızca baştan kesintisiz bir dilim silinir: zamanı eşikten yeni (ya da okunamayan) ilk kayıtta
        durulur. Günlüğün ilk satırına kontrol noktası yazılır; önceki kontrol noktası varsa yenisiyle
        değişir (sayaçlar toplanır). Kalan satırlar bayt bayt aynı kalır. Zincir doğrulanmıyorsa budama
        yapılmaz (şüphede reddet: bozuk bölüm budamayla örtülmesin). Silinecek kayıt yoksa dosyaya
        dokunulmaz. Yazma geçici dosyaya yapılır ve `os.replace` ile değiştirilir; yarıda kesilirse eski
        günlük olduğu gibi kalır.
        """
        if (days is None) == (older_than is None):
            raise ValueError("Budama için ya gün sayısı ya da eşik zamanı verilmeli")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.astimezone()
        if days is not None:
            if isinstance(days, bool) or not isinstance(days, int) or days < 1:
                raise ValueError("Saklama süresi en az 1 gün olmalı")
            older_than = now - timedelta(days=days)
        assert older_than is not None
        if older_than.tzinfo is None:
            older_than = older_than.astimezone()
        if not self.path.exists():
            return PruneResult(0, 0, False)
        tmp = self.path.with_name(self.path.name + ".budama.tmp")
        try:
            with _locked(self.lock_path):
                raw_lines = [ln for ln in self.path.read_bytes().splitlines(keepends=True) if ln.strip()]
                v = self._verify_lines(enumerate(raw_lines, 1))
                if not v.ok:
                    raise AuditError(f"Günlük doğrulanamadı, budama yapılmadı: {v.reason}")
                old_cp = v.checkpoint
                body = raw_lines[1:] if old_cp else raw_lines
                cut, last = 0, None
                for raw in body:
                    rec = _open_record(raw, self._cipher_key)
                    at = _parse_at(rec.get("at"))
                    if at is None or at >= older_than:
                        break
                    cut, last = cut + 1, rec
                if cut == 0 or last is None:
                    return PruneResult(0, v.count, False, old_cp)
                cp: dict[str, Any] = {
                    "v": VERSION,
                    "tur": CHECKPOINT_KIND,
                    "son_seq": int(last["seq"]),
                    "son_silinen_ozet": str(last["hash"]),
                    "silinen": cut + (int(old_cp["silinen"]) if old_cp else 0),
                    "budama_sayisi": 1 + (int(old_cp["budama_sayisi"]) if old_cp else 0),
                    "budama_zamani": now.astimezone().isoformat(timespec="seconds"),
                    "esik": older_than.astimezone().isoformat(timespec="seconds"),
                    "saklama_gun": days,
                }
                cp["hash"] = record_hash(cp)
                remaining = body[cut:]
                try:
                    with tmp.open("wb") as f:
                        f.write(_seal_record(cp, self._cipher_key).encode("utf-8"))
                        for raw in remaining:
                            f.write(raw if raw.endswith(b"\n") else raw + b"\n")
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(tmp, self.path)
                finally:
                    # Yarıda kalan geçici dosya bırakılmaz (eski günlük zaten yerinde).
                    tmp.unlink(missing_ok=True)
                _fsync_dir(self.path.parent)
                return PruneResult(cut, len(remaining), True, cp)
        except AuditError:
            raise
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise AuditError(f"Günlük budanamadı ({type(exc).__name__})") from None


def _local_date(at: str) -> str:
    try:
        return datetime.fromisoformat(at).astimezone().date().isoformat()
    except (TypeError, ValueError):
        return ""


def filter_records(
    records: list[dict[str, Any]],
    *,
    date_from: str | None = None,
    date_to: str | None = None,
    file: str | None = None,
    op: str | None = None,
    caller: str | None = None,
) -> list[dict[str, Any]]:
    """Tarih (YYYY-AA-GG, yerel saat, iki uç dahil), dosya (yolda geçen parça, büyük/küçük
    harf duyarsız), işlem ve çağırana göre süzer. Sıra korunur."""
    needle = (file or "").strip().casefold()
    out = []
    for r in records:
        day = _local_date(str(r.get("at", "")))
        if date_from and day < date_from:
            continue
        if date_to and day > date_to:
            continue
        if op and r.get("op") != op:
            continue
        if caller and r.get("caller") != caller:
            continue
        if needle:
            paths = f"{r.get('source') or ''}\n{r.get('target') or ''}".casefold()
            if needle not in paths:
                continue
        out.append(r)
    return out


# Elektronik tablonun formül olarak yorumlayacağı baş karakterler (CSV formül enjeksiyonu).
_CSV_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _csv_cell(v: Any) -> str:
    """Metin hücresi formül karakteriyle başlıyorsa başına tek tırnak koyar; sayılar değişmez."""
    if v is None:
        return ""
    if isinstance(v, str):
        return "'" + v if v.startswith(_CSV_FORMULA_START) else v
    return str(v)


def to_csv(records: list[dict[str, Any]]) -> str:
    """Excel'in Türkçe karakterleri doğru açması için BOM'lu UTF-8 ile yazılmalı (çağıran yazar).

    Kayıttaki metinler (ajan adı, profil adı, yol, hata) çağırandan gelebilir; formül olarak
    çalışmasınlar diye `=`, `+`, `-`, `@`, sekme ya da CR ile başlayan hücreler tek tırnakla yazılır.
    """
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(FIELDS)
    for r in records:
        row = []
        for k in FIELDS:
            v = r.get(k)
            if k == "counts":
                v = ", ".join(f"{t}={n}" for t, n in (v or {}).items())
            row.append(_csv_cell(v))
        w.writerow(row)
    return buf.getvalue()
