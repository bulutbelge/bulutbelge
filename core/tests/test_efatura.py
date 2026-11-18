"""e-Fatura (PDF, imzalı UBL XML ve ZIP arşivi) ve e-fatura kural seti testleri."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
import xml.etree.ElementTree as ET

import pymupdf
import pytest
from PIL import Image, ImageDraw

from bulutbelge_core.archive import mask_archive, read_archive_text, scan_archive
from bulutbelge_core.detect import detect
from bulutbelge_core.documents import kind_of
from bulutbelge_core.pdf import PdfError, mask_pdf, scan_pdf
from bulutbelge_core.profiles import builtin_profiles
from bulutbelge_core.pseudonym import Pseudonyms
from bulutbelge_core.rules import Rules
from bulutbelge_core.textdoc import mask_text_doc, scan_text_doc

from fake_data import fake_iban, fake_tc

VKN_SATICI = "1234567890"
VKN_ALICI = "0987654321"
MERSIS_SATICI = f"0{VKN_SATICI}00015"
TC_SAHIS = fake_tc()
IBAN_ORNEK = fake_iban()
IBAN_TR_BOSLUK = f"TR {IBAN_ORNEK[2:4]} " + " ".join(IBAN_ORNEK.replace(" ", "")[4:][i:i+4] for i in range(0, 22, 4))
ETTN_ORNEK = "11111111-2222-3333-4444-555555555555"


def efatura_rules(*, pseudonym: bool = False) -> Rules:
    prof = next(p for p in builtin_profiles() if p["id"] == "efatura")
    r = Rules.from_dict(prof)
    if pseudonym:
        for k, tr in list(r.types.items()):
            from bulutbelge_core.rules import DATA_TYPES, PSEUDONYM, TypeRule

            if tr.enabled and PSEUDONYM in DATA_TYPES[k].methods:
                r.types[k] = TypeRule(True, PSEUDONYM)
        r.pseudonyms = Pseudonyms()
    return r


def _fake_qr_png() -> bytes:
    """Siyah-beyaz karekod benzeri sentetik görsel üretir."""
    im = Image.new("L", (120, 120), 255)
    draw = ImageDraw.Draw(im)
    for y in range(0, 120, 10):
        for x in range(0, 120, 10):
            if ((x // 10) + (y // 10)) % 2 == 0 or (x < 30 and y < 30):
                draw.rectangle([x, y, x + 8, y + 8], fill=0)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _fake_ubl_xml() -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2"
         xmlns:ext="urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2"
         xmlns:ds="http://www.w3.org/2000/09/xmldsig#"
         xmlns:xades="http://uri.etsi.org/01903/v1.3.2#">
  <ext:UBLExtensions>
    <ext:UBLExtension>
      <ext:ExtensionContent>
        <ds:Signature Id="Signature_4111111111111111">
          <ds:SignedInfo>
            <ds:Reference URI="#SignedProperties_1111">
              <ds:DigestValue>abcDEF1234567890+/==</ds:DigestValue>
            </ds:Reference>
          </ds:SignedInfo>
          <ds:SignatureValue>{"SigVal" * 40}</ds:SignatureValue>
          <ds:KeyInfo>
            <ds:X509Data>
              <ds:X509Certificate>{"MIIBIjANBgkq" * 120}</ds:X509Certificate>
            </ds:X509Data>
          </ds:KeyInfo>
          <ds:Object>
            <xades:QualifyingProperties Target="#Signature_4111111111111111">
              <xades:SignedProperties>
                <xades:SignedSignatureProperties>
                  <xades:SigningTime>2026-11-16T10:15:30+03:00</xades:SigningTime>
                  <xades:SigningCertificate>
                    <xades:Cert>
                      <xades:IssuerSerial>
                        <ds:X509IssuerName>CN=Ornek Kamu SM Mali Muhur</ds:X509IssuerName>
                        <ds:X509SerialNumber>9876543210987654</ds:X509SerialNumber>
                      </xades:IssuerSerial>
                    </xades:Cert>
                  </xades:SigningCertificate>
                </xades:SignedSignatureProperties>
              </xades:SignedProperties>
            </xades:QualifyingProperties>
          </ds:Object>
        </ds:Signature>
      </ext:ExtensionContent>
    </ext:UBLExtension>
  </ext:UBLExtensions>
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>TICARIFATURA</cbc:ProfileID>
  <cbc:ID>ABC2026000012345</cbc:ID>
  <cbc:UUID>{ETTN_ORNEK}</cbc:UUID>
  <cbc:IssueDate>2026-11-16</cbc:IssueDate>
  <cbc:Note>Yalnız DörtBin AltıYüz TL Sıfır Kuruş</cbc:Note>
  <cac:AdditionalDocumentReference>
    <cbc:ID>Dört Bin Altı Yüz TL</cbc:ID>
    <cbc:DocumentType>TOTAL_NET_STR</cbc:DocumentType>
  </cac:AdditionalDocumentReference>
  <cac:AdditionalDocumentReference>
    <cbc:ID>{ETTN_ORNEK}</cbc:ID>
    <cbc:DocumentType>XSLT</cbc:DocumentType>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject filename="{ETTN_ORNEK}.xslt">{"PD94bWwg" * 200}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cbc:WebsiteURI>www.ornek-yazilim.example</cbc:WebsiteURI>
      <cac:PartyIdentification><cbc:ID schemeID="VKN">{VKN_SATICI}</cbc:ID></cac:PartyIdentification>
      <cac:PartyIdentification><cbc:ID schemeID="MERSISNO">{MERSIS_SATICI}</cbc:ID></cac:PartyIdentification>
      <cac:PartyIdentification><cbc:ID schemeID="TICARETSICILNO">778899</cbc:ID></cac:PartyIdentification>
      <cac:PartyName><cbc:Name>Örnek Yazılım San. Tic. Ltd. Şti.</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>Moda Bahariye Bulvarı No: 42</cbc:StreetName>
        <cbc:CitySubdivisionName>Kadıköy</cbc:CitySubdivisionName>
        <cbc:CityName>İstanbul</cbc:CityName>
        <cbc:PostalZone>34710</cbc:PostalZone>
        <cac:Country><cbc:Name>Türkiye</cbc:Name></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>Göztepe</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>
      <cac:Contact>
        <cbc:Telephone>0216 555 01 02</cbc:Telephone>
        <cbc:ElectronicMail>fatura@ornek-yazilim.example</cbc:ElectronicMail>
      </cac:Contact>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification><cbc:ID schemeID="TCKN">{TC_SAHIS}</cbc:ID></cac:PartyIdentification>
      <cac:PartyName><cbc:Name>Alıcı Lojistik A.Ş.</cbc:Name></cac:PartyName>
      <cac:PostalAddress>
        <cbc:StreetName>Tunalı Caddesi No: 10</cbc:StreetName>
        <cbc:CitySubdivisionName>Çankaya</cbc:CitySubdivisionName>
        <cbc:CityName>Ankara</cbc:CityName>
        <cbc:PostalZone>06680</cbc:PostalZone>
        <cac:Country><cbc:Name>Türkiye</cbc:Name></cac:Country>
      </cac:PostalAddress>
      <cac:PartyTaxScheme><cac:TaxScheme><cbc:Name>Çankaya</cbc:Name></cac:TaxScheme></cac:PartyTaxScheme>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:PaymentMeans>
    <cbc:PaymentMeansCode>42</cbc:PaymentMeansCode>
    <cbc:InstructionNote>1</cbc:InstructionNote>
    <cac:PayeeFinancialAccount>
      <cbc:ID>{IBAN_ORNEK}</cbc:ID>
      <cac:FinancialInstitutionBranch>
        <cbc:Name>Kadıköy Şubesi</cbc:Name>
        <cac:FinancialInstitution><cbc:Name>Örnek Bankası A.Ş.</cbc:Name></cac:FinancialInstitution>
      </cac:FinancialInstitutionBranch>
    </cac:PayeeFinancialAccount>
  </cac:PaymentMeans>
  <cac:TaxTotal>
    <cbc:TaxAmount currencyID="TRY">920.00</cbc:TaxAmount>
  </cac:TaxTotal>
  <cac:LegalMonetaryTotal>
    <cbc:AllowanceTotalAmount currencyID="TRY">0.00</cbc:AllowanceTotalAmount>
    <cbc:PayableAmount currencyID="TRY">5520.00</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
  <cac:InvoiceLine>
    <cbc:ID>1</cbc:ID>
    <cbc:InvoicedQuantity unitCode="NIU">2.0000</cbc:InvoicedQuantity>
    <cbc:LineExtensionAmount currencyID="TRY">4600.00</cbc:LineExtensionAmount>
    <cac:Item>
      <cbc:Name>Danışmanlık Hizmeti</cbc:Name>
      <cac:SellersItemIdentification><cbc:ID>06ABC123</cbc:ID></cac:SellersItemIdentification>
    </cac:Item>
    <cac:Price><cbc:PriceAmount currencyID="TRY">2300.0000</cbc:PriceAmount></cac:Price>
  </cac:InvoiceLine>
</Invoice>
"""


