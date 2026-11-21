from bulutbelge_core.detect import detect
from bulutbelge_core.extra_types import find_addresses, find_imeis, find_macs, find_sicil_numbers, find_vins, mac_vendor
from bulutbelge_core.mask import replacement
from bulutbelge_core.rules import Rules

ALL_ON = Rules.from_dict({"types": {"tutar": {"enabled": True, "method": "genel"}}})


def found(text, rules=ALL_ON):
    return {(f.type, f.value) for f in detect(text, rules)}


def rep(text, type_, rules=ALL_ON):
    f = next(f for f in detect(text, rules) if f.type == type_)
    return replacement(f, rules.method_for(type_))


def test_address_with_label_generalizes_to_province():
    text = "Adres: Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy/İstanbul\n"
    assert ("adres", "Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy/İstanbul") in found(text)
    assert rep(text, "adres") == "Istanbul"


def test_street_address_without_label_and_unknown_province():
    text = "Teslimat: Atatürk Cad. No: 5 Merkez\n"
    assert any(t == "adres" for t, _ in found(text))
    assert rep(text, "adres") == "[ADRES]"


def test_birth_date_needs_context():
    assert ("dogum_tarihi", "14.03.1987") in found("Doğum tarihi: 14.03.1987")
    assert ("dogum_tarihi", "3 Mart 1987") in found("D. Tarihi 3 Mart 1987")
    assert not any(t == "dogum_tarihi" for t, _ in found("Fatura tarihi: 14.03.2024"))
    assert rep("Doğum tarihi: 14.03.1987", "dogum_tarihi") == "1980-1989"


def test_plates():
    assert ("plaka", "34 ABC 123") in found("Araç: 34 ABC 123")
    assert ("plaka", "06 A 1234") in found("Plaka 06 A 1234 ile")
    assert ("plaka", "35BK1234") in found("35BK1234")
    assert not any(t == "plaka" for t, _ in found("99 AB 123"))  # 99 il kodu yok
    assert not any(t == "plaka" for t, _ in found("34 ab 123"))  # küçük harf


def test_ip_and_subnet():
    assert ("ip", "10.20.30.45") in found("Sunucu 10.20.30.45 üzerinde")
    assert not any(t == "ip" for t, _ in found("Sürüm 999.1.2.3"))
    assert rep("Sunucu 10.20.30.45", "ip") == "[IP]"
    gen = Rules.from_dict({"types": {"ip": {"enabled": True, "method": "genel"}}})
    assert rep("Sunucu 10.20.30.45", "ip", gen) == "10.20.30.0/24"


def test_amount_off_by_default_and_range():
    assert not any(t == "tutar" for t, _ in found("Bedel: 12.500,00 TL", Rules.default()))
    assert ("tutar", "12.500,00 TL") in found("Bedel: 12.500,00 TL")
    assert rep("Bedel: 12.500,00 TL", "tutar") == "10.000-100.000 TL"
    assert rep("Price $950", "tutar") == "100-1.000 $"


def test_manual_area_type_is_always_on():
    from bulutbelge_core.rules import DATA_TYPES, describe_types

    assert DATA_TYPES["elle"].always_on
    assert next(t for t in describe_types() if t["key"] == "elle")["always_on"]


def test_address_stops_at_csv_cell_separator():
    line = "Ayşe;TR33 0006 1005;34 ABC 123;Caferağa Mah. Moda Cad. No:12 Kadıköy/İstanbul;not"
    spans = list(find_addresses(line))
    assert [line[s:e] for s, e in spans] == ["Caferağa Mah. Moda Cad. No:12 Kadıköy/İstanbul"]


