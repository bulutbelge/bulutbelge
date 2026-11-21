"""Güvenlik taraması 1. tur, regex ve ikinci dereceden döngü hizmet reddi (F1-F7, F9, F11, F17-F20, F22-F24).

İki tür sınama var:
- Karşılaştırma: eski desen (aşağıda metin olarak saklı) ile yenisi kısa, rastgele ve elle yazılmış
  girdilerde aynı eşleşmeleri verir. Kısa girdide eski desen de hızlıdır.
- Süre: sömürü girdisi küçük boyutta ve süre sınırı altında çalışır. Eski desenler bu girdilerde
  saniyelerden saatlere sürer; sınır aşılırsa `signal` ile kesilir, CPU kilitlenmez.

Tüm veriler sahtedir.
"""

from __future__ import annotations

import random
import re
import signal
import time
from contextlib import contextmanager

import pytest

from bulutbelge_core import detect as detect_mod
from bulutbelge_core import efatura, extra_types, ids, loose, names, tanima, textdoc
from bulutbelge_core.detect import Finding, detect
from bulutbelge_core.rules import Rules
from bulutbelge_core.xmltok import iter_tokens

LIMIT = 2.0  # saniye; yeni kod bu girdilerde milisaniyeler sürer


class _Slow(Exception):
    pass


@contextmanager
def deadline(seconds: float = LIMIT):
    """Süre aşılırsa kodu keser (re modülü uzun eşleşmede sinyalleri denetler) ve testi düşürür."""

    def _raise(signum, frame):
        raise _Slow

    old = signal.signal(signal.SIGALRM, _raise)
    signal.setitimer(signal.ITIMER_REAL, seconds * 2)
    t0 = time.perf_counter()
    try:
        yield
    except _Slow:
        pytest.fail(f"{seconds * 2:.0f} sn içinde bitmedi")
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)
    assert time.perf_counter() - t0 < seconds


def _spans(rx: re.Pattern[str], text: str) -> list[tuple]:
    return [(m.span(), m.groups()) for m in rx.finditer(text)]


def _random_texts(alphabet: str, count: int = 3000, max_len: int = 14, seed: int = 7) -> list[str]:
    rnd = random.Random(seed)
    return ["".join(rnd.choice(alphabet) for _ in range(rnd.randint(0, max_len))) for _ in range(count)]


# ---------- Eski desenler (karşılaştırma için) ----------

_DL = loose._DL
_OLD_IBAN_SEP = r"(?:[ .\-\u00a0]{0,2}(?:\r?\n){0,2}[ \u00a0]*)"
OLD_IBAN = re.compile(rf"(?<![\w])[Tt][Rr](?:{_OLD_IBAN_SEP}{_DL}){{24}}(?![\w])")
OLD_CARD_WRAP = re.compile(rf"(?<![\w]){_DL}(?:{_OLD_IBAN_SEP}{_DL}){{12,18}}(?![\w])")
OLD_NUM_WRAP = re.compile(rf"(?<![\w+])\+?{_DL}(?:{_OLD_IBAN_SEP}{_DL}){{9,18}}(?![\w])")
# Kısa girdide sınamak için tekrar sayısı küçültülmüş eşleri (ayırıcı aynı).
OLD_SEP_SHORT = re.compile(rf"(?<![\w])[Tt][Rr](?:{_OLD_IBAN_SEP}{_DL}){{3}}(?![\w])")
NEW_SEP_SHORT = re.compile(rf"(?<![\w])[Tt][Rr](?:{loose._IBAN_SEP}{_DL}){{3}}(?![\w])")

_OLD_IDS_SEP = r"(?:\s*(?:no\.?|numaras[ıi]|nr\.?|#)?\s*[:#\-]?\s*)"


def _old_labeled(labels: str, value: str) -> re.Pattern[str]:
    return re.compile(r"(?i)(?<![\w])(?:" + labels + r")" + _OLD_IDS_SEP + r"(" + value + r")(?![\w])")