def test_efatura_profile_exists_and_enables_all_invoice_types():
    ids = [p["id"] for p in builtin_profiles()]
    assert "efatura" in ids
    prof = next(p for p in builtin_profiles() if p["id"] == "efatura")
    for key in ("kurum_unvani", "vergi_dairesi", "ticaret_sicil", "banka_bilgisi", "ettn", "mersis", "tutar", "adres"):
        assert prof["types"][key]["enabled"] is True
    for off_key in ("plaka", "pasaport", "ehliyet", "yuz"):
        assert prof["types"][off_key]["enabled"] is False


def test_efatura_text_detection_handles_decimals_spaces_bank_and_no_false_card():
    text = (
        "SATICI TEKNOLOJİ SAN. TİC. LTD.\nŞTİ.\n"
        "Barbaros Mah. Atatürk Cad. No:5\nAtaşehir / İstanbul\n"
        "Vergi Dairesi: Kozyatağı   VKN: 1234567890\n"
        f"Mersis No: {MERSIS_SATICI}   Ticaret Sicil No: 445566\n"
        "SAYIN\nALICI İNŞAAT A.Ş.\n"
        "Tunalı Sok. No:8 Çankaya/Ankara\n"
        "Vergi Dairesi: Başkent VKN: 0987654321\n"
        f"Fatura No: XYZ2026000012345  ETTN: {ETTN_ORNEK}\n"
        f"Birim Fiyat: 4.426,0000 TL   Ara Toplam: 426,50 \xa0TL   Net: 1.250,00\nTL\n"
        "Yanlız: İKİBİNDÖRTYÜZ TL\n"
        "Yirmi Altı Bin Beş Yüz Elli Yedi TL Yirmi Sekiz Kuruş\n"
        f"BANKA ADI\nŞUBE\nHESAP NO\nIBAN\nÖrnek Bank\nMerkez Şb.\nTL\n{IBAN_TR_BOSLUK}\n"
    )
    findings = detect(text, efatura_rules())
    types = {f.type for f in findings}
    assert {"kurum_unvani", "adres", "vergi_dairesi", "vkn", "mersis", "ticaret_sicil", "tutar", "iban", "banka_bilgisi", "ettn"} <= types
    assert "kredi_karti" not in types  # fatura no kredi kartı sanılmamalı
    vals = [f.value for f in findings]
    assert any("4.426,0000 TL" in v for v in vals)
    assert any("426,50" in v for v in vals)
    assert any("1.250,00" in v and "TL" in v for v in vals)
    assert any("SATICI" in v and "ŞTİ." in v for v in vals)
    assert any("ALICI İNŞAAT A.Ş." in v for v in vals)
    assert any("Yirmi Altı Bin" in v and "Kuruş" in v for v in vals)


