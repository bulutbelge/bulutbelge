"""Kalıcı ayarlar: kural profilleri ve parolayla şifreli özel ifade kasası.

- `settings.json` profilleri (veri türleri, yöntemler, kalıplar, beyaz liste,
  imza etiketleri) düz metin tutar; kişisel veri içermez.
- `terms.bbvault` özel ifadeleri (kişi, müşteri, proje adları) AES-256-GCM ile
  şifreli tutar. Anahtar paroladan scrypt ile türetilir; parola ve anahtar
  diske yazılmaz, anahtar yalnızca kasa açıkken motor belleğinde durur.

Bkz. docs/kararlar/2026-11-04-ozel-ifade-sifreli-saklama.md
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import sqlite3
import tempfile
import time
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from bulutbelge_core.dosya_adi import scrub_path
from bulutbelge_core.allowlist import AllowMatcher, value_hash
from bulutbelge_core.profiles import BUILTIN_PURPOSES, DEFAULT_PROFILE_ID, builtin_profiles, default_profile  # noqa: F401
from bulutbelge_core.pseudonym import Pseudonyms, clean_table, restore_text
from bulutbelge_core.rules import DATA_TYPES, RuleError, Rules

from .protocol import EngineError

SETTINGS_FILE = "settings.json"
VAULT_FILE = "terms.bbvault"
MIN_PASSWORD = 8

_SCRYPT = {"n": 2**15, "r": 8, "p": 1}
_AAD = b"bulutbelge-terms-v1"


def data_dir() -> Path:
    raw = os.environ.get("BULUTBELGE_DATA_DIR")
    if not raw:
        raise EngineError("no_data_dir", "Ayar klasörü bilinmiyor")
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write_atomic(path: Path, data: bytes) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# ---------- Profiller ----------

# Varsayılan ve hazır "Kime gidecek?" takımları çekirdekte: bulutbelge_core.profiles


def _clean_profile(p: Any) -> dict[str, Any]:
    if not isinstance(p, dict):
        raise EngineError("invalid_settings", "Profil nesne olmalı")
    pid = str(p.get("id") or "").strip()
    name = str(p.get("name") or "").strip()
    if not pid or not name:
        raise EngineError("invalid_settings", "Profilin kimliği ve adı olmalı")
    base = default_profile()
    profile = {
        "id": pid,
        "name": name[:60],
        "types": {**base["types"], **(p.get("types") or {})},
        "patterns": [
            {"name": str(x.get("name") or ""), "pattern": str(x.get("pattern") or "")}
            for x in (p.get("patterns") or [])
            if isinstance(x, dict) and x.get("pattern")
        ],
        "whitelist": [str(x) for x in (p.get("whitelist") or [])],
        "institutions": [str(x) for x in (p.get("institutions") or [])],
        "signature_labels": [str(x) for x in (p.get("signature_labels") or base["signature_labels"])],
    }
    if p.get("pseudonym_scope") == "belge":
        profile["pseudonym_scope"] = "belge"  # varsayılan (ortak) yazılmaz
    if p.get("varsayilan_sutun_sozlugu") is False:
        profile["varsayilan_sutun_sozlugu"] = False  # varsayılan (açık) yazılmaz
    if p.get("column_rules"):
        profile["column_rules"] = [
            {"header": str(x.get("header") or ""), "type": str(x.get("type") or "")}
            if not x.get("action")
            else {"header": str(x.get("header") or ""), "action": str(x["action"])}
            for x in p["column_rules"]
            if isinstance(x, dict) and str(x.get("header") or "").strip() and (x.get("type") or x.get("action"))
        ]  # boş satırlar (arayüzde yeni eklenip doldurulmamış) atılır
    profile["types"] = {k: v for k, v in profile["types"].items() if k in DATA_TYPES}
    try:
        Rules.from_dict(profile)  # yöntem ve kalıp doğrulaması
    except RuleError as exc:
        raise EngineError("invalid_rules", f"{name}: {exc}") from None
    return profile


def load_settings() -> dict[str, Any]:
    path = data_dir() / SETTINGS_FILE
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}  # bozuk dosya: varsayılana dön, kaydedince düzelir
    profiles = []
    for p in data.get("profiles") or []:
        try:
            profiles.append(_clean_profile(p))
        except EngineError:
            continue
    if not any(p["id"] == DEFAULT_PROFILE_ID for p in profiles):
        profiles.insert(0, default_profile())
    active = data.get("active")
    known_builtins = set(data.get("seeded_builtins") or [])
    if not data.get("seeded"):
        # Hazır amaç profilleri (Müşteriye, Denetçiye, Kurum içine, e-Fatura) bir kez eklenir.
        ids = {p["id"] for p in profiles}
        profiles.extend(p for p in builtin_profiles() if p["id"] not in ids)
        if not path.exists():
            active = "musteri"  # ilk açılış: "Bu belgeyi Müşteriye göndereceğim"
    else:
        # Mevcut kurulumlara sonradan eklenen yeni hazır profiller (ör. efatura) bir kez eklenir.
        if not known_builtins:
            known_builtins = {"musteri", "denetci", "kurum_ici"}
        ids = {p["id"] for p in profiles}
        profiles.extend(p for p in builtin_profiles() if p["id"] not in ids and p["id"] not in known_builtins)
    if not any(p["id"] == active for p in profiles):
        active = DEFAULT_PROFILE_ID
    return {"profiles": profiles, "active": active}


def save_settings(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("profiles")
    if not isinstance(raw, list) or not raw:
        raise EngineError("invalid_settings", "En az bir profil olmalı")
    profiles = [_clean_profile(p) for p in raw]
    ids = [p["id"] for p in profiles]
    if len(set(ids)) != len(ids):
        raise EngineError("invalid_settings", "Profil kimlikleri tekrarlanıyor")
    if DEFAULT_PROFILE_ID not in ids:
        raise EngineError("invalid_settings", "Varsayılan profil silinemez")
    active = params.get("active") if params.get("active") in ids else DEFAULT_PROFILE_ID
    # "seeded" + "seeded_builtins": hazır profiller eklendi; kullanıcı silerse bir daha eklenmez.
    data = {
        "version": 1,
        "active": active,
        "profiles": profiles,
        "seeded": True,
        "seeded_builtins": [pid for pid, _, _ in BUILTIN_PURPOSES],
    }
    _write_atomic(data_dir() / SETTINGS_FILE, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return {"profiles": profiles, "active": active}


# ---------- Profil dışa/içe aktarma ----------

PROFILE_PACK_KIND = "bulutbelge-profiller"
PROFILE_PACK_VERSION = 1
_MAX_PACK_PROFILES = 50


def export_profiles(params: dict[str, Any]) -> dict[str, Any]:
    """Seçilen profilleri (yoksa hepsini) paylaşılabilir JSON nesnesi olarak verir.

    Şifreli özel ifadeler (kasa) ve profildeki beyaz liste değerleri pakete girmez;
    yalnızca türler, yöntemler, özel kalıplar ve imza etiketleri çıkar.
    """
    wanted = params.get("ids")
    if wanted is not None and not isinstance(wanted, list):
        raise EngineError("invalid_settings", "Profil listesi dizi olmalı")
    profiles = load_settings()["profiles"]
    if wanted is not None:
        ids = {str(x) for x in wanted}
        profiles = [p for p in profiles if p["id"] in ids]
    if not profiles:
        raise EngineError("invalid_settings", "Dışa aktarılacak profil yok")
    out = [{k: v for k, v in p.items() if k != "whitelist"} for p in profiles]
    pack = {"kind": PROFILE_PACK_KIND, "version": PROFILE_PACK_VERSION, "profiles": out}
    target = params.get("target")
    if target is None:
        return pack
    if not isinstance(target, str) or not target:
        raise EngineError("invalid_params", "'target' metin olmalı")
    dest = Path(target)
    if dest.suffix.lower() != ".json":
        dest = dest.with_suffix(".json")
    if dest.resolve().parent == data_dir().resolve():
        raise EngineError("invalid_params", "Dışa aktarma ayar klasörüne yazılamaz")
    if not dest.parent.is_dir():
        raise EngineError("document", "Hedef klasör bulunamadı")
    dest.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"target": str(dest), "count": len(out)}


def import_profiles(params: dict[str, Any]) -> dict[str, Any]:
    """Profil paketini mevcut ayarlara ekler; var olan hiçbir profilin üzerine yazılmaz.

    Kimliği çakışan profil yeni kimlik ve " (içe aktarılan)" ekiyle eklenir. Paketteki
    `terms`, `whitelist` gibi fazladan alanlar yok sayılır. Etkin profil değişmez.
    """
    data = params.get("data")
    source = params.get("source")
    if source is not None:
        if not isinstance(source, str) or not source:
            raise EngineError("invalid_params", "'source' metin olmalı")
        src = Path(source)
        if not src.is_file():
            raise EngineError("document", "Dosya bulunamadı")
        if src.stat().st_size > 5 * 1024 * 1024:
            raise EngineError("invalid_pack", "Profil paketi çok büyük")
        try:
            data = src.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            raise EngineError("invalid_pack", "Dosya geçerli bir JSON değil") from None
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except json.JSONDecodeError:
            raise EngineError("invalid_pack", "Dosya geçerli bir JSON değil") from None
    if not isinstance(data, dict) or data.get("kind") != PROFILE_PACK_KIND:
        raise EngineError("invalid_pack", "Bu bir BulutBelge profil paketi değil")
    if data.get("version") != PROFILE_PACK_VERSION:
        raise EngineError("invalid_pack", "Profil paketinin sürümü desteklenmiyor")
    raw = data.get("profiles")
    if not isinstance(raw, list) or not raw or len(raw) > _MAX_PACK_PROFILES:
        raise EngineError("invalid_pack", "Pakette geçerli profil yok")
    current = load_settings()
    taken = {p["id"] for p in current["profiles"]}
    added = []
    for item in raw:
        if not isinstance(item, dict):
            raise EngineError("invalid_pack", "Profil nesne olmalı")
        item = {**item, "whitelist": []}
        cleaned = _clean_profile(item)  # yöntem ve kalıp doğrulaması burada
        base, n = cleaned["id"], 1
        if base in taken:
            cleaned["name"] = f"{cleaned['name'][:40]} (içe aktarılan)"
            while f"{base}_{n}" in taken:
                n += 1
            cleaned["id"] = f"{base}_{n}"
        taken.add(cleaned["id"])
        added.append(cleaned)
    saved = save_settings({"profiles": [*current["profiles"], *added], "active": current["active"]})
    return {**saved, "imported": [p["id"] for p in added]}


# ---------- Şifreli özel ifade kasası ----------


def _b64(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _unb64(s: str) -> bytes:
    return base64.b64decode(s.encode("ascii"))


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=128 * 1024 * 1024, dklen=32)


def _clean_terms(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raise EngineError("invalid_params", "'terms' nesne olmalı")
    out: dict[str, list[str]] = {}
    for pid, values in raw.items():
        if not isinstance(values, list):
            continue
        seen: list[str] = []
        for v in values:
            s = str(v).strip()
            if s and s not in seen:
                seen.append(s)
        out[str(pid)] = seen
    return out


class Vault:
    """Motor süreci boyunca yaşayan kasa durumu.

    Kasada iki şey saklanır: profillerin özel ifadeleri ve takma ad eşleme tablosu
    (bkz. bulutbelge_core.pseudonym). Takma ad tablosu kasadan dışarı çıkmaz; arayüze
    yalnızca sayılar ve kullanıcının tek tek sorduğu takma adların karşılığı döner.
    """

    def __init__(self) -> None:
        self._key: bytes | None = None
        self._salt: bytes | None = None
        self._terms: dict[str, list[str]] = {}
        self._pseudonyms: dict[str, Any] = {}

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    @property
    def pseudonyms(self) -> dict[str, Any]:
        return self._pseudonyms

    @property
    def path(self) -> Path:
        return data_dir() / VAULT_FILE

    def status(self) -> dict[str, bool]:
        return {"exists": self.path.exists(), "unlocked": self._key is not None}

    def _write(self) -> None:
        assert self._key is not None and self._salt is not None
        nonce = secrets.token_bytes(12)
        plain = json.dumps({"terms": self._terms, "pseudonyms": self._pseudonyms}, ensure_ascii=False).encode("utf-8")
        ct = AESGCM(self._key).encrypt(nonce, plain, _AAD)
        doc = {
            "format": "bbvault",
            "version": 1,
            "kdf": {"name": "scrypt", **_SCRYPT, "salt": _b64(self._salt)},
            "cipher": "AES-256-GCM",
            "nonce": _b64(nonce),
            "data": _b64(ct),
        }
        _write_atomic(self.path, json.dumps(doc).encode("utf-8"))

    def create(self, password: str) -> dict[str, Any]:
        if self.path.exists():
            raise EngineError("vault_exists", "Kasa zaten var")
        _check_password(password)
        self._salt = secrets.token_bytes(16)
        self._key = _derive(password, self._salt, **_SCRYPT)
        self._terms = {}
        self._pseudonyms = {}
        self._write()
        return {"terms": self._terms}

    def unlock(self, password: str) -> dict[str, Any]:
        try:
            doc = json.loads(self.path.read_text(encoding="utf-8"))
            kdf = doc["kdf"]
            salt = _unb64(kdf["salt"])
            key = _derive(password, salt, kdf["n"], kdf["r"], kdf["p"])
            plain = AESGCM(key).decrypt(_unb64(doc["nonce"]), _unb64(doc["data"]), _AAD)
        except FileNotFoundError:
            raise EngineError("no_vault", "Kasa yok") from None
        except InvalidTag:
            raise EngineError("wrong_password", "Parola yanlış") from None
        except (KeyError, ValueError, TypeError):
            raise EngineError("vault_corrupt", "Kasa dosyası okunamadı") from None
        self._key, self._salt = key, salt
        data = json.loads(plain)
        self._terms = _clean_terms(data.get("terms") or {})
        self._pseudonyms = clean_table(data.get("pseudonyms"))
        return {"terms": self._terms}

    def save(self, terms: Any) -> dict[str, Any]:
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        self._terms = _clean_terms(terms)
        self._write()
        return {"terms": self._terms}

    def save_pseudonyms(self, table: dict[str, Any]) -> None:
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        self._pseudonyms = clean_table(table)
        self._write()

    def pseudonym_stats(self) -> dict[str, Any]:
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        return {"counts": Pseudonyms(self._pseudonyms).stats()}

    def pseudonym_lookup(self, label: Any) -> dict[str, Any]:
        """Takma adın gerçek değerini döndürür (maske kaldırma: kullanıcının açık isteğiyle)."""
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        if not isinstance(label, str) or not label.strip():
            raise EngineError("invalid_params", "Takma ad yazın, ör. Kişi-3")
        found = Pseudonyms(self._pseudonyms).lookup(label)
        if found is None:
            raise EngineError("not_found", "Bu takma ad kasada yok")
        return found

    def pseudonym_restore_text(self, text: Any) -> dict[str, Any]:
        """Yapıştırılan metindeki takma adları geri çevirir. Sonuç yalnızca çağırana döner, saklanmaz."""
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        if not isinstance(text, str) or not text.strip():
            raise EngineError("invalid_params", "Geri çevrilecek metni yapıştırın")
        out, count = restore_text(text, Pseudonyms(self._pseudonyms))
        return {"text": out, "count": count}

    def pseudonym_clear(self) -> dict[str, Any]:
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        self._pseudonyms = {}
        self._write()
        return {"counts": {}}

    def change_password(self, password: str) -> dict[str, bool]:
        if self._key is None:
            raise EngineError("vault_locked", "Kasa kilitli")
        _check_password(password)
        self._salt = secrets.token_bytes(16)
        self._key = _derive(password, self._salt, **_SCRYPT)
        self._write()
        return self.status()

    def lock(self) -> dict[str, bool]:
        self._key = self._salt = None
        self._terms = {}
        self._pseudonyms = {}
        return self.status()

    def delete(self) -> dict[str, bool]:
        self.lock()
        self.path.unlink(missing_ok=True)
        return self.status()


def _check_password(password: Any) -> None:
    if not isinstance(password, str) or len(password) < MIN_PASSWORD:
        raise EngineError("weak_password", f"Parola en az {MIN_PASSWORD} karakter olmalı")


# ---------- Öğrenilen istisnalar ("Bunu bir daha hiç gizleme") ----------

ALLOW_FILE = "istisnalar.json"
MAX_ALLOW = 500


def _load_allow() -> dict[str, Any]:
    path = data_dir() / ALLOW_FILE
    data: dict[str, Any] = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
    salt = data.get("salt")
    items = [x for x in data.get("items") or [] if isinstance(x, dict) and isinstance(x.get("h"), str)]
    if not isinstance(salt, str):
        salt, items = _b64(secrets.token_bytes(16)), []
    return {"salt": salt, "items": items}


def _save_allow(data: dict[str, Any]) -> None:
    _write_atomic(data_dir() / ALLOW_FILE, json.dumps({"version": 1, **data}, ensure_ascii=False, indent=2).encode("utf-8"))


def allow_matcher() -> AllowMatcher | None:
    if not os.environ.get("BULUTBELGE_DATA_DIR"):
        return None  # ayar klasörü yok (testler, komut satırı): istisna da yok
    data = _load_allow()
    if not data["items"]:
        return None
    return AllowMatcher({x["h"] for x in data["items"]}, _unb64(data["salt"]))


def _allow_public(data: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for x in data["items"]:
        dt = DATA_TYPES.get(str(x.get("type")))
        out.append({"id": x["h"][:16], "type": x.get("type"), "type_label": dt.label if dt else "Bilgi", "at": x.get("at")})
    return out


def allow_add(values: Any, type_key: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not values:
        raise EngineError("invalid_params", "'values' liste olmalı")
    data = _load_allow()
    salt = _unb64(data["salt"])
    known = {x["h"] for x in data["items"]}
    now = int(time.time())
    for v in values:
        if not isinstance(v, str) or not v.strip():
            continue
        h = value_hash(v, salt)
        if h not in known:
            data["items"].append({"h": h, "type": str(type_key or ""), "at": now})
            known.add(h)
    data["items"] = data["items"][-MAX_ALLOW:]
    _save_allow(data)
    return _allow_public(data)


def allow_list() -> list[dict[str, Any]]:
    return _allow_public(_load_allow())


def allow_remove(item_id: Any) -> list[dict[str, Any]]:
    data = _load_allow()
    if item_id == "*":
        data["items"] = []
    else:
        data["items"] = [x for x in data["items"] if x["h"][:16] != item_id]
    _save_allow(data)
    return _allow_public(data)


# ---------- Son Yapılanlar Geçmiş Veritabanı (SQLite) ----------

HISTORY_DB_FILE = "history.db"
MAX_HISTORY = 50


def _history_conn() -> sqlite3.Connection:
    db_path = data_dir() / HISTORY_DB_FILE
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS recent_history (
            target TEXT PRIMARY KEY,
            path TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            at INTEGER NOT NULL DEFAULT 0,
            profile_name TEXT,
            dropped_pages INTEGER NOT NULL DEFAULT 0,
            encrypted INTEGER NOT NULL DEFAULT 0,
            by_type_json TEXT,
            folder_name TEXT,
            folder_root TEXT,
            agent TEXT
        )
        """
    )
    try:
        conn.execute("ALTER TABLE recent_history ADD COLUMN agent TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE recent_history ADD COLUMN folder_name TEXT")
    except Exception:
        pass
    try:
        conn.execute("ALTER TABLE recent_history ADD COLUMN folder_root TEXT")
    except Exception:
        pass
    # Mevcut kayıtlarda folder_name boş olanları target yolundaki _maskeli klasöründen otomatik güncelle
    try:
        rows = conn.execute("SELECT target, path FROM recent_history WHERE folder_name IS NULL").fetchall()
        for r in rows:
            tgt = str(r["target"]).replace("\\", "/")
            parts = [p for p in tgt.split("/") if p]
            inferred = None
            inferred_root = None
            for i, p in enumerate(parts[:-1]):
                if "_maskeli" in p:
                    inferred = p
                    inferred_root = ("/" if r["target"].startswith("/") else "") + "/".join(parts[: i + 1])
                    break
            if inferred:
                conn.execute(
                    "UPDATE recent_history SET folder_name = ?, folder_root = ? WHERE target = ?",
                    (inferred, inferred_root, r["target"]),
                )
        conn.commit()
    except Exception:
        pass
    _scrub_existing_history(conn)
    return conn


