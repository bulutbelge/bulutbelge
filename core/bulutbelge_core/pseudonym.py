"""Takma ad (pseudonymization): aynı değere her yerde aynı takma ad.

"Ayşe Yılmaz" belgenin her yerinde, hatta başka belgelerde de "Kişi-3" olur.
Böylece maskeli belgede kimin kim olduğu gizlenir ama ilişkiler okunabilir
kalır ("Kişi-3, Kişi-5'e 12.500 TL ödedi").

ÖNEMLİ: Takma ad anonimleştirme DEĞİLDİR. Eşleme tablosu saklandığı sürece
takma ad yetkili kişi tarafından geri çevrilebilir; bu yüzden tablo yalnızca
parolalı kasada tutulur, maskeli belgeye ya da başka bir dosyaya yazılmaz.

Tablo biçimi (kasada JSON):
    {"kisi_adi": {"next": 4, "values": {"ayşe yılmaz": [3, "Ayşe Yılmaz"]}}, ...}

Belge başına kapsam (belge_basina=True): aynı değer her belgede yeni bir numara
alır; numaralar kasada tek sayaçtan gelir, böylece "Kişi-7" yine tek bir değere
döner. Belgeler arası bağlanabilirlik azalır, ama takma ad yine anonimleştirme
değildir. Bir Pseudonyms nesnesi tek belge/işlem içindir. Varsayılan (ortak
kapsam) değişmez. İlk numaranın dışındakiler "extra" listesinde tutulur:
    {"kisi_adi": {..., "extra": [[7, "Ayşe Yılmaz"]]}}
"""

from __future__ import annotations

import copy
import re
from typing import Any

from .validators import digits_only

PREFIX = {
    "kisi_adi": "Kişi",
    "kurum_unvani": "Kurum",
    "eposta": "E-posta",
    "telefon": "Telefon",
    "adres": "Adres",
    "tc_kimlik": "TC",
    "vkn": "VKN",
    "vergi_dairesi": "VD",
    "mersis": "MERSİS",
    "ticaret_sicil": "TS",
    "iban": "IBAN",
    "banka_bilgisi": "Banka",
    "tutar": "Tutar",
    "ettn": "ETTN",
    "pasaport": "Pasaport",
    "musteri_no": "Müşteri",
    "kullanici_adi": "Kullanıcı",
    "elle": "Değer",  # Excel'de elle seçilen satır/sütun
}
# Yazılışı farklı ama aynı değer sayılanlar: rakamlardan oluşan türlerde yalnızca rakamlar.
_DIGIT_TYPES = {"telefon", "tc_kimlik", "vkn", "iban", "mersis"}


def _norm(type_: str, value: str) -> str:
    if type_ in _DIGIT_TYPES:
        d = digits_only(value)
        # Telefonda ülke kodu ve baştaki 0 farkı aynı numara sayılır.
        return d[-10:] if type_ == "telefon" else d
    return re.sub(r"\s+", " ", value).strip().casefold()


class Pseudonyms:
    def __init__(self, table: dict[str, Any] | None = None, belge_basina: bool = False) -> None:
        self.table: dict[str, Any] = copy.deepcopy(table) if table else {}
        self.changed = False
        self.belge_basina = belge_basina
        self._belge: dict[tuple[str, str], int] = {}  # bu belgede verilen numaralar

    def label(self, type_: str, value: str) -> str:
        entry = self.table.setdefault(type_, {"next": 1, "values": {}})
        key = _norm(type_, value)
        if self.belge_basina:
            n = self._belge.get((type_, key))
            if n is None:
                n = entry["next"]
                entry["next"] += 1
                if key in entry["values"]:
                    entry.setdefault("extra", []).append([n, value.strip()])
                else:
                    entry["values"][key] = [n, value.strip()]
                self._belge[(type_, key)] = n
                self.changed = True
            return f"{PREFIX.get(type_, 'Değer')}-{n}"
        if key not in entry["values"]:
            entry["values"][key] = [entry["next"], value.strip()]
            entry["next"] += 1
            self.changed = True
        return f"{PREFIX.get(type_, 'Değer')}-{entry['values'][key][0]}"

    def lookup(self, label: str) -> dict[str, str] | None:
        """"Kişi-3" → {"type": "kisi_adi", "value": "Ayşe Yılmaz"}; yoksa None."""
        m = re.fullmatch(r"\s*(.+?)-(\d+)\s*", label)
        if not m:
            return None
        prefix, n = m.group(1).casefold(), int(m.group(2))
        for type_, p in PREFIX.items():
            if p.casefold() != prefix and _ascii(p).casefold() != prefix:
                continue
            for _key, (num, original) in self.table.get(type_, {}).get("values", {}).items():
                if num == n:
                    return {"type": type_, "value": original}
            for num, original in self.table.get(type_, {}).get("extra", []):
                if num == n:
                    return {"type": type_, "value": original}
        return None

    def stats(self) -> dict[str, int]:
        return {t: len(e.get("values", {})) for t, e in self.table.items() if e.get("values")}


def _ascii(s: str) -> str:
    return s.translate(str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU"))


def restore_text(text: str, pseudonyms: Pseudonyms | None) -> tuple[str, int]:
    """Metindeki "Kişi-3" gibi takma adları gerçek değerlere döndürür → (metin, değiştirilen sayı).

    Yalnızca açık kasadan gelen tabloyla çalışır (pseudonyms None ise hata verilir).
    Tabloda olmayan etiketler olduğu gibi kalır. Sonuç gerçek kişisel veri içerir:
    diske, rapora ya da günlüğe yazılmamalı, yalnızca yetkili kişiye gösterilmelidir.
    """
    from .rules import RuleError  # döngüsel içe aktarmayı önlemek için geç

    if pseudonyms is None:
        raise RuleError("Geri çevirmek için önce özel ifade kasasının kilidini açın")
    prefixes = sorted({q for p in PREFIX.values() for q in (p, _ascii(p))}, key=len, reverse=True)
    pattern = re.compile(
        r"(?<![\w-])(" + "|".join(re.escape(p) for p in prefixes) + r")-(\d+)(?!\w)", re.IGNORECASE
    )
    count = 0

    def sub(m: re.Match[str]) -> str:
        nonlocal count
        hit = pseudonyms.lookup(m.group(0))
        if hit is None:
            return m.group(0)
        count += 1
        return hit["value"]

    return pattern.sub(sub, text), count


def clean_table(raw: Any) -> dict[str, Any]:
    """Kasadan okunan tabloyu doğrular (bozuk girişler atılır)."""
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for type_, entry in raw.items():
        if type_ not in PREFIX or not isinstance(entry, dict):
            continue
        values = {}
        for k, v in (entry.get("values") or {}).items():
            if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int):
                values[str(k)] = [v[0], str(v[1])]
        nxt = max([n for n, _ in values.values()] + [int(entry.get("next", 1)) - 1]) + 1
        extra = [[v[0], str(v[1])] for v in (entry.get("extra") or []) if isinstance(v, list) and len(v) == 2 and isinstance(v[0], int)]
        if extra:
            nxt = max(nxt, max(n for n, _ in extra) + 1)
        out[type_] = {"next": nxt, "values": values, **({"extra": extra} if extra else {})}
    return out