def test_ubl_xml_masks_all_invoice_sections_and_keeps_valid_xml(tmp_path: Path):
    src = tmp_path / "efatura.xml"
    src.write_text(_fake_ubl_xml(), encoding="utf-8")

    scan = scan_text_doc(src, efatura_rules())
    types = {f.finding.type for f in scan.findings}
    assert {"kurum_unvani", "adres", "tutar", "vkn", "tc_kimlik", "vergi_dairesi", "mersis", "ticaret_sicil", "iban", "banka_bilgisi", "ettn", "telefon", "eposta"} <= types
    assert "plaka" not in types
    assert "kredi_karti" not in types

    out_path, masked_count, warnings = mask_text_doc(src, tmp_path / "out.xml", efatura_rules())
    assert masked_count > 15
    assert warnings
    masked = Path(out_path).read_text(encoding="utf-8")
    ET.fromstring(masked.encode("utf-8"))  # geçerli XML kalmalı

    for secret in (
        "Örnek Yazılım",
        "Alıcı Lojistik",
        "Moda Bahariye",
        "Kadıköy",
        "Çankaya",
        "Göztepe",
        VKN_SATICI,
        MERSIS_SATICI,
        "778899",
        ETTN_ORNEK,
        "5520.00",
        "2300.0000",
        "MIIBIjAN",
        "SigVal",
        "Kamu SM",
        "9876543210987654",
    ):
        assert secret not in masked

    # Çift yönlü takma ad kipi: bütün hassas değerler Kurum-1, VKN-1, Tutar-1 vb. olmalı
    out_pseudo, pseudo_count, _ = mask_text_doc(src, tmp_path / "pseudo.xml", efatura_rules(pseudonym=True))
    assert pseudo_count > 15
    pseudo_text = Path(out_pseudo).read_text(encoding="utf-8")
    assert "Kurum-1" in pseudo_text and "Tutar-1" in pseudo_text and "VKN-1" in pseudo_text and "ETTN-1" in pseudo_text