def test_address_levels():
    from bulutbelge_core.extra_types import address_level

    a = "Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy/İstanbul"
    assert address_level(a, "il") == "İstanbul"
    assert address_level(a, "il_ilce") == "Kadıköy/İstanbul"
    assert address_level(a, "mahalle") == "Caferağa Mah., Kadıköy/İstanbul"
    assert address_level(a, "bolge") == "Marmara Bölgesi"
    # İlçe yoksa il ile yetinilir; il yoksa None (yöntem etikete düşer).
    assert address_level("Moda Cad. No 3 İstanbul", "il_ilce") == "İstanbul"
    assert address_level("Atatürk Cad. No:5 Merkez", "il_ilce") is None
    # Virgülle ayrılmış yazım
    assert address_level("Lara Mahallesi Tekelioğlu Cad. No:22, Muratpaşa, Antalya", "mahalle") == (
        "Lara Mah., Muratpaşa/Antalya"
    )


def test_partial_methods_and_ascii_for_pdf():
    from bulutbelge_core.detect import HIGH, Finding

    addr = Finding("adres", 0, 0, "Kızılay Mah. Atatürk Bulvarı No:45 Çankaya/Ankara", HIGH)
    assert replacement(addr, "il_ilce") == "Cankaya/Ankara"  # PDF: ASCII
    assert replacement(addr, "il_ilce", ascii_only=False) == "Çankaya/Ankara"
    assert replacement(addr, "bolge", ascii_only=False) == "İç Anadolu Bölgesi"
    mail = Finding("eposta", 0, 0, "ayse@example.com", HIGH)
    assert replacement(mail, "alan_adi") == "***@example.com"
    plate = Finding("plaka", 0, 0, "06 ZK 4567", HIGH)
    assert replacement(plate, "plaka_il") == "06 *** ***"
    birth = Finding("dogum_tarihi", 0, 0, "14.03.1987", HIGH)
    assert replacement(birth, "yil") == "1987"


def test_age_range():
    from datetime import date

    from bulutbelge_core.extra_types import age_range

    assert age_range("14.03.1987", today=date(2026, 11, 4)) == "30-39 yaş"


def test_old_saved_profiles_still_load():
    # Eski profillerde adres yöntemi "genel" idi; hâlâ geçerli (= sadece il).
    rules = Rules.from_dict({"types": {"adres": {"enabled": True, "method": "genel"}}})
    assert rules.method_for("adres") == "genel"


def test_multiline_address_and_stacked_birth_date():
    text = "Doğum tarihi\n27.06.1994\nAdres\nAlsancak Mah. Kıbrıs Şehitleri Cad. No:8\n\nKonak/İzmir\n"
    items = found(text)
    assert ("dogum_tarihi", "27.06.1994") in items
    assert ("adres", "Alsancak Mah. Kıbrıs Şehitleri Cad. No:8\n\nKonak/İzmir") in items
    assert rep(text, "adres") == "Izmir"


IMEI = "490154203237518"


def spans(finder, text):
    return [text[s:e] for s, e in finder(text)]


def test_imei_formats():
    assert spans(find_imeis, f"IMEI: {IMEI}") == [IMEI]
    assert spans(find_imeis, "Cihaz 4901 5420 3237 518 kayıtlı") == ["4901 5420 3237 518"]
    assert spans(find_imeis, "Cihaz 49-015420-323751-8 kayıtlı") == ["49-015420-323751-8"]


def test_imei_rejects():
    for text in ("490154203237519", "49015420323751", "4901542032375180",
                 f"1{IMEI}", f"{IMEI}0", "378282246310005"):
        assert spans(find_imeis, text) == [], text


def test_imei_position_and_long_text():
    assert list(find_imeis(f"Telefon {IMEI} 2 adet")) == [(8, 23)]
    assert spans(find_imeis, "x" * 5000 + f" {IMEI}") == [IMEI]


def test_mac_formats():
    text = "a aa:bb:cc:dd:ee:ff b AA-BB-CC-DD-EE-FF c aabb.CCDD.eeff d"
    assert spans(find_macs, text) == ["aa:bb:cc:dd:ee:ff", "AA-BB-CC-DD-EE-FF", "aabb.CCDD.eeff"]
    assert list(find_macs("MAC: 0a:1b:2c:3d:4e:5f,")) == [(5, 22)]