OLD_PASSPORT = _old_labeled(r"pasaport|passport", r"[A-Z]{1,2}\d{6,8}")
OLD_SGK = _old_labeled(
    r"sgk(?:\s+sicil)?|ssk|sicil|işyeri\s+sicil|isyeri\s+sicil|sosyal\s+güvenlik", r"\d[\d \-]{6,30}\d"
)
OLD_MERSIS = _old_labeled(r"mers[iİı]s", r"0\d{3}[ \-]?\d{4}[ \-]?\d{4}[ \-]?\d{4}")
OLD_CUSTOMER = re.compile(
    r"(?i)(?<![\w])(?:müşteri|musteri|abone|abonelik|poliçe|police|sözleşme|sozlesme|hasta|protokol|dosya|"
    r"başvuru|basvuru|üye|uye|sipariş|siparis|kart\s+sahibi)"
    r"\s*(?:no\.?|numaras[ıi]|nr\.?|#|kodu)\s*[:#\-]?\s*"
    r"((?=[A-Z0-9\-]*\d)[A-Z0-9][A-Z0-9\-]{3,19})(?![\w])"
)
OLD_LABEL = re.compile(names._LABEL.pattern.replace(r"\s*(?:[:\-][ \t]*)?", r"\s*[:\-]?[ \t]*"))
OLD_SICIL = re.compile(
    r"(?i)\b(?:(?:personel|kurum|memur)?\s*sicil(?:\s+numarası)?)(?:\s*no\.?|\s*numarası)?\s*"
    r"[:#-]?\s*([a-zA-Z0-9-]{3,20})(?![a-zA-Z0-9])"
)
OLD_EFATURA_TOKEN = re.compile(
    r"<!--(?P<comment>.*?)-->"
    r"|<!\[CDATA\[(?P<cdata>.*?)\]\]>"
    r"|<\?.*?\?>"
    r"|(?P<tag><(?P<close>/)?(?P<name>[A-Za-z_][A-Za-z0-9_.:-]*)(?P<attrs>(?:\s+[^<>\"']*(?:\"[^\"]*\"|'[^']*'))*)\s*(?P<self>/)?>)",
    re.DOTALL,
)
OLD_BASE64 = re.compile(r"\s*[A-Za-z0-9+/=\s]{1000,}\s*")


def _old_resolve(findings: list[Finding]) -> list[Finding]:
    ordered = sorted(findings, key=lambda f: (-(f.end - f.start), detect_mod._PRIORITY[f.type], f.start))
    kept: list[Finding] = []
    for f in ordered:
        if all(f.end <= k.start or f.start >= k.end for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)


# ---------- Karşılaştırma: meşru ve rastgele girdide aynı sonuç ----------


def test_iban_separator_same_language():
    texts = _random_texts(" .-\u00a0\r\n1OTR", count=6000, max_len=12)
    texts += ["TR1 2 3", "TR1  2  3", "TR1.-2 .3", "TR1 -\n 2\r\n\r\n 3", "TR1\n\n\n2 3", "TR1 . 2 3", "TR123"]
    for t in texts:
        assert _spans(NEW_SEP_SHORT, t) == _spans(OLD_SEP_SHORT, t), repr(t)


@pytest.mark.parametrize(
    "text",
    [
        "IBAN: TR33 0006 1005 1978 6457 8413 26",
        "IBAN TR330006100519786457841326 ile",
        "TR33 0006 1005 1978\n6457 8413 26",
        "TR33-0006-1005-1978-6457-8413-26",
        "Kart: 4111 1111 1111\n1111",
        "Tel: 0532 123\n45 67",
        "TR33 0006 1005 1978 6457 8413 2",
    ],
)
def test_loose_wrapped_numbers_unchanged(text):
    assert _spans(loose._IBAN, text) == _spans(OLD_IBAN, text)
    assert _spans(loose._CARD_WRAP, text) == _spans(OLD_CARD_WRAP, text)
    assert _spans(loose._NUM_WRAP, text) == _spans(OLD_NUM_WRAP, text)


LABELED = [
    "Pasaport No: U12345678",
    "pasaport no U1234567",
    "Passport #: AB1234567",
    "Pasaport   -  U12345678",
    "Pasaport NO123456",
    "Pasaport No.:U12345678",
    "SGK sicil no 1234567890123",
    "SGK No: 1234 5678 9012",
    "Sicil numarası - 12345678",
    "MERSİS No: 0123-4567-8901-2345",
    "Mersis 0123456789012345",
    "Müşteri No: AB-12345",
    "müşteri numarası 98765",
    "Poliçe no. : 2024-55",
    "Abone # 1234-X",
    "Pasaport\n\nNo\n:\nU12345678",
]


@pytest.mark.parametrize("text", LABELED)
def test_ids_labeled_unchanged(text):
    for new, old in ((ids._PASSPORT, OLD_PASSPORT), (ids._SGK, OLD_SGK), (ids._MERSIS, OLD_MERSIS), (ids._CUSTOMER, OLD_CUSTOMER)):
        assert _spans(new, text) == _spans(old, text)