def test_pdf_efatura_masks_text_qr_and_passes_leak_check(tmp_path: Path):
    pdf_path = tmp_path / "efatura.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_image(pymupdf.Rect(420, 40, 520, 140), stream=_fake_qr_png())
    text = (
        "ÖRNEK BİLİŞİM A.Ş.\n"
        "Moda Mah. Çiçek Cad. No:12\nKadıköy / İstanbul\n"
        f"Vergi Dairesi: Kadıköy VKN: {VKN_SATICI}\n"
        f"Mersis No: {MERSIS_SATICI}  Ticaret Sicil No: 12345\n"
        "SAYIN\nALICI HOLDİNG A.Ş.\n"
        "e-FATURA\n"
        f"ETTN: {ETTN_ORNEK}\n"
        "Birim Fiyat: 4.426,0000 TL   Ödenecek: 5.311,20 \xa0TL\n"
        f"Garanti Bankası / Merkez Şb. / IBAN No: {IBAN_ORNEK} TL\n"
    )
    page.insert_text((40, 60), text)
    doc.save(pdf_path)
    doc.close()

    res = mask_pdf(pdf_path, tmp_path / "efatura_maskeli.pdf", efatura_rules())
    assert res.masked >= 10
    masked_doc = pymupdf.open(res.target)
    try:
        masked_txt = masked_doc[0].get_text("text")
        assert VKN_SATICI not in masked_txt
        assert MERSIS_SATICI not in masked_txt
        assert "4.426,0000" not in masked_txt
        assert ETTN_ORNEK not in masked_txt
        assert len(masked_doc[0].get_images()) == 0  # QR görseli tamamen silindi
    finally:
        masked_doc.close()


def test_zip_archive_scan_mask_and_security_limits(tmp_path: Path):
    xml_path = tmp_path / f"{ETTN_ORNEK}.xml"
    xml_path.write_text(_fake_ubl_xml(), encoding="utf-8")

    z_path = tmp_path / "efatura_paketi.zip"
    with zipfile.ZipFile(z_path, "w") as zf:
        zf.write(xml_path, arcname=f"gelen/{ETTN_ORNEK}.xml")
        zf.writestr("ignore.exe", b"MZ-not-supported")

    assert kind_of(z_path) == "arsiv"
    assert "Örnek Yazılım" in read_archive_text(z_path)
    scan = scan_archive(z_path, efatura_rules())
    assert scan.entries == 1
    assert len(scan.entry_summaries) == 1
    assert scan.entry_summaries[0]["uzanti"] == ".xml"
    assert any("atlandı" in w for w in scan.warnings)

    counts: dict[str, int] = {}
    detaylar: list[dict] = []
    out_zip, n_masked, _ = mask_archive(z_path, tmp_path / "out.zip", efatura_rules(), counts=counts, entry_details=detaylar)
    assert n_masked > 15 and counts.get("kurum_unvani") == 3
    assert len(detaylar) == 1 and detaylar[0]["uzanti"] == ".xml" and detaylar[0]["gizlenecek_sayisi"] == n_masked
    with zipfile.ZipFile(out_zip, "r") as zf:
        names = zf.namelist()
        assert len(names) == 1
        assert ETTN_ORNEK not in names[0]  # iç dosya adındaki ETTN maskelendi
        assert "ignore.exe" not in names
        inner = zf.read(names[0]).decode("utf-8")
        assert VKN_SATICI not in inner and ETTN_ORNEK not in inner

    # Güvensiz "../" yol reddi
    bad_zip = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad_zip, "w") as zf:
        zf.writestr("../kotu.xml", "<Invoice/>")
    with pytest.raises(PdfError):
        scan_archive(bad_zip, efatura_rules())


def test_duz_metin_sayin_cumlesi_tc_ve_kisiyi_yutmaz():
    from bulutbelge_core.paste import clean_text, scan_paste

    all_on = Rules.default()
    for k in all_on.types:
        all_on.types[k].enabled = True
    cumle = "Sayın Ahmet Yılmaz, TC kimlik no 10000000146, telefon 0532 000 00 00, e-posta ahmet@ornek.com"
    bulgular = scan_paste(cumle, all_on)
    turler = {b.finding.type for b in bulgular}
    assert {"kisi_adi", "tc_kimlik", "telefon", "eposta"}.issubset(turler)
    assert "kurum_unvani" not in turler
    temiz = clean_text(cumle, scan_paste(cumle, Rules.default()))
    assert "10000000146" not in temiz and "0532 000 00 00" not in temiz
