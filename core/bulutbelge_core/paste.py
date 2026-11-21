"""Yapıştırılan metin: e-posta, not ya da yapay zekâya gönderilecek bir istem.

Dosya yoktur; metin yalnızca bellekte taranır, bulgular ve her birinin yerine
yazılacak metin döner. Temizlenmiş metni arayüz, kullanıcının açık bıraktıklarını
atlayarak kurar ve panoya kopyalar. Hiçbir şey diske yazılmaz.
"""

from __future__ import annotations

from dataclasses import dataclass

from .names import name_hints
from .detect import Finding, detect
from .pdf import PdfError
from .rules import Rules
from .textdoc import _text_replacement

MAX_CHARS = 200_000


@dataclass
class PasteFinding:
    id: str
    finding: Finding
    replacement: str


def is_delimited_table(text: str) -> bool:
    """Metin ayraçlı tablo mu (CSV/TSV): başlık + en az 1 veri satırı, tutarlı ≥2 sütun.

    Temkinli: başlık hücreleri kısa, dolu ve tekrarsız olmalı; aksi hâlde düz metin sayılır.
    """
    from .textdoc import _csv_cells

    if max(text.split("\n", 1)[0].count(d) for d in ",;\t") == 0:
        return False
    widths: dict[int, int] = {}
    dolu: set[int] = set()
    heads: list[str] = []
    for r, c, s, e in _csv_cells(text):
        widths[r] = c + 1
        if text[s:e].strip():
            dolu.add(r)
        if r == 0:
            heads.append(text[s:e].strip())
    sayilar = {w for r, w in widths.items() if r in dolu}  # boş satırlar (ör. sondaki) sayılmaz
    if len(dolu) < 2 or 0 not in dolu or len(sayilar) != 1 or min(sayilar) < 2:
        return False
    if any(not h or len(h) > 40 or len(h.split()) > 4 or h[-1] in ".!?:" for h in heads) or len({h.lower() for h in heads}) != len(heads):
        return False
    return True


def scan_paste(text: str, rules: Rules) -> list[PasteFinding]:
    if len(text) > MAX_CHARS:
        raise PdfError(f"Metin çok uzun; en fazla {MAX_CHARS:,} karakter".replace(",", "."))
    if is_delimited_table(text):
        # Dosya yükleme yolundaki tablo işleme (sütun başlığı kuralları dahil); çıktı aynı ayraçlı metin.
        from .textdoc import _scan_text

        tarama = _scan_text(text, "csv", "utf-8", rules)
        return [PasteFinding(f.id.replace("t:", "p:", 1), f.finding, f.replacement) for f in tarama.findings]
    return [
        PasteFinding(f"p:{f.start}:{f.end}", f, _text_replacement(f, rules, "txt", "utf-8"))
        for f in detect(text, rules, name_hints([text]), lead=True)
    ]


def clean_text(text: str, findings: list[PasteFinding], excluded_ids: set[str] | None = None) -> str:
    """Bulguları yerine yazılacak metinle değiştirir (dışlananlar olduğu gibi kalır)."""
    excluded_ids = excluded_ids or set()
    out, pos = [], 0
    for p in sorted(findings, key=lambda x: x.finding.start):
        if p.id in excluded_ids:
            continue
        out.append(text[pos:p.finding.start])
        out.append(p.replacement)
        pos = p.finding.end
    out.append(text[pos:])
    return "".join(out)


def mask_filename(name: str, rules: Rules | None = None) -> str:
    """Dosya adındaki kişisel veriyi gizler: "Ayşe Yılmaz - dilekçe.pdf" -> "[AD SOYAD] - dilekçe.pdf".

    İşlem kaydında (yönetim paneli) belgenin ne olduğu anlaşılsın diye; klasör yolu atılır, uzantı
    korunur. Alt çizgi boşluk sayılır ("Mehmet_Demir") ve büyük-küçük harf yazımı da denenir.
    Bilinen sınır: Türkçe harfsiz küçük yazılmış adlar ("ayse yilmaz") her zaman bulunmaz.
    """
    import os
    import re

    rules = rules or Rules.from_dict(None)
    name = re.split(r"[\\/]", str(name or ""))[-1]
    name = "".join(ch for ch in name if ch.isprintable())[:160]
    kok, uzanti = os.path.splitext(name)
    if not re.fullmatch(r"\.[A-Za-z0-9]{1,8}", uzanti or ""):
        kok, uzanti = name, ""
    metin = re.sub(r"_+", " ", kok)
    bulgular: dict[tuple[int, int], PasteFinding] = {}
    for aday in (metin, metin.title()):
        for p in scan_paste(aday, rules):
            bulgular.setdefault((p.finding.start, p.finding.end), p)
    secilen, son = [], -1
    for (bas, bit), p in sorted(bulgular.items()):
        if bas >= son:
            secilen.append(p)
            son = bit
    return (clean_text(metin, secilen) + uzanti.lower()).strip()[:160]
