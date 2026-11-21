"""Karışık yazılmış TC, IBAN, telefon, kart ve VKN numaraları.

Aralıklı, noktalı, parantezli, tam genişlikli rakamlar, OCR karışıklıkları
(O/0, l/1, I/1, S/5) ve (IBAN için) satır bölünmesi burada normalleştirilir.
Yanlış pozitifi artırmamak için TC ve IBAN kontrol hanesinden geçmek zorundadır;
telefon yalnızca biçim ve en az 7 gerçek rakam ister. Düz yazım `detect.py`'deki
asıl kalıplarla bulunur, burası yalnızca onların kaçırdığı biçimleri ekler.
"""

from __future__ import annotations

import re

from .labels import label_before, label_kind
from .validators import iban_valid, luhn_valid, tc_kimlik_valid, vkn_valid

_OCR = {"O": "0", "o": "0", "l": "1", "I": "1", "S": "5"}
_DL = r"[\d OolIS]".replace(" ", "")
_SEP = r"(?:[ .\-()/ ]{1,2})"
_RUN = re.compile(rf"(?<![\w+])\+?{_DL}(?:{_SEP}?{_DL})+(?![\w])")
# TR + 24 hane; ayraç olarak tek satır sonu da olabilir.
# Satır sonundan önce boşluk/tire, sonra en çok iki satır sonu (PDF'de blok sınırı) olabilir.
# Dil `[ .\-\u00a0]{0,2}(?:\r?\n){0,2}[ \u00a0]*` ile aynı; ama eski biçimde iki boşluk üç ayrı biçimde
# bölünebildiği için {24} tekrar başarısız olunca üstel geri izliyordu (güvenlik taraması F3/F5).
# Satır sonu varsa (1), yoksa en az iki karakter (2) ya da en çok bir karakter (3): her dizi tek biçimde bölünür.
_IBAN_SEP = (
    r"(?:[ .\-\u00a0]{0,2}(?:\r?\n){1,2}[ \u00a0]*"
    r"|[ .\-\u00a0]{2}[ \u00a0]*"
    r"|[ .\-\u00a0]?)"
)
_IBAN = re.compile(rf"(?<![\w])[Tt][Rr](?:{_IBAN_SEP}{_DL}){{24}}(?![\w])")
# Satır sonundan bölünmüş kart numarası (13-19 hane); yalnızca kart etiketiyle kabul edilir.
_CARD_WRAP = re.compile(rf"(?<![\w]){_DL}(?:{_IBAN_SEP}{_DL}){{12,18}}(?![\w])")
# Satır sonundan bölünmüş TC (11 hane) ve telefon (10-12 hane, başta + olabilir); yalnızca türün etiketiyle.
# Eşleşme sonraki satırdaki başka bir sayıyı da yutabileceği için her hane sınırında kısa adaylar da denenir.
_NUM_WRAP = re.compile(rf"(?<![\w+])\+?{_DL}(?:{_IBAN_SEP}{_DL}){{9,18}}(?![\w])")


# E-posta: "@" yerine [at] (at) {at} [@] (@) ＠, "." yerine [dot] (dot) {dot} [nokta]. Düz "at" sözcüğü
# kabul edilmez (yanlış pozitif); "@" ayraçlı olmalı.
_AT = r"(?:\s?[\[(\{]\s?(?:at|@)\s?[\])\}]\s?|＠)"
_DOT = r"(?:\s?[\[(\{]\s?(?:dot|nokta)\s?[\])\}]\s?|\.)"
_MAIL = re.compile(
    rf"(?<![\w.%+-])[A-Za-z0-9][A-Za-z0-9._%+-]*{_AT}[A-Za-z0-9-]+(?:{_DOT}[A-Za-z0-9-]+)*{_DOT}[A-Za-z]{{2,}}(?![\w])",
    re.IGNORECASE,
)


def _digits(s: str) -> tuple[str, int]:
    """(normalleşmiş rakamlar, gerçek rakam sayısı); rakam olmayanlar atılır."""
    out: list[str] = []
    real = 0
    for ch in s:
        if ch in _OCR:
            out.append(_OCR[ch])
        elif ch.isdecimal():
            out.append(str(int(ch)))
            real += 1
    return "".join(out), real


def _phone_ok(d: str) -> bool:
    if d.startswith("0090"):
        d = d[4:]
    elif d.startswith("90") and len(d) in (12,):
        d = d[2:]
    if d.startswith("0"):
        d = d[1:]
        return len(d) == 10 and d[0] in "2345"
    return len(d) == 10 and d[0] == "5"


def find_mixed_email(text: str) -> list[tuple[int, int]]:
    """Ayraçlı yazılmış e-posta adresleri (düz "@" içerenleri asıl kalıp bulur)."""
    return [(m.start(), m.end()) for m in _MAIL.finditer(text)]


def _label_is(text: str, start: int, kind: str) -> bool:
    return label_kind(label_before(text, start)) == kind


