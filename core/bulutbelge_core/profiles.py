"""Hazır kural takımları ("Kime gidecek?"): masaüstü uygulaması ve sunucu ortak kullanır.

Masaüstünde bunlar ilk açılışta kullanıcının ayarlarına bir kez eklenir (kullanıcı değiştirebilir,
silebilir); sunucuda yönetim arayüzü gelene kadar doğrudan bunlar kullanılır.
Her takım varsayılan kuralların üzerine yalnızca farklı olan türleri yazar.
"""

from __future__ import annotations

from typing import Any

from .rules import Rules

DEFAULT_PROFILE_ID = "varsayilan"

BUILTIN_PURPOSES: tuple[tuple[str, str, dict[str, tuple[bool, str]]], ...] = (
    (
        "musteri",
        "Müşteriye",
        # Dışarıya gidiyor: kişiyi tanıtan her şey gizlenir, yalnızca il ve on yıl kalır.
        {"kisi_adi": (True, "etiket"), "tc_kimlik": (True, "karartma"), "telefon": (True, "karartma")},
    ),
    (
        "denetci",
        "Denetçiye",
        # İz sürülebilsin: baş harfler, son 4 hane, il-ilçe, doğum yılı; tutarlar aralığa çevrilir
        # (büyüklük görünür, kesin değer gitmez).
        {
            "kisi_adi": (True, "bas_harf"),
            "tc_kimlik": (True, "son4"),
            "telefon": (True, "son4"),
            "adres": (True, "il_ilce"),
            "dogum_tarihi": (True, "yil"),
            "tutar": (True, "genel"),
        },
    ),
    (
        "kurum_ici",
        "Kurum içine",
        # Kurum içinde kalıyor: yalnızca kimlik ve hesap numaraları gizlenir.
        {
            "kisi_adi": (False, "etiket"),
            "telefon": (False, "karartma"),
            "eposta": (False, "etiket"),
            "adres": (False, "genel"),
            "dogum_tarihi": (False, "genel"),
            "plaka": (False, "karartma"),
            "ip": (False, "etiket"),
            "imei": (False, "karartma"),
            "mac": (False, "etiket"),
            "sase_no": (False, "karartma"),
            "sicil_no": (False, "karartma"),
            "gps": (False, "karartma"),
            "kullanici_adi": (False, "etiket"),
            "unvan_kurum": (False, "etiket"),
            "musteri_no": (False, "etiket"),
            "imza": (False, "karartma"),
            "yuz": (False, "bulanik"),
        },
    ),
    (
        "efatura",
        "e-Fatura",
        # e-Fatura (PDF, imzalı UBL XML ve ZIP): alıcı/satıcı unvanı, adres, tutar, vergi/sicil no, banka/IBAN, ETTN/e-imza.
        {
            "kurum_unvani": (True, "etiket"),
            "kisi_adi": (True, "etiket"),
            "adres": (True, "karartma"),
            "tutar": (True, "karartma"),
            "vkn": (True, "karartma"),
            "tc_kimlik": (True, "karartma"),
            "vergi_dairesi": (True, "etiket"),
            "mersis": (True, "karartma"),
            "ticaret_sicil": (True, "karartma"),
            "iban": (True, "son4"),
            "banka_bilgisi": (True, "karartma"),
            "telefon": (True, "karartma"),
            "eposta": (True, "etiket"),
            "web_sitesi": (True, "etiket"),
            "ettn": (True, "karartma"),
            "imza": (True, "karartma"),
            # Fatura dışı genel alanlar kapalı başlar; istenirse kural takımından açılabilir.
            "kredi_karti": (False, "son4"),
            "dogum_tarihi": (False, "genel"),
            "plaka": (False, "karartma"),
            "ip": (False, "etiket"),
            "imei": (False, "karartma"),
            "mac": (False, "etiket"),
            "sase_no": (False, "karartma"),
            "pasaport": (False, "karartma"),
            "ehliyet": (False, "karartma"),
            "sgk": (False, "karartma"),
            "sicil_no": (False, "karartma"),
            "musteri_no": (False, "etiket"),
            "yuz": (False, "bulanik"),
        },
    ),
)

