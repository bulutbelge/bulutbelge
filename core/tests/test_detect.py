import pytest

from bulutbelge_core.detect import detect
from bulutbelge_core.rules import RuleError, Rules
from bulutbelge_core.validators import iban_valid, luhn_valid, tc_kimlik_valid, vkn_valid

from fake_data import fake_card, fake_iban, fake_tc, fake_vkn


def types(text, rules=None):
    return [(f.type, f.value) for f in detect(text, rules or Rules.default())]


def test_validators_accept_fake_numbers():
    assert tc_kimlik_valid(fake_tc())
    assert vkn_valid(fake_vkn())
    assert iban_valid(fake_iban())
    assert luhn_valid(fake_card().replace(" ", ""))


def test_validators_reject_wrong_check_digits():
    tc = fake_tc()
    assert not tc_kimlik_valid(tc[:-1] + str((int(tc[-1]) + 1) % 10))
    assert not tc_kimlik_valid("0" + tc[1:])
    vkn = fake_vkn()
    assert not vkn_valid(vkn[:-1] + str((int(vkn[-1]) + 1) % 10))
    assert not iban_valid(fake_iban().replace("TR", "TR9", 1)[:-1])


def test_detects_builtin_types():
    tc, vkn, iban, card = fake_tc(), fake_vkn(), fake_iban(), fake_card()
    text = (
        f"TC: {tc}\nVKN: {vkn}\nIBAN: {iban}\nKart: {card}\n"
        "Tel: 0532 123 45 67\nSabit: +90 212 555 12 34\nE-posta: ayse.yilmaz@ornek.com.tr\n"
    )
    found = types(text)
    assert ("tc_kimlik", tc) in found
    assert ("vkn", vkn) in found
    assert ("iban", iban) in found
    assert ("kredi_karti", card) in found
    assert ("telefon", "0532 123 45 67") in found
    assert ("telefon", "+90 212 555 12 34") in found
    assert ("eposta", "ayse.yilmaz@ornek.com.tr") in found


def test_invalid_tc_is_only_uncertain():
    # Kontrol hanesi tutmayan TC kesin bulgu değildir; "emin olamadıklarımız" olarak gelir.
    tc = fake_tc()
    bad = tc[:-1] + str((int(tc[-1]) + 1) % 10)
    found = [f for f in detect(f"No: {bad}", Rules.default()) if f.type == "tc_kimlik"]
    assert [f.confidence for f in found] == ["dusuk"]


def test_disabled_type_is_skipped():
    rules = Rules.from_dict({"types": {"eposta": {"enabled": False, "method": "etiket"}}})
    assert types("a@ornek.com", rules) == []


def test_custom_terms_word_boundary_and_case():
    rules = Rules.from_dict({"terms": ["Ali Veli"]})
    found = types("ali veli geldi. Alive Veliler değil.", rules)
    assert found == [("ozel_ifade", "ali veli")]


def test_custom_pattern():
    rules = Rules.from_dict({"patterns": [{"name": "Proje kodu", "pattern": r"PRJ-\d{4}"}]})
    assert types("Kod: PRJ-0042", rules) == [("ozel_kalip", "PRJ-0042")]


def test_pattern_matching_empty_is_rejected():
    with pytest.raises(RuleError):
        Rules.from_dict({"patterns": [{"name": "boş", "pattern": r"\d*"}]})


def test_invalid_pattern_is_rejected():
    with pytest.raises(RuleError):
        Rules.from_dict({"patterns": [{"name": "bozuk", "pattern": "("}]})


def test_whitelist():
    rules = Rules.from_dict({"whitelist": ["info@kurum.com.tr"]})
    assert types("info@kurum.com.tr ve ali@ornek.com", rules) == [("eposta", "ali@ornek.com")]


def test_iban_wins_over_inner_numbers():
    found = types(f"IBAN {fake_iban()}")
    assert [t for t, _ in found] == ["iban"]


def test_imei_and_mac_detected_and_masked():
    from bulutbelge_core.mask import replacement

    text = "Cihaz IMEI 4901 5420 3237 518, MAC aa:bb:cc:dd:ee:ff"
    assert types(text) == [("imei", "4901 5420 3237 518"), ("mac", "aa:bb:cc:dd:ee:ff")]
    mac = detect(text, Rules.default())[1]
    assert replacement(mac, "genel") == "aa:bb:cc:**:**:**"
    assert replacement(mac, "etiket") == "[MAC]"
    imei = detect(text, Rules.default())[0]
    assert replacement(imei, "karartma") == ""


def test_amex_stays_card_not_imei():
    assert types("Kart 378282246310005") == [("kredi_karti", "378282246310005")]


def test_vin_detected_and_masked():
    from bulutbelge_core.mask import replacement

    text = "Araç şase no AAA0BBB1CCC2D3456 kayıtlı"
    assert types(text) == [("sase_no", "AAA0BBB1CCC2D3456")]
    vin = detect(text, Rules.default())[0]
    assert replacement(vin, "etiket") == "[SASE NO]"
    assert replacement(vin, "karartma") == ""