def find_mixed(
    text: str, tc: bool = True, iban: bool = True, phone: bool = True, vkn: bool = False, card: bool = False
) -> list[tuple[str, int, int, str]]:
    """(tür, başlangıç, bitiş, güven) listesi; güven "yuksek" ya da "orta" (OCR harfi varsa).

    Kart (13-19 hane) Luhn'dan geçmek zorundadır. VKN'nin kontrol hanesi zayıf olduğu (yaklaşık onda bir
    rastgele sayı geçer) ve 10 haneli telefonla karışabildiği için karışık yazımda önünde vergi etiketi
    ("Vergi No", "VKN") aranır; düz yazılmış VKN'yi asıl kalıp bulur. Satırdan bölünmüş kart da yalnızca
    kart etiketiyle kabul edilir.
    """
    found: list[tuple[str, int, int, str]] = []
    if iban:
        for m in _IBAN.finditer(text):
            d, real = _digits(m.group()[2:])
            if real >= 12 and iban_valid("TR" + d):
                found.append(("iban", m.start(), m.end(), "orta" if real < len(d) else "yuksek"))
    if tc or phone or vkn or card:
        for m in _RUN.finditer(text):
            raw = m.group()
            d, real = _digits(raw)
            if real < 7 or raw.isascii() and raw.isdigit():
                continue  # düz yazımı asıl kalıplar bulur
            conf = "orta" if real < len(d) else "yuksek"
            if tc and len(d) == 11 and tc_kimlik_valid(d):
                found.append(("tc_kimlik", m.start(), m.end(), conf))
            elif phone and _phone_ok(d):
                found.append(("telefon", m.start(), m.end(), conf))
            elif card and 13 <= len(d) <= 19 and luhn_valid(d):
                found.append(("kredi_karti", m.start(), m.end(), conf))
            elif vkn and len(d) == 10 and vkn_valid(d) and _label_is(text, m.start(), "vkn"):
                found.append(("vkn", m.start(), m.end(), conf))
    if card:
        for m in _CARD_WRAP.finditer(text):
            if "\n" not in m.group():
                continue
            d, real = _digits(m.group())
            if real >= 12 and 13 <= len(d) <= 19 and luhn_valid(d) and _label_is(text, m.start(), "kredi_karti"):
                found.append(("kredi_karti", m.start(), m.end(), "orta" if real < len(d) else "yuksek"))
    if tc or phone:
        for m in _NUM_WRAP.finditer(text):
            if "\n" not in m.group():
                continue
            hit = _wrapped_labeled(text, m, tc, phone)
            if hit and not any(s < hit[2] and hit[1] < e for _k, s, e, _c in found):
                found.append(hit)
    return found


def _wrapped_labeled(text: str, m: re.Match, tc: bool, phone: bool) -> tuple[str, int, int, str] | None:
    """Satır sonundan bölünmüş, önünde kendi etiketi olan TC ya da telefon; en uzun geçerli önek alınır."""
    kind = label_kind(label_before(text, m.start()))
    if not (tc and kind == "tc_kimlik" or phone and kind == "telefon"):
        return None
    raw = m.group()
    sonlar = [i + 1 for i, ch in enumerate(raw) if ch in _OCR or ch.isdigit()]
    for son in reversed(sonlar):
        parca = raw[:son]
        if "\n" not in parca:
            break  # satır bölünmesi olmayanı asıl kalıplar bulur
        d, real = _digits(parca)
        if real < 7:
            break
        ok = len(d) == 11 and tc_kimlik_valid(d) if kind == "tc_kimlik" else _phone_ok(d) and real >= len(d) - 1
        if ok:
            return (kind, m.start(), m.start() + son, "orta")
    return None


# Hücreler arası bölünmüş değer (Excel/tablo): bir satırda yan yana hücrelere dağılmış parçalar.
_FRAG = re.compile(r"\d[\d ]{0,10}")
_FRAG_IBAN = re.compile(r"[Tt][Rr]\s?\d{2}[\d ]{0,10}")
MAX_SPLIT_CELLS = 11


def find_split_cells(cells: list[str]) -> list[tuple[str, int, int, str]]:
    """Yan yana hücrelere bölünmüş TC/IBAN/telefon: (tür, ilk hücre, son hücre dahil, güven).

    Parçalar yalnızca rakam ve boşluktan oluşur (IBAN'ın ilk parçası "TR" + 2 hane ile başlar) ve
    kısadır; tam değeri tek başına taşıyan hücre parça sayılmaz (onu asıl kalıplar bulur).
    TC ve IBAN kontrol hanesinden geçmek zorundadır; telefonda en çok 4 hücre ve her hücrede en az
    2 rakam istenir (komşu sayısal sütunlarla yanlış pozitif riski). Güven her zaman "orta".
    """
    n = len(cells)
    kinds = []  # None | "d" (rakam parçası) | "i" (IBAN başı)
    for c in cells:
        t = c.strip()
        if _FRAG_IBAN.fullmatch(t):
            kinds.append("i")
        elif _FRAG.fullmatch(t) and len(t.replace(" ", "")) <= 8 and t.isascii():
            kinds.append("d")
        else:
            kinds.append(None)
    out: list[tuple[str, int, int, str]] = []
    i = 0
    while i < n:
        hit = None
        if kinds[i] is not None:
            for j in range(min(n, i + MAX_SPLIT_CELLS) - 1, i, -1):
                if any(k is None or (k == "i" and x != i) for x, k in enumerate(kinds[i : j + 1], i)):
                    continue
                joined = "".join(cells[x].replace(" ", "").strip() for x in range(i, j + 1))
                counts = [sum(ch.isdigit() for ch in cells[x]) for x in range(i, j + 1)]
                if kinds[i] == "i":
                    if len(joined) == 26 and iban_valid(joined.upper()):
                        hit = ("iban", j)
                elif min(counts) >= 1 and len(joined) == 11 and j - i < 6 and joined[0] != "0" and tc_kimlik_valid(joined):
                    hit = ("tc_kimlik", j)
                elif min(counts) >= 2 and j - i < 4 and len(joined) in (10, 11, 12, 14) and _phone_ok(joined):
                    hit = ("telefon", j)
                if hit:
                    break
        if hit:
            out.append((hit[0], i, hit[1], "orta"))
            i = hit[1] + 1
        else:
            i += 1
    return out
