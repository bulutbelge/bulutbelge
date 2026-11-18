"""Çok belge bağlanabilirlik uyarısı (TAKIP 1.71).

Aynı işte birden fazla belge maskelenip birlikte gönderilirse, belgelerde ORTAK kalan
dolaylı tanımlayıcılar (aynı il, tarih, meslek, unvan+kurum, yaş) ve aynı takma ad
(ör. "Kişi-3") belgeleri birbirine bağlar; bağlanan belgeler tek tek zararsız olsa da
birlikte kişiyi ele verebilir. Takma ad anonimleştirme değildir.

Eşleşen değerler yalnızca bellekte, özetlenmiş (SHA-256) olarak karşılaştırılır; sonuçta
yalnızca tür adı, ortak değer sayısı ve kaç belgede geçtiği döner, değer ya da dosya içeriği dönmez.
Sözcük/kalıp tabanlı yaklaşık tahmindir, kaçırabilir.

Düzey: ortak bir şey yok → Yok; yalnızca ortak takma ad ya da yalnızca ortak dolaylı
tanımlayıcı → Orta; ikisi birlikte → Yüksek.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from . import tanima
from .extra_types import _fold
from .pseudonym import PREFIX

_PSEUDO = re.compile(
    r"(?<![\wÇĞİÖŞÜçğıöşü-])(" + "|".join(re.escape(p) for p in sorted(set(PREFIX.values()), key=len, reverse=True)) + r")-(\d+)(?!\d)"
)
_PATTERNS = {
    "unvan_kurum": (tanima._TITLE_ORG, tanima._ORG_TITLE),
    "meslek": (tanima._OCC,),
    "yas": (tanima._AGE,),
    "tarih": (tanima._DATE,),
}


def _digest(value: str) -> str:
    return hashlib.sha256(re.sub(r"\s+", " ", value).strip().encode("utf-8")).hexdigest()


def _signature(text: str) -> tuple[dict[str, set[str]], set[str]]:
    """Belgedeki dolaylı tanımlayıcıların ve takma adların özetleri (tür → özet kümesi)."""
    low = tanima._lower(text)
    found: dict[str, set[str]] = {}
    for kind, pats in _PATTERNS.items():
        vals = {_digest(m.group(0)) for p in pats for m in p.finditer(low)}
        if vals:
            found[kind] = vals
    il = {_digest(m.group(0)) for m in tanima._IL.finditer(_fold(text))}
    if il:
        found["il"] = il
    return found, {_digest(m.group(0)) for m in _PSEUDO.finditer(text)}


def analyze_texts(texts: list[str]) -> dict[str, Any] | None:
    """Metin listesinden bağlanabilirlik özeti; en az iki belge yoksa None."""
    if len(texts) < 2:
        return None
    sigs = [_signature(t) for t in texts]
    indirect: dict[str, dict[str, int]] = {}
    for kind in tanima.WEIGHTS:
        seen: dict[str, int] = {}
        for found, _ in sigs:
            for d in found.get(kind, ()):
                seen[d] = seen.get(d, 0) + 1
        shared = [n for n in seen.values() if n >= 2]
        if shared:
            indirect[kind] = {"ortak": len(shared), "en_cok_belge": max(shared)}
    pseudo_seen: dict[str, int] = {}
    for _, pseudo in sigs:
        for d in pseudo:
            pseudo_seen[d] = pseudo_seen.get(d, 0) + 1
    pseudo_shared = [n for n in pseudo_seen.values() if n >= 2]
    takma = {"ortak": len(pseudo_shared), "en_cok_belge": max(pseudo_shared)} if pseudo_shared else None
    if indirect and takma:
        level = "Yüksek"
    elif indirect or takma:
        level = "Orta"
    else:
        level = "Yok"
    return {"belge_sayisi": len(texts), "duzey": level, "dolayli": indirect, "takma_ad": takma}


def warning_lines(r: dict[str, Any]) -> list[str]:
    """Kullanıcıya gösterilecek uyarı satırları (değer içermez); risk yoksa boş liste."""
    if r["duzey"] == "Yok":
        return []
    lines = [
        f"Bağlanabilirlik uyarısı ({r['belge_sayisi']} belge, düzey: {r['duzey']}): belgeler birlikte gönderilirse "
        "ortak kalan bilgiler aynı kişiye/olaya bağlanmasını kolaylaştırabilir (anonimleştirme güvencesi değildir)."
    ]
    if r["takma_ad"]:
        t = r["takma_ad"]
        lines.append(
            f"- {t['ortak']} takma ad birden fazla belgede aynı (en çok {t['en_cok_belge']} belgede); "
            "belge başına farklı takma ad kapsamı kullanmayı düşünün."
        )
    for kind, v in sorted(r["dolayli"].items()):
        lines.append(f"- Ortak {tanima.LABELS[kind]}: {v['ortak']} değer birden fazla belgede kalıyor (en çok {v['en_cok_belge']} belgede).")
    return lines


def analyze_documents(paths: list[Any]) -> dict[str, Any] | None:
    """Maskeli kopyaları okuyup çözümler; okunamayanlar atlanır, 2'den az belge kalırsa None."""
    from .ozel_nitelikli import document_text

    texts = []
    for p in paths:
        try:
            t = document_text(p)
        except Exception:
            continue
        if t.strip():
            texts.append(t)
    result = analyze_texts(texts)
    if result is not None:
        result["uyari"] = warning_lines(result)
    return result
