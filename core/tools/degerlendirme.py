"""Tür bazında duyarlılık ve kaçırma oranı ölçer (TAKIP 1.61). Yalnızca sahte veri kullanır.

Kullanım (repo kökünden, motorun Python'uyla):

    python core/tools/degerlendirme.py [--esik 0.9]

Her tür için sahte değerler birkaç bağlam kalıbına gömülür; `detect` çalıştırılır.
- duyarlılık: değeri kapsayan, aynı türde bulgu bulunan örneklerin oranı (kesin + belirsiz)
- kesin duyarlılık: yalnız düşük güvenli (belirsiz) olmayan bulgular sayılır
- kaçırma: 1 - duyarlılık
- yanlış alarm: değer içermeyen metinlerde çıkan bulgu sayısı (tür bazında)

Çıkış kodu: 0 tüm türler eşik üstünde, 1 eşik altı tür var. Rapora değerin kendisi yazılmaz.
"""

from __future__ import annotations

import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from fake_data import fake_card, fake_iban, fake_tc, fake_vkn  # noqa: E402

from bulutbelge_core.detect import LOW, detect  # noqa: E402
from bulutbelge_core.rules import Rules  # noqa: E402

_CONTEXTS = (
    "{v}",
    "Müşteri bilgisi: {v} olarak kayıtlı.",
    "Sayın yetkili,\nilgili kayıt ({v}) tarafımıza iletilmiştir.",
    "Ad: Deneme Kişi; değer: {v}; tarih: 01.02.2024",
)


def _vals(prefixes: list[str], make) -> list[str]:
    return [make(p) for p in prefixes]


# 5 ile başlayan 10 hane telefon biçimine uyar (telefon olarak gizlenir); VKN ölçümüne alınmaz.
_NINE = ["123456789", "234567891", "345678912", "456789123", "678912345", "789123456"]

# tür -> sahte değerler
CORPUS: dict[str, list[str]] = {
    "tc_kimlik": _vals(_NINE, fake_tc),
    "vkn": _vals(_NINE, fake_vkn),
    "iban": [fake_iban(), fake_iban("0001200945100000000000"), fake_iban("0006200000000000000001")],
    "kredi_karti": [fake_card(), fake_card("510510510510510"), fake_card("378282246310005"[:15])],
    "telefon": ["0532 123 45 67", "+90 533 765 43 21", "0555 111 22 33", "(0542) 987 65 43"],
    "eposta": ["deneme.kisi@ornek.com.tr", "a_b-c@ornek.org", "musteri1@ornek.com"],
    "plaka": ["34 ABC 123", "06 DY 4567", "35 A 1234"],
    "ip": ["10.20.30.45", "192.168.1.200"],
    "mac": ["aa:bb:cc:dd:ee:ff", "00-1A-2B-3C-4D-5E"],
    "dogum_tarihi": ["Doğum tarihi: 14.03.1987", "Doğum Tarihi: 02/11/1990"],
}

# Hiçbir kişisel veri içermeyen metinler (yanlış alarm ölçümü).
NEGATIVES = (
    "Toplantı salı günü saat 14:00'te yapılacaktır.",
    "Rapor 3 sayfadan oluşur; ek-2 ve ek-3 ektedir.",
    "Sürüm 2.4.1 yayınlandı, sayfa 12 ve madde 7 incelenecek.",
    "Sipariş miktarı 120 adet, birim ağırlık 4,5 kg.",
)


@dataclass
class TypeResult:
    n: int = 0
    found: int = 0
    certain: int = 0
    missed: list[str] = field(default_factory=list)  # yalnızca ilk iki karakter

    @property
    def recall(self) -> float:
        return self.found / self.n if self.n else 1.0

    @property
    def certain_recall(self) -> float:
        return self.certain / self.n if self.n else 1.0

    @property
    def miss_rate(self) -> float:
        return 1.0 - self.recall


def _target(value: str) -> str:
    """Bağlamlı değerlerde ('Doğum tarihi: X') aranacak asıl kısım."""
    return value.split(": ", 1)[1] if ": " in value else value


def evaluate(rules: Rules | None = None) -> tuple[dict[str, TypeResult], Counter]:
    rules = rules or Rules.from_dict(None)
    results: dict[str, TypeResult] = {}
    for type_key, values in CORPUS.items():
        res = results.setdefault(type_key, TypeResult())
        for value in values:
            target = _target(value)
            for ctx in _CONTEXTS:
                text = ctx.format(v=value)
                start = text.index(target)
                end = start + len(target)
                hits = [
                    f
                    for f in detect(text, rules)
                    if f.type == type_key and f.start < end and f.end > start
                ]
                res.n += 1
                if hits:
                    res.found += 1
                    if any(f.confidence != LOW for f in hits):
                        res.certain += 1
                else:
                    res.missed.append(target[:2] + "…")
    false_alarms: Counter = Counter()
    for text in NEGATIVES:
        for f in detect(text, rules):
            false_alarms[f.type] += 1
    return results, false_alarms


def report(results: dict[str, TypeResult], false_alarms: Counter) -> str:
    lines = [f"{'tür':14}{'örnek':>7}{'duyarlılık':>12}{'kesin':>8}{'kaçırma':>9}"]
    for k, r in results.items():
        lines.append(f"{k:14}{r.n:>7}{r.recall:>12.2%}{r.certain_recall:>8.0%}{r.miss_rate:>9.2%}")
        if r.missed:
            lines.append(f"   kaçırılan (ilk 2 karakter): {', '.join(sorted(set(r.missed))[:6])}")
    total_fa = sum(false_alarms.values())
    lines.append(f"\nyanlış alarm (değersiz {len(NEGATIVES)} metinde): {total_fa}")
    for k, n in false_alarms.items():
        lines.append(f"   {k}: {n}")
    return "\n".join(lines)


def main() -> None:
    threshold = 0.9
    if "--esik" in sys.argv:
        threshold = float(sys.argv[sys.argv.index("--esik") + 1])
    sys.stdout.reconfigure(encoding="utf-8")
    results, false_alarms = evaluate()
    print(report(results, false_alarms))
    weak = [k for k, r in results.items() if r.recall < threshold]
    if weak:
        print(f"\nEşik altı ({threshold:.0%}): {', '.join(weak)}")
    sys.exit(1 if weak else 0)


if __name__ == "__main__":
    main()
