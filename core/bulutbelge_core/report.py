"""Gizleme raporu (TAKIP 1.30, 1.44, 1.66): bir maskeleme işleminin yöntemini, tarihini,
gerekçesini ve dosya özetlerini anlatan, değer taşımayan kısa metin.

Rapora yalnızca (kişi adı gizlenmiş) dosya adı, SHA-256 özeti, tür bazında sayı, yöntem adı, profil ve gerekçe girer.
Bulgunun değeri, belge içeriği ve yol (klasör adları kişi adı taşıyabilir) girmez.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .dosya_adi import scrub_name
from .rules import PSEUDONYM, Rules

REPORT_SUFFIX = ".gizleme-raporu.txt"

_METHOD_LABELS = {
    "karartma": "karartma (siyah kutu; içerik silindi)",
    "etiket": "etiketle değiştirme (içerik silindi)",
    "bulanik": "bulanıklaştırma (içerik silindi)",
    "genel": "genelleştirme",
    "takma_ad": "takma ad (anonimleştirme değildir)",
}


_CLEANUP_COUNTS = (
    ("yazar", "yazar adı"),
    ("yorum", "yorum"),
    ("izlenen_silme", "izlenen silme (silinmiş metin kaldırıldı)"),
    ("izlenen_ekleme", "izlenen ekleme (yazar adı silindi)"),
    ("ek_dosya", "ekli dosya"),
    ("form_alani", "form alanı"),
)


def _cleanup_lines(cleanup: dict[str, Any]) -> list[str]:
    """Temizlik bölümü (TAKIP 1.67): yalnızca adet ve alan adı; ad, yorum metni ve değer yazılmaz."""
    lines = ["Temizlenen gizli bilgiler (adet ya da alan adı; değerler yazılmaz):"]
    for key, label in _CLEANUP_COUNTS:
        if cleanup.get(key):
            lines.append(f"- {label}: {cleanup[key]} adet")
    if cleanup.get("meta"):
        lines.append(f"- meta veri alanları: {', '.join(cleanup['meta'])}")
    if cleanup.get("xml_meta"):
        lines.append("- XML meta veri (XMP): var")
    if len(lines) == 1:
        lines.append("- (kaynakta temizlenecek gizli bilgi bulunmadı)")
    return lines


def _recognizability_lines(r: dict[str, Any]) -> list[str]:
    """Yeniden tanınabilirlik bölümü (TAKIP 1.70): yalnızca tür adı, adet ve puan; değer yazılmaz."""
    from .tanima import LABELS, WEIGHTS

    lines = [
        "Yeniden tanınabilirlik (maskeli kopyada kalan dolaylı tanımlayıcılar; yaklaşık tahmin, anonimleştirme güvencesi değildir):",
        f"- Puan: {r['puan']}/100, düzey: {r['duzey']}",
    ]
    for key, n in sorted(r.get("sayilar", {}).items()):
        lines.append(f"- {LABELS.get(key, key)}: {n} adet (katkı {r['katkilar'][key]}; ağırlık {WEIGHTS.get(key, '-')})")
    if r.get("sayilar"):
        lines.append(f"- Birleşim çarpanı: {r['carpan']:g} (birlikte bulunan her yeni tür etkiyi artırır)")
        if r["duzey"] in ("Orta", "Yüksek"):
            lines.append("- Paylaşmadan önce kalan il, yaş, tarih, meslek ve unvan bilgilerini elle gözden geçirin.")
    else:
        lines.append("- (kalan dolaylı tanımlayıcı bulunmadı)")
    return lines


def report_path(target: str | Path) -> Path:
    t = Path(target)
    return t.with_name(t.name + REPORT_SUFFIX)


def build_report(
    *,
    source: str | Path,
    source_sha256: str | None,
    target: str | Path,
    target_sha256: str | None,
    counts: dict[str, int],
    rules: Rules | None = None,
    purpose: str | None = None,
    profile: str | None = None,
    watermark: bool = False,
    special: dict[str, int] | None = None,
    cleanup: dict[str, Any] | None = None,
    recognizability: dict[str, Any] | None = None,
    at: str | None = None,
) -> str:
    when = at or datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "GİZLEME RAPORU",
        "",
        f"Tarih: {when}",
        f"Gerekçe (amaç): {purpose or 'belirtilmedi'}",
        f"Profil: {profile or '-'}",
        f"Kaynak dosya: {scrub_name(Path(source).name)}",  # ad kişi adı taşıyabilir; rapor kopyayla birlikte gidebilir
        f"Kaynak SHA-256: {source_sha256 or '-'}",
        f"Maskeli kopya: {scrub_name(Path(target).name)}",
        f"Kopya SHA-256: {target_sha256 or '-'}",
        f"Filigran (MASKELİ KOPYA): {'var' if watermark else 'yok'}",
        "",
        "Gizlenen bilgiler (tür, adet, yöntem):",
    ]
    used_pseudonym = False
    for type_key, n in sorted(counts.items()):
        method = ""
        spec = rules.types.get(type_key) if rules is not None else None
        if spec is not None:
            method = spec.method
            used_pseudonym = used_pseudonym or method == PSEUDONYM
        lines.append(f"- {type_key}: {n} adet, yöntem: {_METHOD_LABELS.get(method, method or '-')}")
    if not counts:
        lines.append("- (gizlenen bilgi yok)")
    if special:
        lines += ["", "Özel nitelikli veri uyarısı (KVKK m.6; bulgu değildir, maskelenmedi, elle kontrol edin):"]
        lines += [f"- {name}: {n} yerde ilgili sözcük geçiyor" for name, n in sorted(special.items())]
    if cleanup is not None:
        lines += ["", *_cleanup_lines(cleanup)]
    if recognizability is not None:
        lines += ["", *_recognizability_lines(recognizability)]
    lines += [
        "",
        "Gizlenen değerler bu rapora yazılmaz. Maskeleme gerçek silmedir; orijinal içerik kopyada bulunmaz.",
    ]
    if used_pseudonym:
        lines.append("Takma ad anonimleştirme değildir: aynı kişi aynı takma adla anılır, bağlantı kurulabilir.")
    return "\n".join(lines) + "\n"


def write_report(path: str | Path, **kwargs: Any) -> str:
    p = Path(path)
    p.write_text(build_report(**kwargs), encoding="utf-8", newline="\n")
    return str(p)
