import pytest

from bulutbelge_core.detect import HIGH, Finding, detect
from bulutbelge_core.mask import replacement
from bulutbelge_core.pseudonym import Pseudonyms, clean_table
from bulutbelge_core.rules import RuleError, Rules

ALL = Rules.from_dict({"types": {"mersis": {"enabled": True, "method": "karartma"}}})


def found(text, rules=ALL):
    return [(f.type, f.value) for f in detect(text, rules)]


@pytest.mark.parametrize(
    "text, name",
    [
        ("Ad Soyad: Ayşe Yılmaz", "Ayşe Yılmaz"),
        ("Sayın MEHMET DEMİR,", "MEHMET DEMİR"),
        ("Toplantıya Ali Çelik katıldı.", "Ali Çelik"),
        ("Ayşe Nur Yılmaz imzaladı", "Ayşe Nur Yılmaz"),
        ("Ad Soyad: Ayşe Yılmaz Telefon: 0532 000 12 34", "Ayşe Yılmaz"),
        ("Hasta: Can Öztürk", "Can Öztürk"),
    ],
)
def test_person_names(text, name):
    assert ("kisi_adi", name) in found(text)


@pytest.mark.parametrize(
    "text",
    ["Deniz Bank şubesi", "Fatih Sultan Mehmet Bulvarı", "Umut verici bir gelişme", "İşveren: Örnek Bilişim A.Ş.", "Ali Bey"],
)
def test_not_person_names(text):
    assert not any(t == "kisi_adi" for t, _ in found(text))


def test_institution_numbers_need_label():
    assert ("pasaport", "U12345678") in found("Pasaport No: U12345678")
    assert ("ehliyet", "123456") in found("Sürücü belgesi no: 123456")
    assert ("sgk", "1234567890123") in found("SGK sicil no: 1234567890123")
    assert ("mersis", "0123-4567-8900-0015") in found("MERSİS No: 0123-4567-8900-0015")
    assert ("musteri_no", "MS-2026-004512") in found("Müşteri No: MS-2026-004512")
    # Etiketsiz numaralar bu türlere girmez.
    assert not any(t in ("pasaport", "sgk", "musteri_no") for t, _ in found("Kod U12345678 ve 1234567890123"))


def test_mersis_off_by_default():
    assert not any(t == "mersis" for t, _ in found("MERSİS No: 0123456789000015", Rules.default()))


def test_initials():
    f = Finding("kisi_adi", 0, 0, "Ayşe Nur Yılmaz", HIGH)
    assert replacement(f, "bas_harf", ascii_only=False) == "A. N. Y."


def test_pseudonyms_are_consistent_and_reversible():
    p = Pseudonyms()
    a = Finding("kisi_adi", 0, 0, "Ayşe Yılmaz", HIGH)
    b = Finding("kisi_adi", 0, 0, "Mehmet Demir", HIGH)
    a2 = Finding("kisi_adi", 0, 0, "AYŞE  yılmaz", HIGH)
    assert replacement(a, "takma_ad", False, p) == "Kişi-1"
    assert replacement(b, "takma_ad", False, p) == "Kişi-2"
    assert replacement(a2, "takma_ad", False, p) == "Kişi-1"  # aynı kişi, farklı yazım
    assert replacement(a, "takma_ad", True, p) == "Kisi-1"  # PDF: ASCII
    tel1 = Finding("telefon", 0, 0, "0532 000 12 34", HIGH)
    tel2 = Finding("telefon", 0, 0, "+90 532 000 1234", HIGH)
    assert replacement(tel1, "takma_ad", False, p) == replacement(tel2, "takma_ad", False, p) == "Telefon-1"
    assert p.lookup("Kişi-2") == {"type": "kisi_adi", "value": "Mehmet Demir"}
    assert p.lookup("kisi-1")["value"] == "Ayşe Yılmaz"
    assert p.lookup("Kişi-9") is None
    # Kasaya yazılıp okunan tablo devam eder.
    again = Pseudonyms(clean_table(p.table))
    c = Finding("kisi_adi", 0, 0, "Zeynep Kaya", HIGH)
    assert replacement(c, "takma_ad", False, again) == "Kişi-3"


def test_pseudonym_needs_vault():
    with pytest.raises(RuleError):
        replacement(Finding("kisi_adi", 0, 0, "Ayşe Yılmaz", HIGH), "takma_ad")


