"""Vergi dairesi kalıbı tablo başlıklarını değer sanmasın (25 Kasım 2026 dekont bulgusu).

Vergi tahsil alındısı düzeninde "V.D.Kodu" başlığı değeri ayrı hücrede bekler; kalıp "Kodu" sözcüğünü vergi
dairesi adı sanıyor, aynı sözcük "İşlem Türü Kodu" başlığında kaldığı için kaçak denetimi kopyayı yazmıyordu.
Tüm veriler sahtedir.
"""

from __future__ import annotations

import pymupdf

from bulutbelge_core.detect import detect
from bulutbelge_core.pdf import mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules

SAHTE_VD = "KOZYATAĞI VERGİ DAİRESİ"

ALINDI = (
    "Borçlu Hesap\n:\nÖRNEK YAZILIM ANONİM ŞİRKETİ\n"
    "V.D.Kodu\nVergi Kimlik Numarası\nVer.T.K\nM.K.\nİşlem Türü Kodu\n041202\n"
    f"Vergi Dairesi\n:\n{SAHTE_VD}\n"
    "VERGİ TAHSİL ALINDISI\n"
)


def vd_rules() -> Rules:
    return Rules.from_dict({"types": {"vergi_dairesi": {"enabled": True, "method": "etiket"}}})


def test_vd_kodu_basligi_vergi_dairesi_sayilmaz():
    values = [f.value for f in detect(ALINDI, vd_rules()) if f.type == "vergi_dairesi"]
    assert values == [SAHTE_VD]


def test_yalniz_etiket_sozcugu_deger_sayilmaz():
    for text in ("V.D. Kodu\n123\n", "Vergi Dairesi Kodu: 034\n", "V.D.\nNo\n"):
        assert not [f for f in detect(text, vd_rules()) if f.type == "vergi_dairesi"], text


def test_olagan_yazimlar_bulunmaya_devam_eder():
    for text, beklenen in (
        ("Vergi Dairesi: Kadıköy   VKN: 1234567890\n", "Kadıköy"),
        ("V.D.: Başkent\n", "Başkent"),
        ("V.D. Kodlubahçe\n", "Kodlubahçe"),
    ):
        values = [f.value for f in detect(text, vd_rules()) if f.type == "vergi_dairesi"]
        assert values == [beklenen], text


def test_alindi_pdf_kacak_hatasi_olmadan_maskelenir(tmp_path):
    # Yerleşik Helvetica Türkçe harf basamadığı için PDF'te ASCII sahte metin.
    vd = "KOZYATAGI VERGI DAIRESI"
    lines = ["V.D.Kodu", "Vergi Kimlik Numarasi", "Islem Turu Kodu", "041202", "Vergi Dairesi", ":", vd]
    src = tmp_path / "alindi.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((60, 60 + 14 * i), line, fontname="helv", fontsize=10)
    doc.save(str(src))
    doc.close()

    rules = vd_rules()
    found = [f.finding.value for f in scan_pdf(src, rules).findings if f.finding.type == "vergi_dairesi"]
    assert found == [vd]

    out = tmp_path / "alindi_maskeli.pdf"
    mask_pdf(src, out, rules)  # önceden "Kaçak tespiti" ile duruyordu
    with pymupdf.open(str(out)) as masked:
        text = masked[0].get_text()
    assert "KOZYATAGI" not in text
    assert "V.D.Kodu" in text and "Islem Turu Kodu" in text


# ---- Bölünmüş kurum unvanı (aynı dekont bulgusu) ----

SAHTE_UNVAN = "ÖRNEK YAZILIM SİSTEM DANIŞMANLIK BİLGİSAYAR SANAYİ VE TİCARET LİMİTED ŞİRKETİ"
FORM = (
    f"Borçlu Hesap\n:\n11112222-5001 {SAHTE_UNVAN}\n"
    "Soyadı / Ünvanı\n:\nÖRNEK YAZILIM SİSTE\nAdı\n:\nM DANIŞMANLIK BİLGİS\n"
    "Açıklama\n:\nAYLIK BİLGİ GİRİŞİ\n"
)


def unvan_rules() -> Rules:
    return Rules.from_dict({"types": {"kurum_unvani": {"enabled": True, "method": "etiket"}}})


def test_bolunmus_unvan_parcalari_bulunur():
    values = [f.value for f in detect(FORM, unvan_rules()) if f.type == "kurum_unvani"]
    assert "ÖRNEK YAZILIM SİSTE" in values
    assert "M DANIŞMANLIK BİLGİS" in values
    # Unvanın parçası olmayan satır dokunulmaz.
    assert "AYLIK BİLGİ GİRİŞİ" not in values


def test_unvan_bulunmadiysa_parca_aranmaz():
    text = "Soyadı / Ünvanı\n:\nÖRNEK YAZILIM SİSTE\nAdı\n:\nM DANIŞMANLIK BİLGİS\n"
    assert not [f for f in detect(text, unvan_rules()) if f.type == "kurum_unvani"]
