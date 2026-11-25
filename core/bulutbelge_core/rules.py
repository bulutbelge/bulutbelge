"""Kullanıcının belirlediği maskeleme kuralları.

Kurallar veri türlerini (aç/kapat + yöntem), kullanıcının eklediği özel
ifadeleri ve kalıpları, maskelenmeyecek değerleri (beyaz liste) taşır.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import regex

DEFAULT_SIGNATURE_LABELS = ("imza", "kaşe", "mühür", "onaylayan", "signature")

# Maskeleme yöntemleri
BLACKOUT = "karartma"  # siyah kutu, yerine yazı yok
LABEL = "etiket"  # beyaz kutu üzerine tür etiketi, ör. [TC NO]
KEEP_LAST4 = "son4"  # son 4 hane açık, ör. **** 1234
# Değer silinir, yerine orijinalden bilgi taşımayan buzlu cam görünümü konur (bkz. blur.py).
BLUR = "bulanik"
# Değeri daha az ayrıntılı hâle getirir: adres → il, doğum tarihi → on yıl, IP → alt ağ, tutar → aralık.
GENERALIZE = "genel"

# Türe özgü kısmi gösterim yöntemleri
ADDR_DISTRICT = "il_ilce"  # adres → "Kadıköy/İstanbul"
ADDR_NEIGHBORHOOD = "mahalle"  # adres → "Caferağa Mah., Kadıköy/İstanbul" (sokak ve kapı no gizli)
ADDR_REGION = "bolge"  # adres → "Marmara Bölgesi"
BIRTH_YEAR = "yil"  # doğum tarihi → "1987"
BIRTH_AGE = "yas"  # doğum tarihi → "30-39 yaş"
EMAIL_DOMAIN = "alan_adi"  # e-posta → "***@example.com"
PLATE_CITY = "plaka_il"  # plaka → "34 *** ***"
INITIALS = "bas_harf"  # kişi adı → "A. Y."
# Aynı değere her yerde aynı takma ad ("Kişi-3"). Anonimleştirme değildir: eşleme kasada
# saklanır, yetkili kişi geri çevirebilir. Kasa açık olmadan kullanılamaz (bkz. pseudonym.py).
PSEUDONYM = "takma_ad"

# Özel kalıp derleme ve arama için üst süre (saniye). Kullanıcının yazdığı
# kalıp aşırı geri izleme yaparsa (ReDoS) tarama kilitlenmesin.
PATTERN_TIMEOUT = 2.0


@dataclass(frozen=True)
class DataType:
    key: str
    label: str
    tag: str  # belgeye yazılan etiket; PDF'in standart yazı tipi Türkçe harf içermediği için ASCII
    methods: tuple[str, ...]
    default_method: str
    default_enabled: bool = True
    # Kullanıcı tarafından açılıp kapatılmayan tür (elle seçilen alan): yalnızca yöntemi seçilir.
    always_on: bool = False
    # Bu türde yöntemin adı genel addan farklıysa (ör. adreste "Genelleştirme" = "Sadece il").
    method_labels: tuple[tuple[str, str], ...] = ()
    # Ayarlar ekranında yöntem örneklerini üretmek için sahte örnek değer.
    example: str = ""


DATA_TYPES: dict[str, DataType] = {
    t.key: t
    for t in (
        DataType("kisi_adi", "Kişi adı", "[AD SOYAD]", (LABEL, INITIALS, PSEUDONYM, BLACKOUT, BLUR), LABEL,
                 example="Ayşe Yılmaz"),
        DataType("tc_kimlik", "TC kimlik no", "[TC NO]", (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT,
                 example="12345678950"),
        DataType("vkn", "Vergi kimlik no", "[VKN]", (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT,
                 example="1234567890"),
        DataType("iban", "IBAN", "[IBAN]", (KEEP_LAST4, BLACKOUT, LABEL, PSEUDONYM, BLUR), KEEP_LAST4,
                 example="TR33 0006 1005 1978 6457 8413 26"),
        DataType("kredi_karti", "Kredi kartı no", "[KART]", (KEEP_LAST4, BLACKOUT, LABEL, BLUR), KEEP_LAST4,
                 example="4111 1111 1111 1111"),
        DataType("telefon", "Telefon", "[TELEFON]", (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT,
                 example="0532 000 12 34"),
        DataType("eposta", "E-posta", "[E-POSTA]", (LABEL, EMAIL_DOMAIN, PSEUDONYM, BLACKOUT, BLUR), LABEL,
                 example="ayse.yilmaz@example.com"),
        DataType("adres", "Adres", "[ADRES]",
                 (GENERALIZE, ADDR_DISTRICT, ADDR_NEIGHBORHOOD, ADDR_REGION, BLACKOUT, LABEL, PSEUDONYM, BLUR), GENERALIZE,
                 method_labels=((GENERALIZE, "Sadece il"),),
                 example="Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy/İstanbul"),
        DataType("dogum_tarihi", "Doğum tarihi", "[TARIH]", (GENERALIZE, BIRTH_YEAR, BIRTH_AGE, BLACKOUT, LABEL, BLUR),
                 GENERALIZE, method_labels=((GENERALIZE, "On yıllık aralık"),), example="14.03.1987"),
        DataType("plaka", "Araç plakası", "[PLAKA]", (BLACKOUT, LABEL, PLATE_CITY, BLUR), BLACKOUT, example="34 ABC 123"),
        DataType("ip", "IP adresi", "[IP]", (LABEL, GENERALIZE, BLACKOUT, BLUR), LABEL,
                 method_labels=((GENERALIZE, "Alt ağ"),), example="10.20.30.45"),
        DataType("gizli_anahtar", "Gizli anahtar / Token", "[GIZLI ANAHTAR]", (BLACKOUT, LABEL, BLUR), BLACKOUT,
                 example="bb_ornek_anahtar_0000000000000000"),
        DataType("barkod_qr", "QR kod ve barkod", "[BARKOD/QR]", (BLACKOUT, LABEL, BLUR), BLACKOUT),
        DataType("imei", "IMEI (cihaz no)", "[IMEI]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT,
                 example="4901 5420 3237 518"),
        DataType("mac", "MAC adresi", "[MAC]", (LABEL, GENERALIZE, BLACKOUT, BLUR), LABEL,
                 method_labels=((GENERALIZE, "Üretici kısmı"),), example="aa:bb:cc:dd:ee:ff"),
        DataType("sase_no", "Şase no (VIN)", "[SASE NO]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT,
                 example="AAA0BBB1CCC2D3456"),
        DataType("tutar", "Tutar ve fiyat", "[TUTAR]", (GENERALIZE, BLACKOUT, LABEL, PSEUDONYM, BLUR), GENERALIZE,
                 default_enabled=False, method_labels=((GENERALIZE, "Aralık"),), example="12.500,00 TL"),
        DataType("pasaport", "Pasaport no", "[PASAPORT]", (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT,
                 example="U12345678"),
        DataType("mrz", "Kimlik / pasaport MRZ satırı", "[MRZ]", (BLACKOUT, LABEL, BLUR), BLACKOUT,
                 example="P<TURYILMAZ<<AYSE<<<<<<<<<<<<<<<<<<<<<<<<"),
        DataType("ehliyet", "Sürücü belgesi no", "[EHLIYET]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT,
                 example="123456"),
        DataType("gps", "GPS koordinatı", "[KONUM]", (BLACKOUT, LABEL, BLUR), BLACKOUT, example="41.0082, 28.9784"),
        DataType("kullanici_adi", "Kullanıcı adı / sosyal medya", "[KULLANICI]", (BLACKOUT, LABEL, PSEUDONYM, BLUR), LABEL,
                 example="@ornek_hesap"),
        DataType("unvan_kurum", "Unvan + kurum", "[UNVAN]", (BLACKOUT, LABEL, BLUR), LABEL,
                 default_enabled=False, example="Ankara İl Sağlık Müdürü"),
        DataType("sgk", "SGK / sicil no", "[SGK NO]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT,
                 example="1234567890123"),
        DataType("sicil_no", "Personel sicil no", "[SICIL NO]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT,
                 example="P-04571"),
        DataType("mersis", "MERSİS no", "[MERSIS]", (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT,
                 default_enabled=False, example="0123456789000015"),
        DataType("kurum_unvani", "Kurum / şirket unvanı", "[UNVAN]", (LABEL, BLACKOUT, PSEUDONYM, BLUR), LABEL,
                 default_enabled=False, example="Örnek Bilişim A.Ş."),
        DataType("vergi_dairesi", "Vergi dairesi", "[VERGI DAIRESI]", (BLACKOUT, LABEL, PSEUDONYM, BLUR), LABEL,
                 default_enabled=False, example="Çankaya"),
        DataType("ticaret_sicil", "Ticaret sicil no", "[TICARET SICIL]",
                 (BLACKOUT, LABEL, KEEP_LAST4, PSEUDONYM, BLUR), BLACKOUT, default_enabled=False, example="12345"),
        DataType("banka_bilgisi", "Banka / şube / hesap", "[BANKA]", (BLACKOUT, LABEL, PSEUDONYM, BLUR), BLACKOUT,
                 default_enabled=False, example="Örnek Bankası / Merkez Şb."),
        DataType("ettn", "ETTN / e-İmza bilgisi", "[ETTN / E-IMZA]", (BLACKOUT, LABEL, PSEUDONYM, BLUR), BLACKOUT,
                 default_enabled=False, example="12345678-1234-1234-1234-1234567890ab"),
        DataType("web_sitesi", "Web sitesi / alan adı", "[WEB]", (LABEL, BLACKOUT, BLUR), LABEL,
                 default_enabled=False, example="https://ornek.com.tr"),
        DataType("musteri_no", "Müşteri / poliçe no", "[MUSTERI NO]", (LABEL, KEEP_LAST4, PSEUDONYM, BLACKOUT, BLUR),
                 LABEL, example="MS-2026-004512"),
        DataType("yuz", "Yüz (fotoğraf)", "[YUZ]", (BLUR, BLACKOUT, LABEL), BLUR),
        DataType("imza", "İmza ve kaşe", "[IMZA]", (BLACKOUT, LABEL, BLUR), BLACKOUT),
        DataType("elle", "Elle seçilen alan", "[GIZLI]", (BLACKOUT, LABEL, BLUR), BLACKOUT, always_on=True),
        DataType("ozel_ifade", "Özel ifade", "[GIZLI]", (BLACKOUT, LABEL, BLUR), BLACKOUT),
        DataType("ozel_kalip", "Özel kalıp", "[GIZLI]", (BLACKOUT, LABEL, KEEP_LAST4, BLUR), BLACKOUT),
    )
}

METHOD_LABELS = {
    BLACKOUT: "Karartma",
    LABEL: "Etiket",
    KEEP_LAST4: "Son 4 hane açık",
    BLUR: "Bulanık",
    GENERALIZE: "Genelleştirme",
    ADDR_DISTRICT: "İl ve ilçe",
    ADDR_NEIGHBORHOOD: "Mahalle, ilçe, il",
    ADDR_REGION: "Sadece bölge",
    BIRTH_YEAR: "Yalnızca yıl",
    BIRTH_AGE: "Yaş aralığı",
    EMAIL_DOMAIN: "Alan adı açık",
    PLATE_CITY: "İl kodu açık",
    INITIALS: "Baş harfler",
    PSEUDONYM: "Takma ad",
}


def kacak_iletisi(turler: list[str], yer: str = "çıktıda") -> str:
    """Kaçak denetimi iletisi: kaç değer kaldı ve hangi türlerden (değerin kendisi yazılmaz; ileti arayüze ve
    günlüğe gider). Tür adları arayüzde tek tek çevrilir."""
    adlar = sorted({DATA_TYPES[k].label if k in DATA_TYPES else k for k in turler})
    return (
        f"Kaçak tespiti: maskelenmesi gereken {len(turler)} değer {yer} hâlâ okunuyor "
        f"({', '.join(adlar)}). Dosya yazılmadı."
    )


class RuleError(ValueError):
    """Kurallarda kullanıcıya gösterilecek bir hata."""


# Sütun kuralı olarak seçilemeyen türler: görsel/elle/özel türler bir sütunun türü olamaz.
COLUMN_EXCLUDED = ("yuz", "imza", "elle", "ozel_ifade", "ozel_kalip")


def header_key(header: str) -> str:
    """Sütun başlığını karşılaştırma anahtarına çevirir: "T.C." → "tc", "Telefon No" → "telefonno"."""
    from .extra_types import ascii_tr

    folded = ascii_tr(header.replace("İ", "i").replace("I", "i").replace("ı", "i")).casefold()
    return "".join(ch for ch in folded if ch.isalnum())


# Yerleşik varsayılan sütun başlığı sözlüğü: veri türü → başlıklar. Tam eşleşme
# aranır (header_key ile; büyük/küçük harf, boşluk/alt çizgi/tire ve Türkçe karakter duyarsız);
# "adres_tipi" gibi bileşik başlıklar eşleşmez.
DEFAULT_COLUMN_HEADERS: dict[str, tuple[str, ...]] = {
    "kisi_adi": (
        "ad", "isim", "adı", "soyad", "soyadı", "ad soyad", "adı soyadı", "ad_soyad", "adsoyad",
        "full name", "name", "first name", "last name", "surname",
    ),
    "telefon": ("telefon", "tel", "cep", "gsm", "phone", "mobile"),
    "eposta": ("e-posta", "eposta", "email", "e-mail", "mail"),
    "tc_kimlik": ("tc", "tc kimlik", "tckn", "kimlik no"),
    "iban": ("iban",),
    "adres": ("adres", "address"),
    "dogum_tarihi": ("doğum tarihi", "dogum_tarihi", "birth date"),
}


def _default_column_rules() -> dict[str, str]:
    return {header_key(h): t for t, hs in DEFAULT_COLUMN_HEADERS.items() for h in hs}


@dataclass
class TypeRule:
    enabled: bool
    method: str


@dataclass
class CustomPattern:
    name: str
    pattern: str
    compiled: Any = field(repr=False, compare=False, default=None)
    group: str = "diger"
    enabled: bool = True
    method: str = BLACKOUT
    mode: str = "etiket"
    hint: str = ""


@dataclass
class Rules:
    types: dict[str, TypeRule]
    terms: list[str] = field(default_factory=list)
    patterns: list[CustomPattern] = field(default_factory=list)
    whitelist: list[str] = field(default_factory=list)
    # Kurum sözlüğü: kurum adları ve genel unvanlar. Bu ifadelerin içinde kalan kişi adı ve
    # adres bulguları maskelenmez (örn. "Ahmet Yılmaz Anadolu Lisesi"nde kurum adı kişi sanılmaz).
    institutions: list[str] = field(default_factory=list)
    # İmza/kaşe aranacak etiketler ("İmza", "Kaşe" ...); bkz. signatures.py
    signature_labels: list[str] = field(default_factory=lambda: list(DEFAULT_SIGNATURE_LABELS))
    # Takma ad eşleme tablosu (kasadan; yalnızca bellekte). None ise takma ad kullanılamaz.
    pseudonyms: Any = field(default=None, repr=False, compare=False)
    # Takma ad kapsamı: False = aynı değer her belgede aynı takma ad (varsayılan);
    # True = her belgede yeni takma ad (belgeler arası bağlanabilirlik azalır).
    pseudonym_per_document: bool = False
    # Öğrenilen istisnalar (bkz. allowlist.py): değer özetleriyle eşleşen bulgular gelmez.
    allow: Any = field(default=None, repr=False, compare=False)
    # Excel/CSV sütun kuralları: başlık anahtarı (bkz. header_key) → veri türü. Başlığı eşleşen
    # sütunun dolu hücreleri, içeriğe bakılmadan o türden sayılır.
    column_rules: dict[str, str] = field(default_factory=dict)
    # Tablo sütun eylemleri (bkz. tablo.py): başlık anahtarı → "dolayli" | "yas" | "tarih".
    column_actions: dict[str, str] = field(default_factory=dict)
    # Yerleşik sütun başlığı sözlüğü açık mı (bkz. DEFAULT_COLUMN_HEADERS); takımın kendi kuralları önceliklidir.
    default_column_dictionary: bool = True
    k_threshold: int = 5  # k-anonimlik uyarı eşiği (dolaylı sütunlarda grup < k)
    age_limit: int = 90  # üstten kodlama eşiği: bu yaş ve üstü "90+"
    # Tarih kaydırma: iş (Rules örneği) başına sabit gün; ilk kullanımda rastgele seçilir.
    date_shift_days: int | None = field(default=None, repr=False)

    def shift_days(self) -> int:
        if self.date_shift_days is None:
            from .tablo import new_shift_days

            self.date_shift_days = new_shift_days()
        return self.date_shift_days
    # Tür bazında isteğe bağlı muafiyet/kural gerekçesi (ör. {"tc_kimlik": "KVKK Md.28"}).
    reasons: dict[str, str] = field(default_factory=dict)

    @classmethod
    def default(cls) -> Rules:
        rules = cls(types={k: TypeRule(t.default_enabled, t.default_method) for k, t in DATA_TYPES.items()})
        rules.column_rules = _default_column_rules()
        return rules

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Rules:
        rules = cls.default()
        if not data:
            return rules

        for key, value in (data.get("types") or {}).items():
            dt = DATA_TYPES.get(key)
            if dt is None:
                raise RuleError(f"Bilinmeyen veri türü: {key}")
            method = value.get("method", dt.default_method)
            if method not in dt.methods:
                raise RuleError(f"{dt.label} için geçersiz yöntem: {method}")
            rules.types[key] = TypeRule(bool(value.get("enabled", True)), method)

        # Sözlük kayıtlı takımlara veri göçü olmadan uygulanır; kapatmak için profilde false yazılır.
        rules.default_column_dictionary = data.get("varsayilan_sutun_sozlugu") is not False
        if not rules.default_column_dictionary:
            rules.column_rules = {}

        own: dict[str, str] = {}
        for item in data.get("column_rules") or []:
            header = str(item.get("header") or "").strip() if isinstance(item, dict) else ""
            action = str(item.get("action") or "").strip() if isinstance(item, dict) else ""
            if action:
                from .tablo import ACTIONS

                if action not in ACTIONS:
                    raise RuleError(f"Sütun kuralı için geçersiz eylem: {action}")
                if not header_key(header):
                    raise RuleError("Sütun kuralında başlık boş olamaz")
                rules.column_actions[header_key(header)] = action
                continue
            type_key = str(item.get("type") or "").strip() if isinstance(item, dict) else ""
            if not header_key(header):
                raise RuleError("Sütun kuralında başlık boş olamaz")
            if type_key not in DATA_TYPES or type_key in COLUMN_EXCLUDED:
                raise RuleError(f"Sütun kuralı için geçersiz veri türü: {type_key}")
            own[header_key(header)] = type_key
        rules.column_rules.update(own)  # takımın kendi kuralı sözlüğün önüne geçer

        for name, lo, hi in (("k_threshold", 2, 1000), ("age_limit", 18, 120)):
            if data.get(name) is not None:
                try:
                    value = int(data[name])
                except (TypeError, ValueError):
                    raise RuleError(f"{name} tam sayı olmalı") from None
                if not lo <= value <= hi:
                    raise RuleError(f"{name} {lo}-{hi} arasında olmalı")
                setattr(rules, name, value)

        rules.pseudonym_per_document = data.get("pseudonym_scope") == "belge"
        rules.terms = _clean_list(data.get("terms"))
        rules.whitelist = _clean_list(data.get("whitelist"))
        rules.institutions = _clean_list(data.get("institutions"))
        if data.get("signature_labels") is not None:
            rules.signature_labels = _clean_list(data.get("signature_labels"))

        raw_reasons = data.get("reasons")
        if isinstance(raw_reasons, dict):
            for k, v in raw_reasons.items():
                if k in DATA_TYPES and isinstance(v, str) and v.strip():
                    rules.reasons[str(k)] = v.strip()[:40]

        for item in data.get("patterns") or []:
            name = str(item.get("name") or "Özel kalıp").strip()
            pattern = str(item.get("pattern") or "")
            if not pattern:
                continue
            group = str(item.get("group") or "diger").strip() or "diger"
            enabled_flag = bool(item.get("enabled", True))
            method_val = str(item.get("method") or BLACKOUT).strip()
            if method_val not in (BLACKOUT, LABEL, KEEP_LAST4, BLUR):
                method_val = BLACKOUT
            mode_val = str(item.get("mode") or "etiket").strip()
            hint_val = str(item.get("hint") or "").strip()
            try:
                compiled = regex.compile(pattern, regex.IGNORECASE)
            except regex.error as exc:
                raise RuleError(f"'{name}' kalıbı geçersiz: {exc}") from None
            if compiled.search("", timeout=PATTERN_TIMEOUT) is not None:
                raise RuleError(f"'{name}' kalıbı boş metinle eşleşiyor; her yeri maskelerdi")
            rules.patterns.append(
                CustomPattern(
                    name,
                    pattern,
                    compiled,
                    group=group,
                    enabled=enabled_flag,
                    method=method_val,
                    mode=mode_val,
                    hint=hint_val,
                )
            )

        return rules

    def method_for(self, type_key: str, source: str = "") -> str:
        if type_key == "ozel_kalip" and source:
            for p in self.patterns:
                if p.name == source and getattr(p, "method", None):
                    return p.method
        return self.types[type_key].method

    def column_type(self, header: str) -> str | None:
        """Başlığa göre sütunun türü; kural yoksa ya da tür kapalıysa None."""
        key = self.column_rules.get(header_key(header)) if self.column_rules else None
        return key if key and self.types[key].enabled else None

    def column_action(self, header: str) -> str | None:
        return self.column_actions.get(header_key(header)) if self.column_actions else None

    def uses_pseudonyms(self) -> bool:
        return any(r.enabled and r.method == PSEUDONYM for r in self.types.values())

    def replacement_for(self, finding: Any, ascii_only: bool = True) -> str:
        """Bulgunun yerine yazılacak metin (türün seçili yöntemiyle; etiket modunda varsa muafiyet kodu)."""
        from .extra_types import ascii_tr
        from .mask import replacement  # döngüsel içe aktarmayı önlemek için burada

        source = getattr(finding, "source", "") or ""
        method = self.method_for(finding.type, source)
        if method == LABEL and (finding.type == "ozel_kalip" and source or self.reasons.get(finding.type)):
            from .extra_types import ascii_tr
        if finding.type == "ozel_kalip" and method == LABEL and source:
            etiket = f"[{source.upper()}]"
            return ascii_tr(etiket) if ascii_only else etiket
        reason = self.reasons.get(finding.type)
        if method == LABEL and reason:
            tag = f"[{reason.strip('[] ')}]"
            return ascii_tr(tag) if ascii_only else tag
        return replacement(finding, method, ascii_only, self.pseudonyms)


def _clean_list(values: Any) -> list[str]:
    seen: list[str] = []
    for v in values or []:
        s = str(v).strip()
        if s and s not in seen:
            seen.append(s)
    return seen


def describe_types() -> list[dict[str, Any]]:
    """Arayüzün kural ekranını çizmesi için veri türleri, yöntemler ve yöntem örnekleri."""
    from .detect import HIGH, Finding  # döngüsel içe aktarmayı önlemek için burada
    from .mask import replacement
    from .pseudonym import PREFIX as PSEUDONYM_PREFIX

    out = []
    for t in DATA_TYPES.values():
        if t.key in ("ozel_ifade", "ozel_kalip"):
            continue
        labels = dict(t.method_labels)
        methods = []
        for m in t.methods:
            sample = None
            if t.example:
                f = Finding(t.key, 0, len(t.example), t.example, HIGH)
                if m == PSEUDONYM:
                    sample = f"{PSEUDONYM_PREFIX.get(t.key, 'Değer')}-1"
                else:
                    sample = replacement(f, m, ascii_only=False) or None
            methods.append({"key": m, "label": labels.get(m, METHOD_LABELS[m]), "sample": sample})
        out.append(
            {
                "key": t.key,
                "label": t.label,
                "tag": t.tag,
                "always_on": t.always_on,
                "default_method": t.default_method,
                "example": t.example,
                "methods": methods,
            }
        )
    return out