def test_mac_rejects():
    for text in ("aa:bb-cc:dd:ee:ff", "aabbccddeeff", "aa:bb:cc:dd:ee:ff:00",
                 "00:aa:bb:cc:dd:ee:ff", "aabb.ccdd.eeff.0011", "gg:bb:cc:dd:ee:ff"):
        assert spans(find_macs, text) == [], text


def test_mac_vendor():
    assert mac_vendor("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:**:**:**"
    assert mac_vendor("AA-BB-CC-DD-EE-FF") == "AA-BB-CC-**-**-**"
    assert mac_vendor("aabb.ccdd.eeff") == "aabb.cc**.****"


VIN = "AAA0BBB1CCC2D3456"  # sahte


def test_vin_formats():
    assert spans(find_vins, f"Şase no: {VIN}") == [VIN]
    assert list(find_vins(f"Araç {VIN} kayıtlı")) == [(5, 22)]
    assert spans(find_vins, "x " * 3000 + VIN) == [VIN]


def test_vin_rejects():
    for text in (
        "aaa0bbb1ccc2d3456",  # küçük harf
        "AAA0BBB1CCI2D3456",  # I harfi
        "AAA0BBB1CCO2D3456",  # O harfi
        "AAA0BBB1CCQ2D3456",  # Q harfi
        "AAA0BBB1CC2D3456",  # 16 karakter
        "AAA0BBB1CCC2D34567",  # 18 karakter
        "12345678901234567",  # yalnız rakam
        "AAA0BBB1CCC2DABCD",  # son 4 rakam değil
        "XAAA0BBB1CCC2D3456",  # daha uzun dizinin parçası
    ):
        assert spans(find_vins, text) == [], text


def _sicil(text):
    return [text[s:e] for s, e in find_sicil_numbers(text)]


def test_sicil_no_pozitif():
    assert _sicil("Sicil No: 12345") == ["12345"]
    assert _sicil("Personel Sicil No: P-04571") == ["P-04571"]
    assert _sicil("sicil numarası 2019-0457 olan çalışan") == ["2019-0457"]
    assert _sicil("Kurum sicil #A7781") == ["A7781"]
    assert _sicil("memur sicil no: 88123") == ["88123"]


def test_sicil_no_negatif():
    assert _sicil("SGK sicil no 1234567890123") == []
    assert _sicil("işyeri sicil no 1234567") == []
    assert _sicil("Ticaret sicil no 123456") == []
    assert _sicil("sicil kaydı 2020 yılında açıldı") == []
    assert _sicil("Sicil No: 12345678") == []
    assert _sicil("sicil no: AB") == []
    assert _sicil("Sicil No 12") == []
    assert _sicil("sicil no: 12-") == []



# ---- 1.62 karışık yazım (yalnızca sahte değerler)


def test_mixed_tc_spaced_dotted_fullwidth_ocr():
    from fake_data import fake_tc

    tc = fake_tc("198765432")
    ocr = tc.replace("0", "O").replace("1", "l")
    fw = tc.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    for variant in (" ".join(tc), f"{tc[:3]}.{tc[3:6]}.{tc[6:9]}.{tc[9:]}", fw, ocr):
        assert ("tc_kimlik", variant) in found(f"TC: {variant} kayıtlı"), variant


def test_mixed_tc_invalid_checksum_not_flagged():
    assert not any(t == "tc_kimlik" and v != "12345678901" for t, v in found("No: 1 2 3 4 5 6 7 8 9 0 1"))
    assert not any(t == "tc_kimlik" for t, _ in found("Kod: l23 456 789 Ol"))


def test_mixed_iban_split_across_lines():
    from fake_data import fake_iban

    iban = fake_iban().replace(" ", "")
    text = f"IBAN:\n{iban[:14]}\n{iban[14:]}\n"
    assert ("iban", f"{iban[:14]}\n{iban[14:]}") in found(text)
    bad = iban[:-1] + str((int(iban[-1]) + 1) % 10)
    assert not any(t == "iban" and v.startswith("TR") and "\n" in v for t, v in found(f"{bad[:14]}\n{bad[14:]}"))


def test_mixed_phone_forms():
    assert ("telefon", "+90 (532) 000-12-34") in found("Tel: +90 (532) 000-12-34")
    assert ("telefon", "0532.000.12.34") in found("Tel: 0532.000.12.34")
    assert ("telefon", "０５３２０００１２３４") in found("Tel: ０５３２０００１２３４")
    assert not any(t == "telefon" for t, _ in found("Sürüm 5.3.2.0 yayında, SOS lol"))


def test_mixed_email_obfuscated():
    for t in ("ayse.test [at] ornek.com", "ayse.test(at)ornek[dot]com.tr", "ayse.test＠ornek.com", "ayse [@] ornek nokta com".replace(" nokta ", "[nokta]")):
        assert any(f.type == "eposta" for f in detect(f"İletişim: {t} adresi", ALL_ON)), t


def test_mixed_email_plain_word_at_not_flagged():
    assert not any(f.type == "eposta" for f in detect("toplantı at ornek.com saat 5", ALL_ON))


# ---- 1.62 hücreler arası bölünme ve satır sonu IBAN


def test_split_cells_tc_iban_phone():
    from bulutbelge_core.loose import find_split_cells
    from fake_data import fake_iban, fake_tc

    tc = fake_tc("198765432")
    assert find_split_cells(["Ad", tc[:3], tc[3:6], tc[6:9], tc[9:], "x"]) == [("tc_kimlik", 1, 4, "orta")]
    iban = fake_iban().replace(" ", "")
    cells = [iban[:4], iban[4:8], iban[8:16], iban[16:20], iban[20:]]
    assert find_split_cells(cells) == [("iban", 0, 4, "orta")]
    assert find_split_cells(["0532", "123 45 67"]) == [("telefon", 0, 1, "orta")]


def test_split_cells_false_positive_guards():
    from bulutbelge_core.loose import find_split_cells

    assert find_split_cells(["123", "456", "789", "02"]) == []  # kontrol hanesi tutmaz
    assert find_split_cells(["12", "34"]) == []
    assert find_split_cells(["5", "3", "2", "1", "2", "3", "4", "5", "6", "7"]) == []  # tek haneli telefon parçaları


def test_pdf_iban_wrap_with_trailing_space_and_hyphen():
    from bulutbelge_core.loose import find_mixed
    from fake_data import fake_iban

    raw = fake_iban().replace(" ", "")
    for sep in (" \n", "-\n", "\n\n"):
        text = f"IBAN: {raw[:14]}{sep}{raw[14:]} son"
        assert any(k == "iban" for k, *_ in find_mixed(text)), repr(sep)
def test_secrets_detected_with_low_false_positives():
    api = "sk-" + "ornek" * 5
    gh = "ghp_" + "A" * 24
    aws = "AKIA" + "0" * 16
    bb = "bb_" + "ornek_" + "0" * 16
    jwt = "eyJ" + "aGVsbG8" + "." + "eyJ" + "zdWIiOiIx" + "." + "imza12345678"
    db = "postgres://appuser:" + "sahteParola99" + "@db.local:5432/demo"
    pem = "-----BEGIN " + "PRIVATE KEY-----\nMIIBVQIBADANBgkqhkiG9w0=\n-----END PRIVATE KEY-----"

    text = "\n".join([api, gh, aws, bb, jwt, db, pem, "Sürüm: 1.2.3", "https://example.com/dokuman"])
    detected = found(text, Rules.default())
    for secret in (api, gh, aws, bb, jwt, db, pem):
        assert ("gizli_anahtar", secret) in detected
    assert not any(v in ("1.2.3", "https://example.com/dokuman") for _, v in detected)
    assert rep(f"Anahtar: {bb}", "gizli_anahtar", Rules.from_dict({"types": {"gizli_anahtar": {"enabled": True, "method": "etiket"}}})) == "[GIZLI ANAHTAR]"