def test_ids_separator_random():
    texts = ["Pasaport" + t for t in _random_texts(" \n:#-noN.U1", count=4000, max_len=14)]
    texts += ["Müşteri" + t for t in _random_texts(" \n:#-noN.A1", count=4000, max_len=14, seed=11)]
    for t in texts:
        assert _spans(ids._PASSPORT, t) == _spans(OLD_PASSPORT, t), repr(t)
        assert _spans(ids._CUSTOMER, t) == _spans(OLD_CUSTOMER, t), repr(t)


NAME_TEXTS = [
    "Adı Soyadı: Ayşe Yılmaz",
    "Ad Soyad : Mehmet Ali Demir",
    "Sayın Fatma Kaya,",
    "Hasta:\tAli Veli",
    "Müşteri - Zeynep Arslan",
    "isim\n\nAhmet Öztürk",
    "name:   John Smith",
    "Kiracı: AHMET YILMAZ",
    "Ad-Soyad:Can Ersoy",
    "Hazırlayan \n Elif Şahin",
]


@pytest.mark.parametrize("text", NAME_TEXTS)
def test_name_label_unchanged(text):
    assert _spans(names._LABEL, text) == _spans(OLD_LABEL, text)


def test_name_label_random():
    for t in ("isim" + x for x in _random_texts(" \t\n:-AyYı", count=5000, max_len=14)):
        assert _spans(names._LABEL, t) == _spans(OLD_LABEL, t), repr(t)


SICIL_TEXTS = [
    "Personel sicil no: 12345",
    "sicil numarası - AB-123",
    "Kurum sicil: 9876",
    "memur sicil no.#A1B2",
    "Sicil   :   -123",
    "sicil 12",
]


@pytest.mark.parametrize("text", SICIL_TEXTS)
def test_sicil_unchanged(text):
    assert _spans(extra_types._SICIL_LABEL, text) == _spans(OLD_SICIL, text)


def test_sicil_random():
    for t in ("sicil" + x for x in _random_texts(" \n:#-noA1", count=5000, max_len=14)):
        assert _spans(extra_types._SICIL_LABEL, t) == _spans(OLD_SICIL, t), repr(t)


XML_TEXTS = [
    '<?xml version="1.0"?><Invoice xmlns="urn:x"><cbc:ID schemeID="VKN">1234567890</cbc:ID></Invoice>',
    "<a b='1'  c = \"2\" >x</a><!-- not --><![CDATA[ham <b> ]]><?pi x?>",
    '<a b="1"/><c/><d e="x>y">t</d>',
    "<!-- kapanmayan <a>x</a>",
    "<![CDATA[ kapanmayan <a>x</a>",
    "<? kapanmayan <a>x</a>",
    "<!-->x--><a>y</a>",
    '<a  "x">bozuk</a>',
    "metin < a > <1> </a>",
]


def _tokens_old(rx, text):
    return [(m.span(), m.groupdict()) for m in rx.finditer(text)]


def _tokens_new(rx, text):
    return [(m.span(), m.groupdict()) for m in iter_tokens(rx, text)]


@pytest.mark.parametrize("text", XML_TEXTS)
def test_xml_tokens_unchanged(text):
    assert _tokens_new(textdoc._TOKEN, text) == _tokens_old(textdoc._TOKEN, text)
    # e-Fatura: yalnızca adı olmayan bozuk öznitelik (`<a  "x">`) artık etiket sayılmaz.
    if '<a  "x">' not in text:
        assert _tokens_new(efatura._TOKEN, text) == _tokens_old(OLD_EFATURA_TOKEN, text)


def test_xml_tokens_random():
    for t in _random_texts("<>!-[]CDAT?/a \"'=x", count=6000, max_len=18):
        assert _tokens_new(textdoc._TOKEN, t) == _tokens_old(textdoc._TOKEN, t), repr(t)


def test_base64_same_language():
    body = "QUJD" * 300
    for t in (body, "  " + body + "\n", body + ".", " " * 1200, "x" * 999, "\n" + "A=" * 600):
        assert bool(textdoc._BASE64.fullmatch(t)) == bool(OLD_BASE64.fullmatch(t))


OLD_ORG_TITLE = re.compile(tanima._ORG_TITLE.pattern.replace(f"(?:[{tanima._L}][{tanima._L}']*[ \\t]+)", f"(?:[{tanima._L}']+[ \\t]+)"))


