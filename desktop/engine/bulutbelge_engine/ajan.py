"""Ajan işlemleri: komut satırı (cli.py) ve yerel MCP sunucusu (mcp.py) aynı iç işlevleri kullanır.

Her işlev aynı izin denetimini (izinli klasör, yazma izni, kasa koşulu), aynı kural takımı üst sınırını
(K1) ve aynı işlem günlüğünü uygular. Çağıran (ajan adı) `journal.CALLER` ile verilir; çağıran tarafından
ayarlanmalıdır. Ajana hiçbir zaman orijinal değer dönmez: `scan` yalnızca sayılar, `read` maskeli metin,
`mask` yalnızca özet döndürür. Hatalar EngineError olarak yükselir (reddedilenler günlüğe yazılmış olarak).

Ayar klasörü (`BULUTBELGE_DATA_DIR`) çağırmadan önce ayarlanmış olmalıdır.
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from bulutbelge_core.rules import DATA_TYPES

from . import commands, journal, settings
from .protocol import EngineError

# Ajan adı işlem günlüğüne ve CSV dışa aktarımına girer: güvenli karakter kümesi (F15).
AGENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
AGENT_NAME_MAX = 60


def valid_agent_name(name: str) -> bool:
    return bool(AGENT_NAME.fullmatch(name))


def clean_agent_name(raw: Any, default: str = "ajan") -> str:
    """Dışarıdan gelen adı (ör. MCP istemcisinin `clientInfo.name`) aynı kurala uydurur.

    İzin verilmeyen karakterler tireye çevrilir, baştaki işaretler atılır, uzunluk sınırlanır.
    Geriye bir şey kalmazsa `default`.
    """
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(raw or "")).lstrip("._-")[:AGENT_NAME_MAX].rstrip("-")
    return text if valid_agent_name(text) else default


def label(type_key: str) -> str:
    return DATA_TYPES[type_key].label if type_key in DATA_TYPES else type_key


def folders() -> dict[str, Any]:
    cfg = settings.load_agent()
    return {"folders": cfg["folders"], "allow_write": cfg["allow_write"]}


def _profile(op: str, source: str, wanted: str | None, agent_cfg: dict[str, Any]) -> dict[str, Any]:
    """Ajanın kural takımı. Atanan takım üst sınırdır: daha gevşek bir takım seçilemez (K1)."""
    profile, looser = settings.agent_profile(wanted, agent_cfg)
    if looser:
        journal.refuse(
            op,
            "profile_not_allowed",
            f"'{profile['name']}' kural takımı, ajan için atanan takımdan gevşek ({'; '.join(looser)}). "
            "Ajan yalnızca atanan takımı ya da ondan sıkı bir takımı kullanabilir; atanan takımı "
            "BulutBelge › Ayarlar › Ajan erişimi bölümünde kullanıcı değiştirir.",
            source=source,
            profile=profile["name"],
        )
    return profile


def _prepare(op: str, path: str, wanted: str | None) -> tuple[dict[str, Any], str, dict[str, Any], dict[str, Any]]:
    """İzin denetimi: (ajan ayarı, kaynak yolu, kural takımı, motor kuralları). Reddedilen istek günlüğe girer."""
    if not isinstance(path, str) or not path.strip():
        raise EngineError("invalid_params", "Dosya yolu gerekli")
    agent_cfg = settings.load_agent()
    source = str(Path(path).absolute())
    profile = _profile(op, source, wanted, agent_cfg)
    folders_ = agent_cfg["folders"]

    def refuse(code: str, message: str) -> None:
        journal.refuse(op, code, message, source=source, profile=profile["name"])

    if not folders_:
        refuse("not_allowed", "Ajan için izinli klasör yok. BulutBelge › Ayarlar › Ajan erişimi bölümünden ekleyin.")
    if not settings.agent_allows(source, folders_):
        refuse("not_allowed", "Dosya izinli klasörlerin dışında")
    if settings.VAULT.path.exists() and not agent_cfg["allow_without_terms"]:
        # Özel ifadeler şifreli kasada; ajan kasayı açamaz. Kullanıcı açıkça izin vermedikçe
        # özel ifadeleri (kişi, müşteri adları) uygulamadan okuma yapılmaz.
        refuse(
            "terms_unavailable",
            "Özel ifade kasası var ama ajan komutu kasayı açamaz. Özel ifadeler olmadan çalışmasına "
            "Ayarlar › Ajan erişimi bölümünden izin verin.",
        )
    rules = {**profile, "terms": [], "profile_name": profile["name"]}
    return agent_cfg, source, profile, rules


def summary(op: str, source: str, profile: dict[str, Any], result: dict[str, Any], target: str | None) -> dict[str, Any]:
    counts = result.get("counts") or {}
    return {
        "islem": op,
        "kaynak": source,
        "hedef": target,
        "kural_takimi": profile["name"],
        "maskelenen": int(result.get("masked") or sum(counts.values())),
        "turler": {label(k): n for k, n in counts.items()},
        "uyarilar": list(result.get("warnings") or []),
        "not": result.get("changed"),
    }


def format_summary(summary: dict[str, Any]) -> str:
    """read/mask özetinin insan okunur hâli (CLI ve MCP aynı metni verir)."""
    lines = ["--- BulutBelge özeti ---", f"İşlem: {summary['islem']}", f"Kaynak: {summary['kaynak']}"]
    if summary["hedef"]:
        lines.append(f"Maskeli kopya: {summary['hedef']}")
    lines += [f"Kural takımı: {summary['kural_takimi']}", f"Maskelenen: {summary['maskelenen']}"]
    lines += [f"  - {name}: {n}" for name, n in summary["turler"].items()]
    if summary["not"]:
        lines.append(f"Not: {summary['not']}")
    lines += [f"Uyarı: {w}" for w in summary["uyarilar"]]
    return "\n".join(lines) + "\n"


def format_scan(summary: dict[str, Any]) -> str:
    """scan özetinin insan okunur hâli: yalnızca sayılar."""
    lines = [
        "--- BulutBelge tarama özeti ---",
        f"Kaynak: {summary['kaynak']}",
        f"Kural takımı: {summary['kural_takimi']}",
        f"Sayfa: {summary['sayfa']}",
        f"Bulunan: {summary['bulunan']}",
    ]
    lines += [f"  - {name}: {n}" for name, n in summary["turler"].items()]
    lines += [f"Uyarı: {w}" for w in summary["uyarilar"]]
    lines.append("Belge değiştirilmedi, değerler gösterilmez. Maskeli metin için: bulutbelge read")
    return "\n".join(lines) + "\n"


def scan(path: str, profile: str | None = None) -> dict[str, Any]:
    """Belgeyi değiştirmeden tarar; değer döndürmez: tür bazında bulgu sayıları, sayfa sayısı, uyarılar.

    Günlüğe "okuma" olarak girer (masaüstündeki tarama gibi).
    """
    _cfg, source, prof, rules = _prepare("okuma", path, profile)
    result = journal.run(
        "okuma",
        lambda: commands._doc_scan({"path": source, "rules": rules}),
        source=source,
        profile=prof["name"],
        counts_of=lambda r: journal.count_findings(r["findings"]),
    )
    counts = journal.count_findings(result["findings"])
    # Yalnızca sayılar dışarı çıkar: bulguların değeri, önizlemesi ve belge metni burada bırakılır.
    return {
        "islem": "tarama",
        "kaynak": source,
        "kural_takimi": prof["name"],
        "bulunan": sum(counts.values()),
        "turler": {label(k): n for k, n in counts.items()},
        "sayfa": int(result.get("pages") or 1),
        "uyarilar": [str(w) for w in result.get("warnings") or []],
    }


def read(path: str, profile: str | None = None) -> dict[str, Any]:
    """Belgenin maskeli metni ve özeti. Belge geçici kopyada maskelenir, metin o kopyadan çıkarılır."""
    from bulutbelge_core.readout import read_masked

    _cfg, source, prof, rules = _prepare("okuma", path, profile)

    @commands._user_errors
    def do_read(params: dict[str, Any]) -> dict[str, Any]:
        r = read_masked(source, commands._rules(params))
        return {"text": r.text, "format": r.format, "masked": r.masked, "counts": r.counts, "warnings": r.warnings}

    result = journal.run(
        "okuma",
        lambda: do_read({"rules": rules}),
        source=source,
        profile=prof["name"],
        counts_of=lambda r: r["counts"],
    )
    return {"text": result["text"], "summary": summary("okuma", source, prof, result, None)}


def mask(path: str, target: str | None = None, profile: str | None = None, agent: str | None = None) -> dict[str, Any]:
    """Maskeli kopyayı yeni dosyaya yazar (yazma izni gerekir); yalnızca özet döner."""
    from bulutbelge_core.pdf import default_target

    cfg, source, prof, rules = _prepare("maskeleme", path, profile)
    folders_ = cfg["folders"]
    if not cfg["allow_write"]:
        journal.refuse(
            "maskeleme",
            "write_not_allowed",
            "Ajanın maskeli kopya yazmasına izin verilmemiş (Ayarlar › Ajan erişimi)",
            source=source,
            profile=prof["name"],
        )
    dest = str(Path(target).absolute()) if target else default_target(source)
    if not settings.agent_allows(dest, folders_):
        journal.refuse("maskeleme", "not_allowed", "Hedef izinli klasörlerin dışında", source=source, profile=prof["name"])
    result = journal.run(
        "maskeleme",
        lambda: commands._doc_mask_checked({"source": source, "target": dest, "rules": rules}),
        source=source,
        profile=prof["name"],
        counts_of=lambda r: r.get("counts") or {},
        target_of=lambda r: r["target"],
    )
    if not settings.agent_allows(result["target"], folders_):
        # Çekirdek yolu değiştirdiyse (uzantı, var olan dosya) yine izinli klasörde olmalı.
        Path(result["target"]).unlink(missing_ok=True)
        raise EngineError("not_allowed", "Kopya izinli klasörün dışına düştü; silindi")
    _record_recent(source, prof, result, agent)
    return {"summary": summary("maskeleme", source, prof, result, result["target"])}


def _record_recent(source: str, profile: dict[str, Any], result: dict[str, Any], agent: str | None) -> None:
    """Ajanın yazdığı maskeli kopyayı arayüzdeki "Son yapılanlar" listesine ekler ("Ajan" etiketiyle).

    Yardımcı kayıttır: eklenemezse işlem başarısız sayılmaz (denetim kaydı işlem günlüğündedir).
    """
    try:
        counts = result.get("counts") or {}
        settings.history_add(
            {
                "entry": {
                    "path": source,
                    "target": result["target"],
                    "count": int(result.get("masked") or sum(counts.values())),
                    "at": int(time.time() * 1000),
                    "profileName": profile["name"],
                    "byType": [{"type": k, "label": label(k), "count": n} for k, n in counts.items()],
                    "agent": agent or "ajan",
                }
            }
        )
    except Exception:  # noqa: BLE001 - yardımcı kayıt
        pass
