"""Ad tespitinin ek yolları: ASCII yazım, e-posta ipucu, belge başlığı, yazım benzerliği (sahte veri)."""

from pathlib import Path

import pymupdf

from bulutbelge_core.detect import LOW, MEDIUM, detect
from bulutbelge_core.names import find_person_names, name_hints
from bulutbelge_core.pdf import mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

RULES = Rules.default()


def names(text, **kw):
    return [(f.value, f.confidence) for f in detect(text, RULES, **kw) if f.type == "kisi_adi"]


def test_dictionary_covers_more_names_and_ascii_spelling():
    for text in ("Resül Çatan", "Resul Catan", "RESÜL ÇATAN"):
        found = [text[a:b] for a, b, _ in find_person_names(text)]
        assert found == [text], text


def test_hints_from_email_local_part():
    assert name_hints(["ik: zenon.aydinoglu@example.com"]) == {"zenonaydinoglu", "zenon", "aydinoglu"}
    assert name_hints(["info@example.com iletisim@example.com ik@example.com"]) == frozenset()


def test_email_hint_masks_unknown_name_pair_and_lone_surname():
    text = "Zenon Aydınoğlu\nzenon.aydinoglu@example.com\n\nAydınoğlu görevi devraldı."
    hints = name_hints([text])
    found = names(text, hints=hints)
    assert ("Zenon Aydınoğlu", MEDIUM) in found
    assert ("Aydınoğlu", MEDIUM) in found
    # İpucu olmadan "Zenon" sözlükte olmadığı için yakalanmaz.
    assert names(text) == []


def test_email_hint_does_not_mask_lone_first_name_or_heading_words():
    text = "Ayşe teşekkür etti.\nKimlik fotokopisi\nE-posta: ayse.kimlik@example.com"
    assert names(text, hints=name_hints([text])) == []


def test_document_heading_is_a_low_confidence_candidate():
    page = "Tel\n0 532 000 00 00\nAdres\nKocaeli\nZenon Aydınoğlu\nMÜHENDİS / PLANLAMA UZMANI\nEğitim Bilgileri\nİş Deneyimleri"
    assert ("Zenon Aydınoğlu", LOW) in names(page, lead=True)
    assert names(page, lead=False) == []
    # Başlık satırları ad sanılmaz.
    assert all(v not in ("Eğitim Bilgileri", "İş Deneyimleri") for v, _ in names(page, lead=True))


def test_heading_needs_nearby_contact_or_title_line():
    assert names("Zenon Aydınoğlu\nBirinci paragraf.", lead=True) == []


def test_near_spelling_of_dictionary_name_is_low_confidence():
    found = names("Başvuran: Mehmedd Karaca ile görüşüldü.")
    assert ("Mehmedd Karaca", LOW) in found
    # Tek harf farkı olmayan sıradan sözcükler yakalanmaz.
    assert names("Genel Müdürlük kararı") == []


def _cv_pdf(path: Path) -> Path:
    doc = pymupdf.open()
    p = doc.new_page()
    y = 72
    for line in [
        "Adres",
        "Kocaeli",
        "Zenon Aydinoglu",
        "MUHENDIS / PLANLAMA UZMANI",
        "E-posta: zenon.aydinoglu@example.com",
    ]:
        p.insert_text((72, y), line, fontsize=11)
        y += 20
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Referans: Aydinoglu", fontsize=11)
    doc.save(path)
    doc.close()
    return path


def test_pdf_masks_name_via_email_hint_on_every_page(tmp_path):
    src = _cv_pdf(tmp_path / "cv.pdf")
    scan = scan_pdf(src, RULES)
    kinds = {(f.page, f.finding.type) for f in scan.findings}
    assert (1, "kisi_adi") in kinds and (2, "kisi_adi") in kinds
    res = mask_pdf(src, tmp_path / "out.pdf", RULES)
    out = pymupdf.open(res.target)
    try:
        text = "".join(pg.get_text() for pg in out)
    finally:
        out.close()
    assert "Zenon" not in text and "Aydinoglu" not in text and "example.com" not in text


def test_form_column_headers_after_name_label_are_not_names():
    text = "Referans Adı Soyadı Çalıştığı Firma Çalıştığı Firma Pozisyon Telefon E-posta"
    assert names(text) == []


def test_english_section_headings_are_not_heading_candidates():
    page = "Tel: 0 532 000 00 00\nWORK EXPERIENCE\nPersonal Information\nZenon Aydınoğlu\nPLANNING ENGINEER"
    found = [v for v, c in names(page, lead=True)]
    assert "WORK EXPERIENCE" not in found and "Personal Information" not in found
    assert "Zenon Aydınoğlu" in found


