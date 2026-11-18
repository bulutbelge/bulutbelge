"""Özel nitelikli veri uyarısı (KVKK m.6, TAKIP 1.46). Tüm veriler sahtedir."""

from bulutbelge_core.ozel_nitelikli import scan_document, scan_special, special_warnings
from bulutbelge_core.readout import read_masked
from bulutbelge_core.report import build_report
from bulutbelge_core.rules import Rules


def test_categories_detected_with_turkish_suffixes_and_case():
    text = "Çalışan DİYABET hastalığı nedeniyle tedavi görüyor. Sendikaya üye. Sabıka kaydı yok."
    c = scan_special(text)
    assert c["Sağlık"] == 3
    assert c["Dernek, vakıf ve sendika üyeliği"] == 1
    assert c["Ceza mahkûmiyeti ve güvenlik tedbirleri"] == 1


def test_no_false_positive_on_similar_words():
    assert scan_special("Dinamik fiyat, dinç ekip, dinlenme tesisi, ırmak kenarı, araç kiralama") == {}


def test_warning_has_no_matched_word():
    w = special_warnings(scan_special("Kemoterapi görüyor"))
    assert len(w) == 1 and "Sağlık" in w[0] and "bulgu değildir" in w[0]
    assert "emoterapi" not in w[0]


def test_text_file_scan_and_readout_warning(tmp_path):
    p = tmp_path / "not.txt"
    p.write_text("Personel ameliyat oldu, rapor ekte.", encoding="utf-8")
    assert scan_document(p) == {"Sağlık": 1}
    r = read_masked(p, Rules.from_dict({}))
    assert any("KVKK m.6" in w for w in r.warnings)


def test_report_lists_category_without_values():
    t = build_report(source="a.txt", source_sha256=None, target="b.txt", target_sha256=None, counts={},
                     special={"Sağlık": 2})
    assert "Özel nitelikli veri uyarısı" in t and "Sağlık: 2 yerde" in t
    assert "KVKK" not in build_report(source="a.txt", source_sha256=None, target="b.txt", target_sha256=None, counts={})