@pytest.mark.parametrize(
    "low",
    [
        "istanbul belediyesi başkanı ile görüşüldü",
        "sağlık bakanlığı genel müdürü, eğitim bakanlığı müfettişi",
        "belediyesi'nin başkanı, hastanesi başhekimi",
        "üniversitesi, tıp fakültesi dekanı",
        "kaymakamlığı ilçe şefi; şirketi'nin yeni genel müdürü",
        "bankası 'kurumsal' müdürü",
    ],
)
def test_org_title_legit_examples(low):
    assert OLD_ORG_TITLE.pattern != tanima._ORG_TITLE.pattern
    assert tanima._ORG_TITLE.findall(low) == OLD_ORG_TITLE.findall(low)
    assert tanima._ORG_TITLE.findall(low)


def test_resolve_overlaps_matches_old():
    types = list(detect_mod._PRIORITY)
    rnd = random.Random(3)
    for _ in range(400):
        fs = []
        for _ in range(rnd.randint(0, 25)):
            s = rnd.randint(0, 40)
            e = s + rnd.choice([0, 0, 1, 2, 3, 5, 8, 13])
            fs.append(Finding(rnd.choice(types), s, e, "x" * (e - s), "yuksek", "deneme"))
        assert detect_mod._resolve_overlaps(fs) == _old_resolve(fs)


def test_detect_legit_document_unchanged():
    text = (
        "Adı Soyadı: Ayşe Yılmaz\nTC: 10000000146\nIBAN: TR33 0006 1005 1978 6457 8413 26\n"
        "Pasaport No: U12345678\nTel: 0532 123 45 67\ne-posta: ayse.yilmaz@example.com\n"
    )
    got = {(f.type, f.value) for f in detect(text, Rules.default())}
    assert ("tc_kimlik", "10000000146") in got
    assert ("pasaport", "U12345678") in got
    assert any(t == "iban" for t, _ in got) and any(t == "kisi_adi" for t, _ in got)


# ---------- Süre: sömürü girdileri küçük boyutta ----------


def test_f1_f2_efatura_unclosed_tag():
    text = "<Invoice xmlns='urn:x'><a" + '  "x"' * 40 + "\n<b>1</b></Invoice>"
    with deadline():
        list(iter_tokens(efatura._TOKEN, text))
        efatura.scan_ubl_xml(text, Rules.default(), frozenset(), lead=True)


def test_f3_f5_iban_separator():
    text = "TR" + "  1" * 23 + "\n" + "TR1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1  1"
    with deadline():
        loose.find_mixed(text, card=True, vkn=True)


def test_f4_ids_whitespace():
    text = "Pasaport" + " " * 3000 + "!\nMüşteri no" + " " * 3000 + "!"
    with deadline():
        for fn in (ids.find_passports, ids.find_licences, ids.find_sgk, ids.find_mersis, ids.find_customer_numbers):
            list(fn(text))


def test_f6_f22_name_label_whitespace():
    text = "isim" + " " * 30000 + "x"
    with deadline():
        list(names.find_person_names(text))


def test_f7_many_findings():
    tc = "10000000146"
    text = "\n".join(f"{tc} 0532 123 45 67 a{i}@example.com" for i in range(6000))
    with deadline(LIMIT * 4):
        found = detect(text, Rules.default())
    assert len(found) >= 6000


def test_f9_f20_unclosed_comments():
    for opener in ("<!--", "<![CDATA[", "<?"):
        text = "<a>" + opener * 60000
        with deadline():
            textdoc._content_spans(text, "xml")
            list(iter_tokens(efatura._TOKEN, text))


def test_f11_long_capitalized_word():
    word = "A" + "".join(chr(ord("b") + i % 24) for i in range(60000))
    with deadline():
        names._near_first_name(word)
        list(names.find_name_candidates("Belge " + word + " Yılmaz"))


def test_f17_sicil_whitespace():
    text = "sicil" + " " * 30000 + "!"
    with deadline():
        list(extra_types.find_sicil_numbers(text))


def test_f18_long_url_token():
    text = "www." + "zq" * 200000 + ".com"
    with deadline():
        list(names.find_url_names(text))


def test_f19_base64_leading_whitespace():
    segment = " " * 20000 + "."
    with deadline():
        assert textdoc._BASE64.fullmatch(segment) is None
        textdoc._scan_text("<a>" + segment + "</a>", "xml", "utf-8", Rules.default())


def test_f23_f24_org_title_apostrophes():
    low = "belediyesi" + "'" * 50000
    with deadline():
        tanima._ORG_TITLE.findall(low)
        tanima.scan(low)