def _scrub_existing_history(conn: sqlite3.Connection) -> None:
    """Eski kayıtlardaki yol ve klasör adlarından kişi adlarını temizler."""
    try:
        for r in conn.execute("SELECT * FROM recent_history").fetchall():
            new = {k: scrub_path(r[k]) if r[k] else r[k] for k in ("target", "path", "folder_name", "folder_root")}
            if all(new[k] == r[k] for k in new):
                continue
            conn.execute("DELETE FROM recent_history WHERE target = ?", (r["target"],))
            conn.execute(
                """
                INSERT OR REPLACE INTO recent_history
                (target, path, count, at, profile_name, dropped_pages, encrypted, by_type_json, folder_name, folder_root, agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    new["target"], new["path"], r["count"], r["at"], r["profile_name"], r["dropped_pages"],
                    r["encrypted"], r["by_type_json"], new["folder_name"], new["folder_root"], r["agent"],
                ),
            )
        conn.commit()
    except Exception:
        pass


def _row_to_recent(row: sqlite3.Row) -> dict[str, Any]:
    by_type: list[dict[str, Any]] = []
    raw_by_type = row["by_type_json"]
    if raw_by_type:
        try:
            parsed = json.loads(raw_by_type)
            if isinstance(parsed, list):
                by_type = parsed
        except json.JSONDecodeError:
            by_type = []
    item: dict[str, Any] = {
        "path": row["path"],
        "target": row["target"],
        "count": int(row["count"]),
        "at": int(row["at"]),
    }
    if row["profile_name"]:
        item["profileName"] = row["profile_name"]
    if row["dropped_pages"]:
        item["droppedPages"] = int(row["dropped_pages"])
    if row["encrypted"]:
        item["encrypted"] = bool(row["encrypted"])
    if by_type:
        item["byType"] = by_type
    try:
        if row["folder_name"]:
            item["folderName"] = row["folder_name"]
    except Exception:
        pass
    try:
        if row["folder_root"]:
            item["folderRoot"] = row["folder_root"]
    except Exception:
        pass
    try:
        if row["agent"]:
            item["agent"] = row["agent"]
    except Exception:
        pass
    return item


def history_list() -> list[dict[str, Any]]:
    with _history_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM recent_history ORDER BY at DESC LIMIT ?",
            (MAX_HISTORY,),
        ).fetchall()
    return [_row_to_recent(r) for r in rows]


def _clean_history_entry(
    raw: Any,
) -> tuple[str, str, int, int, str | None, int, int, str | None, str | None, str | None, str | None] | None:
    if not isinstance(raw, dict):
        return None
    # Dosya adı ve yoldaki kişi adları veritabanına yazılmaz.
    target = scrub_path(str(raw.get("target") or "").strip())
    path = scrub_path(str(raw.get("path") or "").strip())
    if not target or not path:
        return None
    try:
        count = int(raw.get("count") or 0)
    except (TypeError, ValueError):
        count = 0
    try:
        at = int(raw.get("at") or int(time.time() * 1000))
    except (TypeError, ValueError):
        at = int(time.time() * 1000)
    profile_name = str(raw["profileName"]).strip()[:80] if raw.get("profileName") else None
    try:
        dropped_pages = int(raw.get("droppedPages") or 0)
    except (TypeError, ValueError):
        dropped_pages = 0
    encrypted = 1 if raw.get("encrypted") else 0
    by_type_raw = raw.get("byType")
    by_type_clean: list[dict[str, Any]] = []
    if isinstance(by_type_raw, list):
        for b in by_type_raw:
            if isinstance(b, dict) and b.get("type") and b.get("label"):
                entry_b: dict[str, Any] = {
                    "type": str(b["type"]),
                    "label": str(b["label"]),
                    "count": int(b.get("count") or 0),
                }
                if b.get("methodLabel"):
                    entry_b["methodLabel"] = str(b["methodLabel"])
                by_type_clean.append(entry_b)
    by_type_json = json.dumps(by_type_clean, ensure_ascii=False) if by_type_clean else None
    folder_name = scrub_path(str(raw["folderName"]).strip()[:120]) if raw.get("folderName") else None
    folder_root = scrub_path(str(raw["folderRoot"]).strip()) if raw.get("folderRoot") else None
    # Ajan komutuyla yapılan işlemde ajanın adı (arayüzde "Ajan" etiketi); kullanıcı işleminde boş.
    agent = str(raw["agent"]).strip()[:60] if raw.get("agent") else None
    return (target, path, count, at, profile_name, dropped_pages, encrypted, by_type_json, folder_name, folder_root, agent)


def history_add(params: dict[str, Any]) -> list[dict[str, Any]]:
    raw_entries: list[Any] = []
    if isinstance(params.get("entries"), list):
        raw_entries.extend(params["entries"])
    elif isinstance(params.get("entry"), dict):
        raw_entries.append(params["entry"])
    else:
        raw_entries.append(params)

    cleaned = [c for e in raw_entries if (c := _clean_history_entry(e)) is not None]
    if cleaned:
        with _history_conn() as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO recent_history
                (target, path, count, at, profile_name, dropped_pages, encrypted, by_type_json, folder_name, folder_root, agent)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                cleaned,
            )
            conn.execute(
                """
                DELETE FROM recent_history
                WHERE target NOT IN (
                    SELECT target FROM recent_history ORDER BY at DESC LIMIT ?
                )
                """,
                (MAX_HISTORY,),
            )
            conn.commit()
    return history_list()


def history_delete(params: Any) -> list[dict[str, Any]]:
    targets: list[str] = []
    if isinstance(params, dict):
        if "targets" in params and isinstance(params["targets"], list):
            targets = [scrub_path(str(x).strip()) for x in params["targets"] if str(x).strip()]
        elif "target" in params:
            t = str(params["target"] or "").strip()
            if t:
                targets = [scrub_path(t)]
    elif isinstance(params, list):
        targets = [scrub_path(str(x).strip()) for x in params if str(x).strip()]
    elif isinstance(params, str):
        t = str(params or "").strip()
        if t:
            targets = [scrub_path(t)]

    if targets:
        with _history_conn() as conn:
            conn.executemany("DELETE FROM recent_history WHERE target = ?", [(t,) for t in targets])
            conn.commit()
    return history_list()


def history_clear() -> list[dict[str, Any]]:
    with _history_conn() as conn:
        conn.execute("DELETE FROM recent_history")
        conn.commit()
    return []

# ---------- Ajan erişimi (komut satırı) ----------

AGENT_FILE = "ajan.json"
MAX_AGENT_FOLDERS = 20


def _agent_defaults() -> dict[str, Any]:
    # Varsayılan: hiçbir klasör izinli değil, yazma kapalı. Ajan ancak kullanıcı izin verince çalışır.
    return {"folders": [], "allow_write": False, "allow_without_terms": False, "profile": None}


def _clean_folder(raw: Any) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise EngineError("invalid_settings", "Klasör yolu boş olamaz")
    p = Path(raw.strip())
    if not p.is_absolute():
        raise EngineError("invalid_settings", f"Klasör tam yol olmalı: {raw}")
    try:
        p = p.resolve(strict=True)
    except OSError:
        raise EngineError("invalid_settings", f"Klasör bulunamadı: {raw}") from None
    if not p.is_dir():
        raise EngineError("invalid_settings", f"Klasör değil: {raw}")
    if p.parent == p:
        raise EngineError("invalid_settings", "Sürücünün tamamına izin verilemez; bir klasör seçin")
    if p == Path.home().resolve():
        raise EngineError("invalid_settings", "Kullanıcı klasörünün tamamına izin verilemez; bir alt klasör seçin")
    data = data_dir().resolve()
    if p == data or p.is_relative_to(data) or data.is_relative_to(p):
        raise EngineError("invalid_settings", "Uygulamanın ayar klasörü (ve onu içeren klasör) izinli olamaz")
    return str(p)


def load_agent() -> dict[str, Any]:
    path = data_dir() / AGENT_FILE
    out = _agent_defaults()
    if path.exists():
        try:
            # utf-8-sig: Windows PowerShell 5.1 / eski Not Defteri ile düzenlenen dosya BOM'la başlar; BOM yüzünden
            # izinler sessizce "yok" sayılıyordu (1.55 paketli denemesi). Bozuk JSON yine izin vermez.
            data = json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return out  # bozuk dosya: hiçbir izin yok (şüphede reddet)
        out["folders"] = [str(x) for x in data.get("folders") or [] if isinstance(x, str)][:MAX_AGENT_FOLDERS]
        out["allow_write"] = data.get("allow_write") is True
        out["allow_without_terms"] = data.get("allow_without_terms") is True
        out["profile"] = data.get("profile") if isinstance(data.get("profile"), str) else None
    return out


def save_agent(params: dict[str, Any]) -> dict[str, Any]:
    raw = params.get("folders") or []
    if not isinstance(raw, list):
        raise EngineError("invalid_settings", "'folders' liste olmalı")
    folders: list[str] = []
    saved = set(load_agent()["folders"])
    for f in raw:
        if isinstance(f, str) and f.strip() in saved and not Path(f.strip()).exists():
            # Daha önce izin verilmiş ama sonradan silinmiş klasör listeden düşer. Yoksa her kayıt
            # "Klasör bulunamadı" ile durur ve ne o klasör kaldırılabilir ne yenisi eklenebilir (24 Kasım).
            continue
        c = _clean_folder(f)
        if c not in folders:
            folders.append(c)
    if len(folders) > MAX_AGENT_FOLDERS:
        raise EngineError("invalid_settings", f"En fazla {MAX_AGENT_FOLDERS} klasör")
    profile = params.get("profile")
    if profile is not None and not any(p["id"] == profile for p in load_settings()["profiles"]):
        raise EngineError("invalid_settings", "Kural takımı bulunamadı")
    data = {
        "version": 1,
        "folders": folders,
        "allow_write": params.get("allow_write") is True,
        "allow_without_terms": params.get("allow_without_terms") is True,
        "profile": profile,
    }
    _write_atomic(data_dir() / AGENT_FILE, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
    return load_agent()


def looser_than(wanted: dict[str, Any], ceiling: dict[str, Any]) -> list[str]:
    """`wanted` kural takımı `ceiling`den hangi yönlerden gevşek (boşsa en az onun kadar sıkı).

    Ajan için atanan takım üst sınırdır (K1): ceiling'de açık her veri türü wanted'da da açık olmalı
    (yöntem farklı olabilir). Ayrıca ceiling'in açık özel kalıpları, sütun kuralları ve imza etiketleri
    wanted'da da bulunmalı; wanted'ın beyaz listesi ve kurum sözlüğü ceiling'inkinden geniş olmamalı
    (ikisi de bulguları maskelemeden bırakır). Dönen metinler değer içermez: tür adı ve sayı.
    """
    try:
        w, c = Rules.from_dict(wanted), Rules.from_dict(ceiling)
    except RuleError:
        return ["kural takımı okunamadı"]
    out = [DATA_TYPES[k].label for k, r in c.types.items() if r.enabled and not w.types[k].enabled]
    patterns = {p.pattern for p in w.patterns if p.enabled}
    missing = sum(1 for p in c.patterns if p.enabled and p.pattern not in patterns)
    if missing:
        out.append(f"{missing} özel kalıp yok")
    if not set(w.whitelist) <= set(c.whitelist):
        out.append("beyaz liste daha geniş")
    if not set(w.institutions) <= set(c.institutions):
        out.append("kurum sözlüğü daha geniş")
    if any(w.column_rules.get(h) != t for h, t in c.column_rules.items()) or any(
        w.column_actions.get(h) != a for h, a in c.column_actions.items()
    ):
        out.append("sütun kuralları eksik")
    if c.types["imza"].enabled and not set(c.signature_labels) <= set(w.signature_labels):
        out.append("imza etiketleri eksik")
    return out


def agent_profile(wanted: str | None, agent_cfg: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Ajan çağrısının kural takımı ve (varsa) atanan takımdan gevşek olduğu yönler.

    Atanan takım (yoksa etkin takım) üst sınırdır; `wanted` yalnızca en az onun kadar sıkı bir takım
    seçebilir. Bilinmeyen takım EngineError("invalid_params").
    """
    s = load_settings()
    by_id = {p["id"]: p for p in s["profiles"]}
    ceiling_id = agent_cfg.get("profile") or s["active"]
    pid = wanted or ceiling_id
    if pid not in by_id:
        raise EngineError("invalid_params", f"Kural takımı bulunamadı: {pid}")
    if ceiling_id not in by_id:
        # Atanan takım silinmiş: hangi takımın üst sınır olduğu bilinmiyor (şüphede reddet).
        raise EngineError("invalid_params", f"Ajan için atanan kural takımı bulunamadı: {ceiling_id}")
    if pid == ceiling_id:
        return by_id[pid], []
    return by_id[pid], looser_than(by_id[pid], by_id[ceiling_id])


def agent_allows(path: str | os.PathLike, folders: list[str]) -> bool:
    """Yol (sembolik bağlar çözülerek) izinli klasörlerden birinin içinde mi."""
    try:
        p = Path(path).resolve()
    except OSError:
        return False
    for f in folders:
        try:
            base = Path(f).resolve(strict=True)
        except OSError:
            continue
        if p != base and p.is_relative_to(base):
            return True
    return False


VAULT = Vault()