def test_sicil_no_detected_and_masked():
    from bulutbelge_core.mask import replacement

    text = "Personel sicil no: P-04571"
    assert types(text) == [("sicil_no", "P-04571")]
    sicil = detect(text, Rules.default())[0]
    assert replacement(sicil, "etiket") == "[SICIL NO]"
    assert replacement(sicil, "karartma") == ""


def test_sgk_sicil_still_sgk():
    text = "SGK sicil no 1234567890123"
    assert types(text) == [("sgk", "1234567890123")]


def test_gps_decimal_and_dms_detected():
    from bulutbelge_core.mask import replacement

    assert types("Konum: 41.0082, 28.9784 civarı") == [("gps", "41.0082, 28.9784")]
    dms = types("Nokta 41°0'29\"N 28°58'42\"E")
    assert [t for t, _ in dms] == ["gps"]
    gps = detect("41.0082, 28.9784", Rules.default())[0]
    assert replacement(gps, "etiket") == "[KONUM]"
    assert replacement(gps, "karartma") == ""


def test_gps_ignores_amounts_and_out_of_range():
    assert types("Oran 12.50, 30.25 olarak") == []
    assert [t for t, _ in types("Değer 95.1234, 20.1234")] == []
    assert [t for t, _ in types("Değer 45.1234, 200.1234")] == []


def test_gps_comma_decimal_lists_not_matched():
    assert types("Tutarlar 41,0082, 28,9784 ve 12,5000, 30,2500") == []
    assert types("Konum: 41,0082; 28,9784 civarı") == [("gps", "41,0082; 28,9784")]
    assert types("Konum: 41.0082; 28.9784") == [("gps", "41.0082; 28.9784")]


def test_social_handles_detected():
    from bulutbelge_core.mask import replacement

    assert ("kullanici_adi", "@ayse_yilmaz") in types("Instagram hesabı @ayse_yilmaz paylaştı")
    assert ("kullanici_adi", "ayse.y") in types("Kullanıcı adı: ayse.y")
    assert ("kullanici_adi", "ayseyilmaz") in types("Profil: https://twitter.com/ayseyilmaz")
    assert ("kullanici_adi", "alivelii") in types("linkedin.com/in/alivelii")
    handle = [f for f in detect("@ayse_yilmaz", Rules.default()) if f.type == "kullanici_adi"][0]
    assert replacement(handle, "etiket") == "[KULLANICI]"


def test_social_handle_not_email_or_number():
    kinds = [t for t, _ in types("Yazın: ali.veli@firma.com.tr")]
    assert "kullanici_adi" not in kinds
    assert "kullanici_adi" not in [t for t, _ in types("Kullanıcı adı: 123456")]


def _unvan_rules():
    rules = Rules.default()
    rules.types["unvan_kurum"].enabled = True
    return rules


def test_unvan_kurum_default_off_and_detected_when_on():
    assert "unvan_kurum" not in [t for t, _ in types("Ankara İl Sağlık Müdürü açıkladı")]
    got = types("dün Ankara İl Sağlık Müdürü açıkladı", _unvan_rules())
    assert ("unvan_kurum", "Ankara İl Sağlık Müdürü") in got
    got = types("bugün Örnek Yazılım A.Ş. Genel Müdürü toplantıya katıldı", _unvan_rules())
    assert ("unvan_kurum", "Örnek Yazılım A.Ş. Genel Müdürü") in got


def test_unvan_kurum_needs_institution():
    rules = _unvan_rules()
    assert "unvan_kurum" not in [t for t, _ in types("Müdür bey geldi, genel müdür yok", rules)]
    assert "unvan_kurum" not in [t for t, _ in types("Sayın Müdürü arayın", rules)]


def test_unvan_kurum_masked_with_label():
    from bulutbelge_core.mask import replacement

    f = [f for f in detect("Ankara İl Sağlık Müdürü", _unvan_rules()) if f.type == "unvan_kurum"][0]
    assert replacement(f, "etiket") == "[UNVAN]"
    assert replacement(f, "karartma") == ""


def test_kurum_sozlugu_kurum_adini_kisi_saymaz():
    metin = "Mehmet Akif Ersoy Anadolu Lisesi müdürü Deniz Kaya ile görüştü."
    assert ("kisi_adi", "Mehmet Akif Ersoy") in types(metin)
    rules = Rules.from_dict({"institutions": ["Mehmet Akif Ersoy Anadolu Lisesi"]})
    assert types(metin, rules) == [("kisi_adi", "Deniz Kaya")]


def test_kurum_sozlugu_numara_turlerini_etkilemez():
    tc = fake_tc()
    rules = Rules.from_dict({"institutions": [tc]})
    assert types(f"TC {tc}", rules) == [("tc_kimlik", tc)]


def test_kurum_sozlugu_kismi_ortusmede_maskeler():
    # Bulgu sözlük ifadesinden taşıyorsa (kişi adı + kurum) şüphede maskelenir.
    rules = Rules.from_dict({"institutions": ["Anadolu Lisesi"]})
    assert any(t == "kisi_adi" for t, _ in types("Adı Soyadı: Ayşe Yıldız Anadolu Lisesi öğrencisi.", rules))
