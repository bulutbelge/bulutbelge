"""Ek veri türleri: adres, doğum tarihi, araç plakası, IP adresi, IMEI, MAC adresi, şase no, tutar.

Tasarım belgesindeki "Maskelenecek veri türleri" tablosunu izler. Her tür için
bir bulucu (metin → eşleşmeler) ve gerekiyorsa genelleştirme (değer → daha az
ayrıntılı değer) vardır:

- adres → yalnızca il ("Istanbul")
- doğum tarihi → on yıllık aralık ("1980-1989")
- IP → alt ağ ("10.20.30.0/24")
- MAC adresi → üretici kısmı ("aa:bb:cc:**:**:**")
- tutar → büyüklük aralığı ("10.000-100.000 TL")

Genelleştirilmiş metin PDF'in standart yazı tipiyle yazıldığı için ASCII'dir.
"""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Iterator

from .validators import luhn_valid

# 81 il. Eşleşme Türkçe karaktersiz yazımı da tanır (bkz. _fold).
ILLER = (
    "Adana Adıyaman Afyonkarahisar Ağrı Aksaray Amasya Ankara Antalya Ardahan Artvin Aydın Balıkesir "
    "Bartın Batman Bayburt Bilecik Bingöl Bitlis Bolu Burdur Bursa Çanakkale Çankırı Çorum Denizli "
    "Diyarbakır Düzce Edirne Elazığ Erzincan Erzurum Eskişehir Gaziantep Giresun Gümüşhane Hakkari Hatay "
    "Iğdır Isparta İstanbul İzmir Kahramanmaraş Karabük Karaman Kars Kastamonu Kayseri Kilis Kırıkkale "
    "Kırklareli Kırşehir Kocaeli Konya Kütahya Malatya Manisa Mardin Mersin Muğla Muş Nevşehir Niğde Ordu "
    "Osmaniye Rize Sakarya Samsun Şanlıurfa Siirt Sinop Sivas Şırnak Tekirdağ Tokat Trabzon Tunceli Uşak "
    "Van Yalova Yozgat Zonguldak"
).split()

_ASCII = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")


