"""Tek yönlü maskeleme: bulgunun yerine ne yazılacağı.

Geri çevrilebilir yöntemler (takma ad) kasa ya da parolalı eşleme dosyası
gerektirir; bu modülde yoktur.

`ascii_only`: PDF'e yazılan metin PDF'in standart yazı tipiyle çizildiği için
Türkçe harf içeremez ("İstanbul" → "Istanbul"). XML, TXT, CSV ve Word'de
Türkçe harfler korunur.
"""

import re

from .detect import Finding
from .names import initials
from .extra_types import (
    address_level,
    age_range,
    amount_range,
    ascii_tr,
    birth_decade,
    year_capped,
    ip_subnet,
    mac_vendor,
)
from .rules import (
    ADDR_DISTRICT,
    ADDR_NEIGHBORHOOD,
    ADDR_REGION,
    BIRTH_AGE,
    BIRTH_YEAR,
    BLACKOUT,
    BLUR,
    DATA_TYPES,
    EMAIL_DOMAIN,
    GENERALIZE,
    INITIALS,
    KEEP_LAST4,
    LABEL,
    PLATE_CITY,
    PSEUDONYM,
    RuleError,
)
from .validators import digits_only

_ADDRESS_LEVEL = {GENERALIZE: "il", ADDR_DISTRICT: "il_ilce", ADDR_NEIGHBORHOOD: "mahalle", ADDR_REGION: "bolge"}


def replacement(finding: Finding, method: str, ascii_only: bool = True, pseudonyms=None) -> str:
    """Belgeye yazılacak metin. Karartmada boş döner (yalnızca siyah kutu).

    `pseudonyms`: takma ad yönteminde kullanılan eşleme tablosu (pseudonym.Pseudonyms).
    """
    if method == PSEUDONYM:
        if pseudonyms is None:
            raise RuleError("Takma ad için önce özel ifade kasasının kilidini açın")
        out = pseudonyms.label(finding.type, finding.value)
    else:
        out = _replacement(finding, method)
    return ascii_tr(out) if ascii_only else out


def _replacement(finding: Finding, method: str) -> str:
    if method in (BLACKOUT, BLUR):
        return ""
    if method == INITIALS:
        return initials(finding.value)
    if method == LABEL:
        return DATA_TYPES[finding.type].tag
    if method == KEEP_LAST4:
        digits = digits_only(finding.value)
        if len(digits) <= 4:
            return "****"
        return "**** " + digits[-4:]
    try:
        if finding.type == "adres" and method in _ADDRESS_LEVEL:
            return address_level(finding.value, _ADDRESS_LEVEL[method]) or DATA_TYPES["adres"].tag
        if method == BIRTH_YEAR:
            return year_capped(finding.value)
        if method == BIRTH_AGE:
            return age_range(finding.value)
        if method == EMAIL_DOMAIN:
            return "***@" + finding.value.rsplit("@", 1)[1]
        if method == PLATE_CITY:
            code = re.match(r"\d{2}", finding.value)
            return f"{code.group()} *** ***" if code else DATA_TYPES["plaka"].tag
    except (ValueError, AttributeError, IndexError):
        return DATA_TYPES[finding.type].tag
    if method == GENERALIZE:
        return generalize(finding)
    raise ValueError(f"Bilinmeyen yöntem: {method}")


def generalize(finding: Finding) -> str:
    """Değerin daha az ayrıntılı hâli; anlaşılamazsa türün etiketi."""
    try:
        if finding.type == "adres":
            return address_level(finding.value, "il") or DATA_TYPES["adres"].tag
        if finding.type == "dogum_tarihi":
            return birth_decade(finding.value)
        if finding.type == "ip":
            return ip_subnet(finding.value)
        if finding.type == "mac":
            return mac_vendor(finding.value)
        if finding.type == "tutar":
            src = f"{finding.value} {finding.source}" if finding.source in ("TRY", "USD", "EUR", "GBP", "TL") else finding.value
            return amount_range(src)
    except (ValueError, AttributeError, IndexError):
        pass
    return DATA_TYPES[finding.type].tag