def test_weak_label_needs_a_known_first_name():
    assert not any(t == "kisi_adi" for t, _ in found("MÜŞTERİ BAŞVURU FORMU"))
    assert not any(t == "kisi_adi" for t, _ in found("Müşteri Portföy Değerlendirmesi"))
    assert ("kisi_adi", "Ayşe Yılmaz") in found("Müşteri: Ayşe Yılmaz")
    assert ("kisi_adi", "Xavier Lopez") in found("Ad Soyad: Xavier Lopez")  # güçlü etiket: sözlük gerekmez


def test_customer_number_needs_no():
    assert not any(t == "musteri_no" for t, _ in found("Bireysel müşteri 2019'dan beri"))
    assert ("musteri_no", "88123456") in found("Poliçe no 88123456 yenileme")


def test_turkce_harfsiz_ad_ve_dosya_adi():
    from bulutbelge_core.paste import mask_filename

    assert mask_filename("C:/Belgeler/Ayse Yilmaz - sozlesme.pdf") == "[AD SOYAD] - sozlesme.pdf"
    assert mask_filename("Mehmet_Demir_bordro_2026.xlsx") == "[AD SOYAD] bordro 2026.xlsx"
    assert mask_filename("Ayşe Yılmaz - dilekçe.pdf") == "[AD SOYAD] - dilekçe.pdf"
    assert mask_filename("e-fatura.xml") == "e-fatura.xml"
    assert mask_filename("sozlesme-ali.veli@example.com.docx") == "[E-POSTA].docx"


def test_pseudonym_per_document_gives_new_label_but_stays_reversible():
    table = Pseudonyms()
    a = Finding("kisi_adi", 0, 0, "Ayşe Yılmaz", HIGH)
    assert replacement(a, "takma_ad", False, table) == "Kişi-1"
    # Varsayılan kapsam: ikinci belgede aynı kişi aynı takma adı alır.
    assert replacement(a, "takma_ad", False, Pseudonyms(clean_table(table.table))) == "Kişi-1"
    # Belge başına kapsam: aynı kişi yeni numara alır, belge içinde tutarlıdır.
    doc2 = Pseudonyms(clean_table(table.table), belge_basina=True)
    assert replacement(a, "takma_ad", False, doc2) == "Kişi-2"
    assert replacement(a, "takma_ad", False, doc2) == "Kişi-2"
    doc3 = Pseudonyms(clean_table(doc2.table), belge_basina=True)
    assert replacement(a, "takma_ad", False, doc3) == "Kişi-3"
    final = Pseudonyms(clean_table(doc3.table))
    assert final.lookup("Kişi-2") == {"type": "kisi_adi", "value": "Ayşe Yılmaz"}
    assert final.lookup("Kişi-3")["value"] == "Ayşe Yılmaz"
    # Yeni kişi sayaçta çakışmaz.
    b = Finding("kisi_adi", 0, 0, "Mehmet Demir", HIGH)
    assert replacement(b, "takma_ad", False, final) == "Kişi-4"


def test_restore_text_needs_open_vault_and_restores_labels():
    from bulutbelge_core.pseudonym import restore_text

    p = Pseudonyms()
    a = Finding("kisi_adi", 0, 0, "Ayşe Yılmaz", HIGH)
    b = Finding("kisi_adi", 0, 0, "Mehmet Demir", HIGH)
    t = Finding("telefon", 0, 0, "0532 000 12 34", HIGH)
    for f in (a, b, t):
        replacement(f, "takma_ad", False, p)
    text = "Kişi-1, Kişi-2'ye Telefon-1 ile ulaştı; kisi-1 ve Kisi-2 ASCII. Kişi-9 bilinmiyor, ÇKişi-1 ve Kişi-12 aynen kalır."
    out, n = restore_text(text, p)
    assert n == 5
    assert out == (
        "Ayşe Yılmaz, Mehmet Demir'ye 0532 000 12 34 ile ulaştı; Ayşe Yılmaz ve Mehmet Demir ASCII. "
        "Kişi-9 bilinmiyor, ÇKişi-1 ve Kişi-12 aynen kalır."
    )
    assert restore_text("Etiket yok", p) == ("Etiket yok", 0)
    with pytest.raises(RuleError):
        restore_text("Kişi-1", None)
