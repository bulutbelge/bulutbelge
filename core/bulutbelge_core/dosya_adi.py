"""Dosya adı hijyeni: dosya adı ve yoldaki kişi adı.

Dosya adı belgenin içeriği kadar kişisel olabilir ("Ahmet Yılmaz sözleşme.pdf"). Bu modül adı
(yol parçalarını da) bulur, maskeli çıktı için ad önerir ve kayıtlara yazılacak yolu temizler.
Kişi adı değeri hiçbir yerde döndürülmez; yalnızca konum, sayı ve temizlenmiş metin döner.
Tespit, metindeki ad bulucuyla aynıdır (`names.find_person_names`); ayraçlar (`_ - .`) boşluk
sayılır, küçük harfle yazılmış adların ilk harfi büyütülerek aranır.
"""

from __future__ import annotations

import re
from pathlib import Path

from .names import find_person_names
from .pdf import unique_path

# Yerine yazılan sözcük; yol ve dosya adında güvenle durabilir.
PLACEHOLDER = "kisi"
HISTORY_PLACEHOLDER = "[kişi]"

_SEP = re.compile(r"[_\-.]+")
_WORD = re.compile(r"[^\W\d_]+")


def _searchable(stem: str) -> tuple[str, bool]:
    """Aynı uzunlukta metin: ayraçlar boşluk. Hiç büyük harf yoksa her sözcüğün ilk harfi büyütülür.

    İkinci değer: büyütme yapıldı mı (uzunluk değişmez).
    """
    text = _SEP.sub(lambda m: " " * len(m.group()), stem)
    if any(c.isupper() for c in text):
        return text, False
    return _WORD.sub(lambda m: m.group()[:1].upper() + m.group()[1:], text), True


def name_spans(stem: str) -> list[tuple[int, int]]:
    """Ad içindeki kişi adı aralıkları (`stem` üzerinde, çakışmasız, sıralı).

    Tamamı küçük harfli adlarda sözcükler ayırt edilemez ("ahmet_yilmaz_sozlesme"); en çok
    iki sözcük (ad soyad) alınır, ikinci ad aranmaz.
    """
    text, lowered = _searchable(stem)
    spans = []
    for s, e, _ in find_person_names(text):
        if lowered:
            words = list(_WORD.finditer(text, s, e))
            e = words[min(len(words), 2) - 1].end()
        spans.append((s, e))
    return spans


def has_person_name(filename: str) -> bool:
    return bool(name_spans(Path(filename).stem))


def _replace(stem: str, repl: str) -> str:
    out, last = [], 0
    for s, e in name_spans(stem):
        out.append(stem[last:s])
        out.append(repl)
        last = e
    out.append(stem[last:])
    return "".join(out)


def scrub_name(filename: str, repl: str = PLACEHOLDER) -> str:
    """Dosya adındaki kişi adlarını `repl` ile değiştirir (uzantı korunur)."""
    p = Path(filename)
    return _replace(p.stem, repl) + p.suffix


def suggest_masked_name(source: str | Path) -> str | None:
    """Kaynak adı kişi adı taşıyorsa, adsız `_maskeli` çıktı yolu önerir; taşımıyorsa None.

    Öneri kaynağın klasöründedir ve var olan dosyanın üzerine yazmaz.
    """
    src = Path(source)
    if not has_person_name(src.name):
        return None
    stem = _replace(src.stem, PLACEHOLDER).strip(" _-.") or PLACEHOLDER
    return str(unique_path(src.with_name(f"{stem}_maskeli{src.suffix}")))


def scrub_path(path: str, repl: str = HISTORY_PLACEHOLDER) -> str:
    """Yolun her parçasındaki kişi adlarını değiştirir (ayraçlar ve uzantı korunur).

    Kayıtlara (ör. "Son Yapılanlar") yazılmadan önce kullanılır.
    """
    parts = re.split(r"([/\\])", path)
    for i, part in enumerate(parts):
        if part in ("/", "\\") or not part:
            continue
        if i == 0 and re.fullmatch(r"[A-Za-z]:", part):
            continue  # Windows sürücü harfi ("C:") kişi adı değildir; silinirse yol bozulur
        parts[i] = scrub_name(part, repl)
    return "".join(parts)


LOG_PLACEHOLDER = "[AD SOYAD]"


def mask_log_text(text: str, rules=None, *, filename: bool = False) -> str:
    """İşlem günlüğüne yazılacak serbest metni (dosya adı, amaç) çekirdekle tarayıp etiketle değiştirir.

    Dosya adında ayraçlar (`_ - .`) korunur: "Ayse_Yilmaz_CV.pdf" -> "[AD SOYAD]_CV.pdf". Kişi adı dışındaki
    kişisel veriler (kimlik no, e-posta, telefon, IBAN vb.) de tarama kurallarıyla etiketlenir. Özgün değer
    döndürülmez. Boş ya da metin olmayan girdi için boş metin döner.
    """
    from .paste import clean_text, scan_paste
    from .rules import Rules

    if not isinstance(text, str) or not text.strip():
        return ""
    text = "".join(ch for ch in text if ch.isprintable())
    rules = rules or Rules.from_dict(None)
    if filename:
        text = scrub_name(text, LOG_PLACEHOLDER)
    else:
        spans = [(s, e) for s, e, _ in find_person_names(text)]
        out, last = [], 0
        for s, e in spans:
            out.append(text[last:s])
            out.append(LOG_PLACEHOLDER)
            last = e
        out.append(text[last:])
        text = "".join(out)
    return clean_text(text, scan_paste(text, rules))
