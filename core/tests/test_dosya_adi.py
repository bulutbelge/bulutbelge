"""Dosya adı hijyeni: yalnızca sahte adlarla."""

from bulutbelge_core.dosya_adi import has_person_name, scrub_name, scrub_path, suggest_masked_name


def test_detects_name_in_filename_variants():
    assert has_person_name("Ahmet Yılmaz sözleşme.pdf")
    assert has_person_name("ahmet_yilmaz-sozlesme.docx")
    assert has_person_name("AHMET_YILMAZ.xlsx")
    assert not has_person_name("sozlesme_taslak.pdf")
    assert not has_person_name("rapor 2024.pdf")


def test_scrub_name_keeps_extension_and_rest():
    assert scrub_name("Ahmet Yılmaz sözleşme.pdf") == "kisi sözleşme.pdf"
    assert scrub_name("ahmet_yilmaz-sozlesme.docx") == "kisi-sozlesme.docx"


def test_suggest_masked_name(tmp_path):
    src = tmp_path / "Ahmet Yılmaz sözleşme.pdf"
    assert suggest_masked_name(src) == str(tmp_path / "kisi sözleşme_maskeli.pdf")
    assert suggest_masked_name(tmp_path / "taslak.pdf") is None


def test_suggest_does_not_overwrite(tmp_path):
    (tmp_path / "kisi_maskeli.pdf").write_bytes(b"x")
    out = suggest_masked_name(tmp_path / "Ahmet_Yılmaz.pdf")
    assert out == str(tmp_path / "kisi_maskeli_2.pdf")


def test_scrub_path_all_segments():
    assert scrub_path("/home/Ahmet Yılmaz/belgeler/Ayşe Demir kira.pdf") == "/home/[kişi]/belgeler/[kişi] kira.pdf"
    assert scrub_path("C:\\Users\\Ahmet Yılmaz\\a.pdf") == "C:\\Users\\[kişi]\\a.pdf"
    assert scrub_path("/tmp/a.pdf") == "/tmp/a.pdf"


def test_scrub_path_windows_surucu_harfi_korunur():
    bs = chr(92)
    yol = bs.join(["C:", "Users", "Ahmet Yılmaz", "a.pdf"])
    assert scrub_path(yol).startswith("C:" + bs + "Users" + bs)
    assert scrub_path(bs.join(["D:", "belgeler", "x.pdf"])) == bs.join(["D:", "belgeler", "x.pdf"])


def test_mask_log_text_dosya_adi_ayraclari_korunur():
    from bulutbelge_core.dosya_adi import mask_log_text

    assert mask_log_text("Ayse_Yilmaz_CV.pdf", filename=True) == "[AD SOYAD]_CV.pdf"
    assert mask_log_text("Mehmet-Demir_kimlik.png", filename=True) == "[AD SOYAD]_kimlik.png"
    assert mask_log_text("rapor_2024.pdf", filename=True) == "rapor_2024.pdf"
    assert mask_log_text("", filename=True) == ""


def test_mask_log_text_amac_metni():
    from bulutbelge_core.dosya_adi import mask_log_text

    out = mask_log_text("Ahmet Yılmaz için kira, ahmet@ornek.com")
    assert "Ahmet" not in out and "ahmet@" not in out
    assert mask_log_text("denetim amaçlı") == "denetim amaçlı"