def test_english_school_and_institution_names_are_not_people():
    for text in ("Selcuk Esedoglu High School 2010", "Nuri Bayar Primary School", "Ahmet Yilmaz University"):
        assert names(text) == [], text


def test_email_hint_matches_lowercase_surname_next_to_name():
    text = "Referans\nZenon aydınoğlu\nzenon.aydinoglu@example.com"
    assert ("Zenon aydınoğlu", MEDIUM) in names(text, hints=name_hints([text]))


def test_first_name_plus_common_surname_in_lowercase():
    assert ("Taner şahin", MEDIUM) in names("Referans\nTaner şahin\nPorvil")
    # Sıradan küçük harfli sözcük soyad sayılmaz.
    assert names("Taner geldi") == []


def test_names_inside_web_addresses_are_masked():
    text = "Web: https://nuribayar.meb.k12.tr/ ve www.ahmetyilmaz.com ve http://ahmet.yilmaz.net/cv"
    found = [(f.value, f.confidence) for f in detect(text, RULES) if f.type == "kisi_adi"]
    assert ("nuribayar", MEDIUM) in found
    assert ("ahmetyilmaz", MEDIUM) in found
    assert ("ahmet.yilmaz", MEDIUM) in found


def test_company_and_service_domains_are_not_names():
    text = "https://demirbank.com https://www.google.com mail: ayse@gmail.com https://alibaba.com https://nurisoft.com.tr"
    found = [(f.value, f.confidence) for f in detect(text, RULES) if f.type == "kisi_adi"]
    # Alan adı sözcüğü eklenmiş ya da genel adresler maskelenmez; belirsiz olanlar yalnızca düşük güvenli.
    assert all(c != MEDIUM for _v, c in found), found
    assert not any(v in ("google", "gmail", "demirbank") for v, _c in found)


def test_pdf_masks_name_in_web_address(tmp_path):
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Web sitesi: https://nuribayar.meb.k12.tr/", fontsize=11)
    doc.save(tmp_path / "w.pdf")
    doc.close()
    res = mask_pdf(tmp_path / "w.pdf", tmp_path / "o.pdf", RULES)
    out = pymupdf.open(res.target)
    try:
        text = out[0].get_text()
    finally:
        out.close()
    assert "nuribayar" not in text.lower() and "meb.k12.tr" in text


def test_name_from_web_address_is_masked_everywhere_in_document(tmp_path):
    doc = pymupdf.open()
    p1 = doc.new_page()
    p1.insert_text((72, 72), "Web sitesi: https://nuribayar.meb.k12.tr/", fontsize=11)
    p2 = doc.new_page()
    p2.insert_text((72, 72), "Okul: Nuri Bayar Primary School", fontsize=11)
    doc.save(tmp_path / "w2.pdf")
    doc.close()
    res = mask_pdf(tmp_path / "w2.pdf", tmp_path / "o2.pdf", RULES)
    out = pymupdf.open(res.target)
    try:
        text = "".join(pg.get_text() for pg in out).lower().replace(" ", "")
    finally:
        out.close()
    assert "nuribayar" not in text


def test_surnameless_name_list_with_separators():
    for text, expected in (
        ("Kayıt Mustafa/Tuğçe tarafından silindi.", "Mustafa/Tuğçe"),
        ("Onaylayanlar: Ayşe, Fatma ve Ali.", "Ayşe, Fatma ve Ali"),
        ("Ali ve Veli toplantıya katıldı.", "Ali ve Veli"),
    ):
        assert (expected, MEDIUM) in names(text), text


def test_name_list_does_not_hit_ordinary_slash_pairs():
    for text in ("TCP/IP ayarı", "Giriş/Çıkış kaydı", "Alış/Satış, Ürün ve Hizmet", "ali/veli"):
        assert names(text) == [], text


def test_lone_first_name_masked_after_full_name_elsewhere():
    text = "Müşteri: Zeynep Karaman\n\nBaşvuruyu Zeynep inceledi.\nDeniz bugün izinli."
    found = names(text, hints=name_hints([text]))
    assert ("Zeynep", MEDIUM) in [f for f in found if f[0] == "Zeynep"]
    assert sum(1 for v, _ in found if v == "Zeynep") >= 1
    # Belgede ad soyadı geçmeyen sözlük adı tek başına maskelenmez.
    assert not any(v == "Deniz" for v, _ in found)
    assert names("Deniz bugün izinli.", hints=name_hints(["Deniz bugün izinli."])) == []


def test_lone_first_name_not_masked_without_document_hints():
    assert names("Başvuruyu Zeynep inceledi.") == []