def _fold(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower().translate(_ASCII)


def ascii_tr(s: str) -> str:
    """PDF'e yazılacak metin için Türkçe harfleri ASCII karşılığına çevirir."""
    return s.translate(_ASCII)


_IL_BY_FOLD = {_fold(il): il for il in ILLER}

# ---------- Adres ----------

# "Adres:" etiketinden satır sonuna kadar ya da mahalle/cadde/sokak + "No" içeren satır parçası.
# Adres satır sonunda ve tablo hücresi ayracında (CSV'de ; ya da sekme, |) biter;
# aksi hâlde aynı satırdaki önceki hücreler (IBAN, plaka…) adres sanılırdı.
_A = r"[^\n;\t|]"
_ADDRESS_LABEL = re.compile(r"(?i)\b(?:adres|adresi|ikametgah|ikamet adresi)\s*:\s*(" + _A + r"{6,160})")
_ADDRESS_STREET = re.compile(
    r"(?i)(?P<pre>" + _A + r"{0,60}?)(?P<core>\b(?:mah(?:allesi)?\.?|cad(?:desi)?\.?|sok(?:ağı|ak|\.)?|bulvar(?:ı)?|blv\.?)"
    + _A + r"{0,80}\bno\s*[:.]?\s*\d+)(?P<post>" + _A + r"{0,60})"
)
# Kapı numarasından sonra adreste geçebilen küçük harfli sözcükler ve kısaltmalar.
_ADDRESS_TAIL_WORDS = {"kat", "daire", "d", "k", "blok", "apt", "apt.", "no", "iç", "kapı"}


def _street_span(text: str, m: re.Match[str]) -> tuple[int, int]:
    """Düz yazıda adresin önündeki ve arkasındaki cümle parçalarını ayıklar.

    "…numaram 123, adresim Alsancak Mah. … No:8 Konak/İzmir. Bana 0505…" içinden yalnızca
    "Alsancak Mah. … No:8 Konak/İzmir" kalır: önde son noktalama işaretinden sonrası, küçük
    harfle başlayan sözcükler atılarak; arkada cümle sonunda ya da adrese ait olmayan küçük harfli
    bir sözcükte durularak.
    """
    pre = m.group("pre")
    cut = max(pre.rfind(c) for c in ",:;.")
    seg = m.start("pre") + cut + 1
    start = m.start("core")
    for w in re.finditer(r"\S+", text[seg:start]):
        if not w.group()[0].islower():
            start = seg + w.start()  # ilk büyük harfli (ya da rakamla başlayan) sözcükten itibaren
            break
    end = m.end("core")
    for w in re.finditer(r"\S+", m.group("post")):
        token = w.group()
        bare = token.rstrip(".,").casefold()
        if token[0].islower() and bare.split(":")[0] not in _ADDRESS_TAIL_WORDS:
            break
        end = m.start("post") + w.end()
        if token.endswith(".") and bare not in _ADDRESS_TAIL_WORDS:
            break  # cümle sonu
    while end > start and text[end - 1] in ".,":
        end -= 1
    return start, end


_NEXT_LINE_PLACE = re.compile(r"[ \t]*\n(?:[ \t]*\n)?[ \t]*([^\n;\t|:0-9]{2,40}?)(?=[ \t]*(?:\n|$))")


def _extend_next_line_place(text: str, start: int, end: int) -> int:
    """Adresin il/ilçe bilgisi bir alt satıra yazılmışsa ('...No:8\\nKonak/İzmir') onu da kapsama alır."""
    if address_province(text[start:end]) is not None:
        return end
    m = _NEXT_LINE_PLACE.match(text, end)
    if not m:
        return end
    candidate = m.group(1).strip()
    if candidate and address_province(candidate) is not None:
        return m.end(1)
    return end


def find_addresses(text: str) -> Iterator[tuple[int, int]]:
    labeled = [(m.start(1), _extend_next_line_place(text, m.start(1), m.end(1))) for m in _ADDRESS_LABEL.finditer(text)]
    yield from labeled
    for m in _ADDRESS_STREET.finditer(text):
        s, e = _street_span(text, m)
        e = _extend_next_line_place(text, s, e)
        # "Adres:" etiketli satırı yukarıda aldık; etiket sözcüğü maskelenmesin.
        if not any(s < le and ls < e for ls, le in labeled):
            yield s, e


def address_province(value: str) -> str | None:
    """Adresteki son il adını döndürür ("Kadıköy/İstanbul" → "İstanbul")."""
    return address_parts(value)[2]


# Coğrafi bölgeler (adresi "yalnızca bölge" düzeyine indirmek için).
_BOLGELER = {
    "Marmara": "Balıkesir Bilecik Bursa Çanakkale Edirne İstanbul Kırklareli Kocaeli Sakarya Tekirdağ Yalova",
    "Ege": "Afyonkarahisar Aydın Denizli İzmir Kütahya Manisa Muğla Uşak",
    "Akdeniz": "Adana Antalya Burdur Hatay Isparta Kahramanmaraş Mersin Osmaniye",
    "İç Anadolu": "Aksaray Ankara Çankırı Eskişehir Karaman Kayseri Kırıkkale Kırşehir Konya Nevşehir Niğde Sivas Yozgat",
    "Karadeniz": "Amasya Artvin Bartın Bayburt Bolu Çorum Düzce Giresun Gümüşhane Karabük Kastamonu Ordu Rize "
    "Samsun Sinop Tokat Trabzon Zonguldak",
    "Doğu Anadolu": "Ağrı Ardahan Bingöl Bitlis Elazığ Erzincan Erzurum Hakkari Iğdır Kars Malatya Muş Tunceli Van",
    "Güneydoğu Anadolu": "Adıyaman Batman Diyarbakır Gaziantep Kilis Mardin Siirt Şanlıurfa Şırnak",
}
BOLGE_BY_IL = {il: bolge for bolge, iller in _BOLGELER.items() for il in iller.split()}

# İlçe sanılmaması gereken adres sözcükleri ("No", "Cad." gibi).
_NOT_DISTRICT = {
    _fold(w)
    for w in "mah mahalle mahallesi cad cadde caddesi sok sokak sokağı bulvar bulvarı blv no kat daire d apt "
    "apartmanı site sitesi blok adres merkez tr türkiye turkiye".split()
}
_MAHALLE = re.compile(r"((?:[^\W\d_][\w'’]*\.?\s+){0,2}?[^\W\d_][\w'’]*)\s+(Mah(?:allesi)?\.?)(?!\w)", re.IGNORECASE)


def address_parts(value: str) -> tuple[str | None, str | None, str | None]:
    """Adresi (mahalle, ilçe, il) parçalarına ayırır; bulunamayan parça None.

    İl, 81 il listesinden; ilçe, ilin hemen önündeki sözcükten ("Kadıköy/İstanbul",
    "Kadıköy İstanbul", "Kadıköy, İstanbul"); mahalle, "Mah." sözcüğünden önceki
    bir-üç sözcükten çıkarılır. İlçe listesi tutulmaz; ilin önündeki sözcük bir
    adres sözcüğü ya da sayıysa ilçe yok sayılır.
    """
    words = list(re.finditer(r"[^\W\d_]+", value))
    il = ilce = None
    for i, m in enumerate(words):
        found = _IL_BY_FOLD.get(_fold(m.group()))
        if not found:
            continue
        il, ilce = found, None
        if i > 0:
            prev = words[i - 1]
            between = value[prev.end():m.start()]
            # Yalnızca boşluk, "/" , "," ya da "-" ile ayrılmış, büyük harfle başlayan sözcük.
            if (
                re.fullmatch(r"\s*[/,-]?\s*", between)
                and prev.group()[0].isupper()
                and _fold(prev.group()) not in _NOT_DISTRICT
                and not _IL_BY_FOLD.get(_fold(prev.group()))
            ):
                ilce = prev.group()
    mahalle = None
    m = _MAHALLE.search(value)
    if m:
        mahalle = f"{m.group(1).strip()} Mah."
    return mahalle, ilce, il


def address_level(value: str, level: str) -> str | None:
    """Adresin istenen ayrıntı düzeyindeki hâli; il bulunamazsa None.

    level: "il" | "il_ilce" | "mahalle" (mahalle, ilçe, il; sokak ve kapı no gizli) | "bolge"
    """
    mahalle, ilce, il = address_parts(value)
    if not il:
        return None
    if level == "bolge":
        return f"{BOLGE_BY_IL[il]} Bölgesi"
    if level == "il" or not ilce and level == "il_ilce":
        return il
    place = f"{ilce}/{il}" if ilce else il
    if level == "mahalle" and mahalle:
        return f"{mahalle}, {place}"
    return place


# ---------- Doğum tarihi ----------

_MONTHS = "ocak şubat mart nisan mayıs haziran temmuz ağustos eylül ekim kasım aralık".split()
_DATE = (
    r"(?:(?:0?[1-9]|[12]\d|3[01])[ \t]*[./-][ \t]*(?:0?[1-9]|1[0-2])[ \t]*[./-][ \t]*(?:19|20)\d{2}"
    r"|(?:0?[1-9]|[12]\d|3[01])\s+(?:" + "|".join(_MONTHS) + r")\s+(?:19|20)\d{2})"
)
# Tarih, "doğum" bağlamından sonra (aynı satırda veya form/tablodaki alt satırda) en fazla 40 karakter içinde gelmeli.
_BIRTH = re.compile(
    r"(?i)(?:doğum\s*tarihi|doğum\s*t\.|d\.\s*tarihi|d\.\s*t\.|doğum|dogum\s*tarihi|dogum|date\s+of\s+birth|birth\s*date)"
    r"(?:[^\n\d]|\n(?!\n)){0,40}?(" + _DATE + r")"
)


def find_birth_dates(text: str) -> Iterator[tuple[int, int]]:
    for m in _BIRTH.finditer(text):
        yield m.start(1), m.end(1)


def birth_year(value: str) -> int:
    return int(re.findall(r"(?:19|20)\d{2}", value)[-1])


def birth_decade(value: str) -> str:
    year = birth_year(value)
    start = year - year % 10
    return f"{start}-{start + 9}"


AGE_CAP = 90  # bu yaş ve üstü ayrıca anılmaz ("90+"): çok yaşlılar az olduğu için kişiyi ele verir


def year_capped(value: str, today: "date | None" = None) -> str:
    """Doğum yılı; yaş AGE_CAP ve üstüyse yıl yerine "90+ yaş"."""
    from datetime import date

    year = birth_year(value)
    return f"{AGE_CAP}+ yaş" if (today or date.today()).year - year >= AGE_CAP else str(year)


def age_range(value: str, today: "date | None" = None) -> str:
    """Bugünkü yaşın on yıllık aralığı ("30-39 yaş"); yıl bazında yaklaşık."""
    from datetime import date

    age = (today or date.today()).year - birth_year(value)
    if age >= AGE_CAP:
        return f"{AGE_CAP}+ yaş"
    low = max(0, age - age % 10)
    return f"{low}-{low + 9} yaş"


# ---------- Araç plakası ----------

# 01-81 il kodu + harf + rakam: 1 harf/4 rakam, 2 harf/3-4 rakam, 3 harf/2-3 rakam.
# Türk plakalarında Q, W, X ve Türkçe harf yok; büyük harf zorunlu (yanlış eşleşmeyi azaltır).
_PLATE = re.compile(
    r"(?<![\w-])(0[1-9]|[1-7]\d|8[01])[ -]?"
    r"(?:([A-PR-VYZ])[ -]?(\d{4})|([A-PR-VYZ]{2})[ -]?(\d{3,4})|([A-PR-VYZ]{3})[ -]?(\d{2,3}))(?![\w-])"
)


def find_plates(text: str) -> Iterator[tuple[int, int]]:
    for m in _PLATE.finditer(text):
        yield m.start(), m.end()


# ---------- IP adresi ----------

_IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?(?![\d.])")
_IPV6 = re.compile(r"(?<![\w:])(?:[0-9A-Fa-f]{1,4}:){2,7}[0-9A-Fa-f]{0,4}(?![\w:])")


def find_ips(text: str) -> Iterator[tuple[int, int]]:
    for rx in (_IPV4, _IPV6):
        for m in rx.finditer(text):
            try:
                ipaddress.ip_interface(m.group())
            except ValueError:
                continue
            yield m.start(), m.end()


def ip_subnet(value: str) -> str:
    ip = ipaddress.ip_interface(value).ip
    prefix = 24 if ip.version == 4 else 64
    return str(ipaddress.ip_network(f"{ip}/{prefix}", strict=False))


# ---------- IMEI ----------
# 15 haneli, Luhn geçerli, 34/37 ile başlamayan; boşluk veya tire ayırabilir
_IMEI = re.compile(r"(?<!\d)\d(?:[ -]?\d){14}(?!\d)")


def find_imeis(text: str) -> Iterator[tuple[int, int]]:
    for m in _IMEI.finditer(text):
        cleaned = m.group().replace(" ", "").replace("-", "")
        if cleaned.startswith(("34", "37")):
            continue
        if not luhn_valid(cleaned):
            continue
        yield m.start(), m.end()


# ---------- MAC adresi ----------
# 6 bayt hex: aa:bb:cc:dd:ee:ff, aa-bb-cc-dd-ee-ff ya da Cisco aabb.ccdd.eeff; ayraç tek tip olmalı.
# Ayraçsız 12 hane MAC sayılmaz; 7 baytlık dizinin parçası alınmaz.
_HEX = "[0-9A-Fa-f]"
_MAC = re.compile(
    rf"(?<![0-9A-Fa-f:.-])(?:{_HEX}{{2}}([:-]){_HEX}{{2}}(?:\1{_HEX}{{2}}){{4}}"
    rf"|{_HEX}{{4}}\.{_HEX}{{4}}\.{_HEX}{{4}})(?![0-9A-Fa-f]|[:.-]{_HEX})"
)


def find_macs(text: str) -> Iterator[tuple[int, int]]:
    for m in _MAC.finditer(text):
        yield m.start(), m.end()


def mac_vendor(value: str) -> str:
    """MAC adresinin üretici kısmını maskeler."""
    if "." in value:
        return value[:7] + "**.****"
    sep = value[2]
    return value[:8] + (sep + "**") * 3


# ---------- Şase no (VIN) ----------
# 17 karakter, büyük harf ve rakam; I, O, Q kullanılmaz (ISO 3779).
# Son 4 karakter rakam olmalı ve en az bir harf bulunmalı (yalnız rakam dizileri başka türdür).
_VIN = re.compile(r"(?<![A-Za-z0-9])[A-HJ-NPR-Z0-9]{13}[0-9]{4}(?![A-Za-z0-9])")


def find_vins(text: str) -> Iterator[tuple[int, int]]:
    for m in _VIN.finditer(text):
        if not any(c.isalpha() for c in m.group()):
            continue
        yield m.start(), m.end()


# ---------- Personel/Kurum sicil numarası ----------
# Etiket zorunlu, büyük/küçük harf duyarsız: "sicil", "personel sicil", "kurum sicil", "memur sicil", "sicil numarası".
# Etiketten sonra isteğe bağlı "no", "no.", "numarası", ":", "#", "-" ve boşluklar gelebilir.
# Değer: harf, rakam ve tire; 3-20 karakter; en az bir rakam içerir; harf veya rakamla başlar ve biter; ardından harf/rakam gelmez.
# Etiketin hemen önünde "sgk", "ssk", "işyeri"/"isyeri" ya da "ticaret" sözcüğü varsa EŞLEŞME YOK.
# Değer tamamen rakamsa ve 8 veya daha fazla rakam içeriyorsa EŞLEŞME YOK (sgk türü onu zaten alıyor; çift tespit olmasın).
_SICIL_LABEL = re.compile(
    r"(?i)\b(?:(?:personel|kurum|memur)?\s*sicil(?:\s+numarası)?)(?:\s*no\.?|\s*numarası)?\s*"
    r"(?:[:#-]\s*)?([a-zA-Z0-9-]{3,20})(?![a-zA-Z0-9])"
)


def find_sicil_numbers(text: str) -> Iterator[tuple[int, int]]:
    for m in _SICIL_LABEL.finditer(text):
        value = m.group(1)
        label_start = m.start()
        value_start = m.start(1)
        value_end = m.end(1)
        if not any(c.isdigit() for c in value):
            continue
        if value.isdigit() and len(value) >= 8:
            continue
        pre_text = text[max(0, label_start - 20):label_start]
        words_before = list(re.finditer(r"\S+", pre_text))
        if words_before:
            last_word = words_before[-1].group().lower()
            if last_word in ("sgk", "ssk", "işyeri", "isyeri", "ticaret"):
                continue
        if not value[0].isalnum() or not value[-1].isalnum():
            continue
        yield value_start, value_end


# ---------- Tutar ----------

_CUR = r"(?:₺|TL|TRY|USD|EUR|GBP|\$|€|£)"
_DEC_NUM = r"\d{1,3}(?:\.\d{3})+[.,]\d{1,6}|\d{1,3}(?:,\d{3})+\.\d{1,6}|\d+[.,]\d{1,6}"
_NUM = r"(?:\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,6})?|\d+(?:[.,]\d{1,6})?)"
_AMOUNT = re.compile(
    r"(?<![\w.,])(?:"
    + _CUR + r"[^\S\r\n]{0,3}(?:" + _NUM + r")"
    + r"|(?:" + _DEC_NUM + r")(?:[^\S\r\n]{0,4}|[^\S\r\n]*\r?\n[^\S\r\n]{0,4})" + _CUR
    + r"|(?:" + _NUM + r")[^\S\r\n]{0,4}" + _CUR
    + r")(?![\w])"
)


def find_amounts(text: str) -> Iterator[tuple[int, int]]:
    for m in _AMOUNT.finditer(text):
        yield m.start(), m.end()


def _amount_number(value: str) -> float:
    num = re.search(_NUM, value).group()
    if "." in num and "," in num:
        if num.rfind(",") > num.rfind("."):
            return float(num.replace(".", "").replace(",", "."))
        return float(num.replace(",", ""))
    if "," in num:
        head, tail = num.rsplit(",", 1)
        if num.count(",") == 1 and (len(tail) != 3 or head == "0"):
            return float(f"{head}.{tail}")
        return float(num.replace(",", ""))
    if "." in num:
        head, tail = num.rsplit(".", 1)
        if num.count(".") == 1 and len(tail) != 3:
            return float(num)
        return float(num.replace(".", ""))
    return float(num)


def amount_range(value: str) -> str:
    cur = re.search(_CUR, value).group()
    n = _amount_number(value)
    low = 1
    while low * 10 <= n:
        low *= 10
    fmt = lambda x: f"{x:,}".replace(",", ".")  # noqa: E731
    return f"{fmt(low)}-{fmt(low * 10)} {cur}".replace("₺", "TL").replace("€", "EUR").replace("£", "GBP")


# ---------- GPS koordinatı ----------
# Ondalık çift ("41.0082, 28.9784") ya da derece-dakika-saniye ("41°0'29\"N 28°58'42\"E").
# Ondalıkta en az dört basamak ve geçerli aralık (enlem ±90, boylam ±180) aranır; "12.50, 30.25" gibi
# tutar/oran ikilileri eşleşmez. Virgül ondalık ayırıcı yalnızca ";" ayırıcılı çiftte kabul edilir;
# "41,0082, 28,9784" gibi virgüllü listeler eşleşmez.
_GPS_DECIMAL = re.compile(
    # nokta ondalıklı çift: virgül ya da noktalı virgülle ayrılır
    r"(?<![\d.,-])(-?\d{1,2}\.\d{4,})\s*[;,]\s*(-?\d{1,3}\.\d{4,})(?![\d.])"
    # virgül ondalıklı çift: yalnızca noktalı virgülle ayrılır ("41,0082, 28,9784" liste sayılır)
    r"|(?<![\d.,-])(-?\d{1,2},\d{4,})\s*;\s*(-?\d{1,3},\d{4,})(?![\d.,]\d)"
)
_GPS_DMS = re.compile(
    r"\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*\d{1,2}(?:[.,]\d+)?\s*[\"″]?\s*[NSEWKGDB]"
    r"[\s,;]+\d{1,3}\s*°\s*\d{1,2}\s*['′]\s*\d{1,2}(?:[.,]\d+)?\s*[\"″]?\s*[NSEWKGDB]\b"
)


def find_gps(text: str) -> Iterator[tuple[int, int]]:
    for m in _GPS_DECIMAL.finditer(text):
        lat = float((m.group(1) or m.group(3)).replace(",", "."))
        lon = float((m.group(2) or m.group(4)).replace(",", "."))
        if abs(lat) <= 90 and abs(lon) <= 180:
            yield m.start(), m.end()
    for m in _GPS_DMS.finditer(text):
        yield m.start(), m.end()


# ---------- Kullanıcı adı / sosyal medya ----------
# 1) "@kullanici" (e-posta adresinin içindeki @ sayılmaz),
# 2) "kullanıcı adı: x", "instagram: x", "twitter: x" gibi etiketli değer,
# 3) profil adresleri (twitter.com/x, instagram.com/x, linkedin.com/in/x ...).
# Yalnızca kullanıcı adı kısmı eşleşir (etiket ve alan adı açık kalır).
_HANDLE = r"[A-Za-z0-9_][A-Za-z0-9_.]{2,29}"
_SOCIAL_AT = re.compile(r"(?<![\w.@/])(@" + _HANDLE + r")(?![\w@])")
_SOCIAL_LABEL = re.compile(
    r"(?i)\b(?:kullan[ıi]c[ıi]\s*ad[ıi]|user\s*name|username|instagram|twitter|x\s*hesab[ıi]|tiktok|snapchat|"
    r"facebook|linkedin|telegram)\b\s*[:=\-]\s*@?(" + _HANDLE + r")(?![\w@])"
)
_SOCIAL_URL = re.compile(
    r"(?i)\b(?:(?:www\.)?(?:twitter|x|instagram|facebook|tiktok|t)\.(?:com|me)/|"
    r"(?:[a-z]{2,3}\.)?linkedin\.com/in/)@?(" + _HANDLE + r")(?![\w@])"
)


def find_social_handles(text: str) -> Iterator[tuple[int, int]]:
    seen: set[tuple[int, int]] = set()
    for pat, grp in ((_SOCIAL_AT, 1), (_SOCIAL_LABEL, 1), (_SOCIAL_URL, 1)):
        for m in pat.finditer(text):
            span = (m.start(grp), m.end(grp))
            # Yalnızca rakamdan oluşan etiketsiz değerler (sürüm, numara) kullanıcı adı sayılmaz.
            if pat is not _SOCIAL_AT and text[span[0]:span[1]].isdigit():
                continue
            if span not in seen:
                seen.add(span)
                yield span


# ---------- Unvan + kurum ----------
# "Ankara İl Sağlık Müdürü", "Örnek Yazılım A.Ş. Genel Müdürü": kurum adı ve unvan birlikte kişiyi dolaylı
# tanımlar (makam tek kişidir). Eşleşme kurum adı (büyük harfle başlayan 1-6 sözcük) + unvan sözcüğüdür;
# kurum adı olmadan yalnızca unvan ("Müdür Bey", "genel müdür") eşleşmez.
_UNVANLAR = (
    "Genel Müdür Yardımcısı|Genel Müdürü|Genel Müdür|Müdür Yardımcısı|Müdürü|Müdür|Başkan Yardımcısı|Başkanı|Başkan|"
    "Başhekimi|Başhekim|Valisi|Vali|Kaymakamı|Kaymakam|Belediye Başkanı|Rektörü|Rektör|Dekanı|Dekan|"
    "Başsavcısı|Başsavcı|Savcısı|Hâkimi|Hakimi|Komutanı|Komutan|Müfettişi|Müfettiş|Sorumlusu|"
    "Yönetim Kurulu Başkanı|Murahhas Üyesi|CEO|CFO|CTO"
)
_UNVAN_SOZ = r"[A-ZÇĞİÖŞÜ][\wçğıöşüÇĞİÖŞÜ.'’-]*"
_UNVAN_YASAK = {"sayın", "bay", "bayan", "sn", "sn.", "say", "bu", "bir", "şu", "o", "ve", "ile"}
_UNVAN_KURUM = re.compile(
    r"(?<![\wçğıöşüÇĞİÖŞÜ])(?P<kurum>(?:" + _UNVAN_SOZ + r"[ \t]+){1,6}?)(?P<unvan>(?:" + _UNVANLAR + r"))(?![\wçğıöşüÇĞİÖŞÜ])"
)


def find_title_institution(text: str) -> Iterator[tuple[int, int]]:
    for m in _UNVAN_KURUM.finditer(text):
        words = m.group("kurum").split()
        # Cümle başındaki "Sayın" gibi sözcükler kurum adı sayılmaz; baştan atılır.
        skip = 0
        while skip < len(words) and words[skip].lower() in _UNVAN_YASAK:
            skip += 1
        if skip == len(words):
            continue
        start = m.start("kurum")
        for w in words[:skip]:
            start = text.index(w, start) + len(w)
        yield start, m.end("unvan")
# ---------- Gizli anahtar / Token ----------

_PEM_KEY = re.compile(
    r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----[\s\S]{10,4096}?-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----"
)
_API_TOKEN = re.compile(
    r"(?<![A-Za-z0-9_-])(?:"
    r"sk-(?:proj-|ant-|live-|test-)?[A-Za-z0-9_-]{20,}"
    r"|gh[pou]_[A-Za-z0-9]{20,}"
    r"|github_pat_[A-Za-z0-9_]{20,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r"|xox[baprs]-[0-9A-Za-z-]{16,}"
    r"|bb_[A-Za-z0-9_-]{16,}"
    r")(?![A-Za-z0-9_-])"
)
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])eyJ[A-Za-z0-9_-]{6,}\.eyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
_DB_URI = re.compile(
    r"(?i)\b(?:postgres(?:ql)?|mysql|mariadb|mongodb(?:\+srv)?|redis|amqp|mssql)"
    r"://[^:/\s@]{1,64}:[^@\s/]{4,128}@[^\s\"'<>]+"
)


def find_secrets(text: str) -> Iterator[tuple[int, int]]:
    """API anahtarları, JWT, PEM özel anahtarları ve parola içeren veritabanı URI'lerini bulur."""
    spans: list[tuple[int, int]] = []
    for rx in (_PEM_KEY, _API_TOKEN, _JWT, _DB_URI):
        for m in rx.finditer(text):
            spans.append((m.start(), m.end()))
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    last_end = -1
    for start, end in spans:
        if start >= last_end:
            yield start, end
            last_end = end

