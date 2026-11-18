from bulutbelge_core.report import build_report, report_path
from bulutbelge_core.rules import Rules

from fake_data import fake_tc

TC = fake_tc()


def test_report_has_method_date_hash_purpose_and_no_values():
    rules = Rules.from_dict({})
    text = build_report(
        source="/gizli-klasor/ornek.pdf",
        source_sha256="a" * 64,
        target="/gizli-klasor/ornek_maskeli.pdf",
        target_sha256="b" * 64,
        counts={"tc_kimlik": 2},
        rules=rules,
        purpose="Dış denetçiye paylaşım",
        profile="Müşteriye",
        watermark=True,
        at="2026-11-16T10:00:00+03:00",
    )
    assert "2026-11-16T10:00:00+03:00" in text
    assert "Dış denetçiye paylaşım" in text
    assert "a" * 64 in text and "b" * 64 in text
    assert "tc_kimlik: 2 adet, yöntem:" in text
    assert "Filigran (MASKELİ KOPYA): var" in text
    assert "gizli-klasor" not in text and TC not in text  # yol ve değer girmez


def test_report_without_purpose_and_path_suffix():
    text = build_report(source="a.pdf", source_sha256=None, target="b.pdf", target_sha256=None, counts={})
    assert "belirtilmedi" in text and "gizlenen bilgi yok" in text
    assert report_path("/x/b.pdf").name == "b.pdf.gizleme-raporu.txt"


def test_report_cleanup_section_lists_counts_and_field_names_only():
    text = build_report(
        source="a.docx",
        source_sha256=None,
        target="b.docx",
        target_sha256=None,
        counts={},
        cleanup={"yazar": 2, "yorum": 1, "izlenen_silme": 3, "meta": ["yazar", "şirket"]},
    )
    assert "yazar adı: 2 adet" in text and "yorum: 1 adet" in text
    assert "izlenen silme (silinmiş metin kaldırıldı): 3 adet" in text
    assert "meta veri alanları: yazar, şirket" in text
    empty = build_report(source="a", source_sha256=None, target="b", target_sha256=None, counts={}, cleanup={})
    assert "temizlenecek gizli bilgi bulunmadı" in empty
    none = build_report(source="a", source_sha256=None, target="b", target_sha256=None, counts={})
    assert "Temizlenen gizli bilgiler" not in none


def test_report_dosya_adindaki_kisi_adini_yazmaz():
    text = build_report(
        source="/klasor/Ayşe Yılmaz - dilekçe.pdf",
        source_sha256="a" * 64,
        target="/klasor/Ayşe Yılmaz - dilekçe_maskeli.pdf",
        target_sha256="b" * 64,
        counts={"tc_kimlik": 1},
        rules=Rules.from_dict({}),
    )
    assert "Ayşe" not in text and "Yılmaz" not in text
    assert "dilekçe" in text and ".pdf" in text


def test_tanima_skoru_birlesim_etkisi_ve_rapor():
    from bulutbelge_core.tanima import scan, score

    metin = (
        "Ankara Büyükşehir Belediyesi müdürü, 42 yaşında bir avukat. İzmir'de 12.03.2020 tarihinde görev aldı."
    )
    sayim = scan(metin)
    assert set(sayim) == {"unvan_kurum", "meslek", "il", "yas", "tarih"}
    birlesik = score(sayim)
    tek = score({"il": 2})
    assert birlesik["puan"] > tek["puan"] and birlesik["duzey"] == "Yüksek"
    assert score({})["duzey"] == "Yok" and score({"il": 99})["katkilar"]["il"] == 6  # tekrar sınırlı

    text = build_report(
        source="a.txt", source_sha256=None, target="b.txt", target_sha256=None, counts={}, recognizability=birlesik
    )
    assert "Yeniden tanınabilirlik" in text and "Puan:" in text and "Yüksek" in text
    assert "Ankara" not in text and "avukat" not in text  # değer girmez
    assert "Yeniden tanınabilirlik" not in build_report(
        source="a.txt", source_sha256=None, target="b.txt", target_sha256=None, counts={}
    )


def test_baglanabilirlik_ortak_dolayli_ve_takma_ad():
    from bulutbelge_core.baglanabilirlik import analyze_texts, warning_lines

    a = "Kişi-3 İzmir'de 12.03.2020 tarihinde avukat olarak görev aldı."
    b = "Kişi-3 yine İzmir'de çalıştı. Kişi-9 ayrı biri."
    r = analyze_texts([a, b])
    assert r["duzey"] == "Yüksek" and r["takma_ad"]["ortak"] == 1 and r["dolayli"]["il"]["ortak"] == 1
    metin = "\n".join(warning_lines(r))
    assert "Bağlanabilirlik uyarısı" in metin and "İzmir" not in metin and "Kişi-3" not in metin

    assert analyze_texts([a]) is None  # tek belgede uyarı yok
    ayri = analyze_texts(["Kişi-1 Ankara'da.", "Kişi-2 Bursa'da."])
    assert ayri["duzey"] == "Yok" and warning_lines(ayri) == []
    assert analyze_texts(["Kişi-1 yazdı.", "Kişi-1 okudu."])["duzey"] == "Orta"