# Sektör kural takımları: amaç takımlarının yanında, sektöre özgü kalıp ve yöntemler. Her biri
# (kimlik, ad, tür geçersiz kılmaları, özel kalıplar, sütun kuralları). Kalıplar sahte değerle
# denenir; kurum kendi numara biçimine göre ayarlamalıdır.
SECTOR_PROFILES: tuple[tuple[str, str, dict[str, tuple[bool, str]], list[dict[str, str]], list[dict[str, str]]], ...] = (
    (
        "saglik",
        "Sağlık",
        # Tarihte yalnızca yıl (90 yaş ve üstü "90+ yaş"), adreste yalnızca bölge.
        {
            "kisi_adi": (True, "etiket"),
            "tc_kimlik": (True, "karartma"),
            "telefon": (True, "karartma"),
            "dogum_tarihi": (True, "yil"),
            "adres": (True, "bolge"),
            "sgk": (True, "karartma"),
            "yuz": (True, "bulanik"),
        },
        [
            {"name": "Protokol no", "pattern": r"(?:protokol|hasta)\s*(?:no|numarası)\s*[:.]?\s*\d{4,12}"},
        ],
        [
            {"header": "Yaş", "action": "yas"},
        ],
    ),
    (
        "ik",
        "İnsan kaynakları",
        # Personel dosyası: kimlik, sicil, SGK, IBAN gizli; doğum tarihi yalnızca yıl; tutarlar (maaş) aralık.
        {
            "kisi_adi": (True, "etiket"),
            "tc_kimlik": (True, "karartma"),
            "sicil_no": (True, "karartma"),
            "sgk": (True, "karartma"),
            "iban": (True, "karartma"),
            "telefon": (True, "karartma"),
            "dogum_tarihi": (True, "yil"),
            "adres": (True, "il_ilce"),
            "tutar": (True, "genel"),
        },
        [],
        [],
    ),
    (
        "hukuk",
        "Hukuk / UYAP",
        # Dava dosyası: esas, karar ve dosya numaraları ile taraf kimlikleri gizli.
        {
            "kisi_adi": (True, "etiket"),
            "tc_kimlik": (True, "karartma"),
            "vkn": (True, "karartma"),
            "telefon": (True, "karartma"),
            "adres": (True, "il_ilce"),
            "iban": (True, "karartma"),
            "plaka": (True, "karartma"),
        },
        [
            {"name": "Esas no", "pattern": r"\b\d{4}/\d{1,6}\s*(?:E\.?|Esas)(?![\w])"},
            {"name": "Karar no", "pattern": r"\b\d{4}/\d{1,6}\s*(?:K\.?|Karar)(?![\w])"},
            {"name": "Dosya no", "pattern": r"(?:dosya|soruşturma|takip)\s*(?:no|numarası)\s*[:.]?\s*\d{4}/\d{1,7}"},
        ],
        [],
    ),
    (
        "finans",
        "Finans",
        # Hesap ve kart bilgileri: IBAN/kart son 4 hane açık; tutar açık kalır (iz sürme).
        {
            "kisi_adi": (True, "etiket"),
            "tc_kimlik": (True, "karartma"),
            "vkn": (True, "karartma"),
            "iban": (True, "son4"),
            "kredi_karti": (True, "son4"),
            "telefon": (True, "karartma"),
            "adres": (True, "il_ilce"),
            "musteri_no": (True, "son4"),
            "tutar": (False, "genel"),
        },
        [],
        [],
    ),
)


def default_profile() -> dict[str, Any]:
    rules = Rules.default()
    return {
        "id": DEFAULT_PROFILE_ID,
        "name": "Varsayılan",
        "types": {
            k: {"enabled": r.enabled, "method": r.method}
            for k, r in rules.types.items()
            if k not in ("ozel_ifade", "ozel_kalip")
        },
        "patterns": [],
        "whitelist": [],
        "institutions": [],
        "signature_labels": list(rules.signature_labels),
    }


def builtin_profiles() -> list[dict[str, Any]]:
    out = []
    for pid, name, overrides in BUILTIN_PURPOSES:
        p = default_profile()
        p["id"], p["name"] = pid, name
        for key, (enabled, method) in overrides.items():
            p["types"][key] = {"enabled": enabled, "method": method}
        out.append(p)
    for pid, name, overrides, patterns, columns in SECTOR_PROFILES:
        p = default_profile()
        p["id"], p["name"] = pid, name
        for key, (enabled, method) in overrides.items():
            p["types"][key] = {"enabled": enabled, "method": method}
        p["patterns"] = [dict(x) for x in patterns]
        if columns:
            p["column_rules"] = [dict(x) for x in columns]
        out.append(p)
    return out


def all_builtin() -> list[dict[str, Any]]:
    """Varsayılan + hazır takımlar, sırayla."""
    return [default_profile(), *builtin_profiles()]
