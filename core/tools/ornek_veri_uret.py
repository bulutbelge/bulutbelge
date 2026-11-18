"""Uygulamayı denemek için sahte verili örnek belgeler üretir.

Ön koşul (bir kez, repo kökünden): pip install "./core[dev]"

Kullanım (desktop/engine/.venv içindeki Python ile, repo kökünden):

    python core/tools/ornek_veri_uret.py <hedef-klasör>

Üretilen dosyalar (hepsi SAHTE veridir; numaralar doğrulamadan geçer ama
kimseye ait değildir, e-postalar ayrılmış example.com alanındadır):

- e-fatura.xml             UBL-TR biçiminde e-Fatura: VKN, TCKN, adres, IBAN,
                           telefon, e-posta, tutar, yorum içinde e-posta ve
                           gömülü (base64) PDF görünümü
- musteri-listesi.csv      Excel'den dışa aktarılmış gibi (UTF-8 BOM, ; ayraçlı)
- musteri-listesi-1254.csv Aynı liste, eski Windows Türkçe kodlamasıyla
- sunucu-gunlugu.txt       IP, e-posta, telefon, kart numarası geçen günlük
- basvuru-formu.jpg        Telefonla çekilmiş form fotoğrafı (yan, EXIF'te sahte
                           GPS konumu ve cihaz bilgisi)
- ekran-goruntusu.png      Müşteri kartı ekran görüntüsü
- taranmis-dilekce.pdf     Metin katmanı olmayan, taranmış dilekçe (OCR gerekir)
- kimlikli-sozlesme.pdf    Metinli PDF, imza alanıyla
- is-sozlesmesi.docx       Word: üst bilgi, tablo, biçimi bölünmüş TC, mailto
                           bağlantısı, izlenen değişiklikte silinmiş eski telefon,
                           SGK ve pasaport no, belge özelliklerinde yazar adı
- musteri-sunumu.pptx      PowerPoint: başlık, müşteri bilgileri, tablo, konuşmacı
                           notunda telefon, vesikalık görselli slayt
- musteri-tablosu.xlsx     Excel: sayı olarak saklanmış TC ve telefon, yorum,
                           ikinci sayfada IBAN ve poliçe no
- personel-karti.png       Çizilmiş yüzlü personel kartı (yüz tespiti denemesi)
- basvuru-dosyasi.pdf      İki sayfa: başvuru formu (kontrol hanesi tutmayan "yakınının
                           numarası", şirket santrali) ve kimlik fotokopisi sayfası
                           (sayfa çıkarma ve "emin olamadıklarımız" denemesi)

Gerçek kişisel veri repoya konmaz; bu betik her seferinde aynı sahte veriyi üretir.
"""

from __future__ import annotations

import base64
import io
import json
import math
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFilter, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from fake_data import fake_card, fake_iban, fake_tc, fake_vkn  # noqa: E402
from fake_face import draw_face  # noqa: E402  (çizim; gerçek kişiye ait değil)

def _font_path(bold: bool = False) -> str:
    """Türkçe karakterli bir TrueType yazı tipi: Windows, macOS ya da Linux (TAKIP 1.79)."""
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/Library/Fonts/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
         "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else [r"C:\Windows\Fonts\arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
              "/usr/share/fonts/dejavu/DejaVuSans.ttf"]
    )
    for c in candidates:
        if Path(c).is_file():
            return c
    raise SystemExit("Türkçe karakterli bir TrueType yazı tipi bulunamadı (Arial ya da DejaVu Sans)")


FONT = _font_path()
FONT_BOLD = _font_path(bold=True)
rng = random.Random(42)

PEOPLE = [
    # ad, TC'nin ilk 9 hanesi, telefon, e-posta, IBAN BBAN, plaka, doğum tarihi, adres
    ("Ayşe Yılmaz", "123456789", "0532 000 12 34", "ayse.yilmaz@example.com", "0006100519786457841326",
     "34 ABC 123", "14.03.1987", "Caferağa Mah. Moda Cad. No:12 D:3 Kadıköy/İstanbul"),
    ("Mehmet Demir", "234567891", "0541 000 56 78", "m.demir@example.com", "0001000123456789012345",
     "06 ZK 4567", "02.11.1979", "Kızılay Mah. Atatürk Bulvarı No:45 Çankaya/Ankara"),
    ("Zeynep Kaya", "345678912", "0505 000 90 12", "zeynep.kaya@example.com", "0006400000112233445566",
     "35 TR 789", "27.06.1994", "Alsancak Mah. Kıbrıs Şehitleri Cad. No:8 Konak/İzmir"),
    ("Ali Çelik", "456789123", "0555 000 34 56", "ali.celik@example.com", "0004600987654321098765",
     "16 BB 2024", "09.09.1968", "Nilüfer Mah. Fatih Sultan Mehmet Bulvarı No:101 Nilüfer/Bursa"),
    ("Elif Şahin", "567891234", "0533 000 78 90", "elif.sahin@example.com", "0001200555666777888999",
     "07 ES 321", "31.12.2001", "Lara Mah. Tekelioğlu Cad. No:22 Muratpaşa/Antalya"),
]


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


# ---------------------------------------------------------------- metin belgeler


def efatura(out: Path) -> None:
    name, tc9, tel, mail, bban, *_rest, adres = PEOPLE[0]
    embedded = base64.b64encode(_tiny_pdf(f"Fatura görünümü - {name} - {fake_tc(tc9)}")).decode()
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<!-- SAHTE VERİ: BulutBelge örneği. Hazırlayan: muhasebe@example.com -->
<Invoice xmlns="urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"
         xmlns:cac="urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
         xmlns:cbc="urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2">
  <cbc:UBLVersionID>2.1</cbc:UBLVersionID>
  <cbc:CustomizationID>TR1.2</cbc:CustomizationID>
  <cbc:ProfileID>EARSIVFATURA</cbc:ProfileID>
  <cbc:ID>BLT2026000000123</cbc:ID>
  <cbc:IssueDate>2026-11-04</cbc:IssueDate>
  <cbc:Note>Ödeme IBAN: {fake_iban("0001500158007300000001")}</cbc:Note>
  <cac:AdditionalDocumentReference>
    <cbc:ID>FaturaGorunumu</cbc:ID>
    <cac:Attachment>
      <cbc:EmbeddedDocumentBinaryObject mimeCode="application/pdf" filename="fatura.pdf">{embedded}</cbc:EmbeddedDocumentBinaryObject>
    </cac:Attachment>
  </cac:AdditionalDocumentReference>
  <cac:AccountingSupplierParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="VKN">{fake_vkn("987654321")}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PartyName><cbc:Name>Örnek Bilişim A.Ş.</cbc:Name></cac:PartyName>
      <cac:Contact>
        <cbc:Telephone>0212 000 11 22</cbc:Telephone>
        <cbc:ElectronicMail>fatura@example.com</cbc:ElectronicMail>
      </cac:Contact>
    </cac:Party>
  </cac:AccountingSupplierParty>
  <cac:AccountingCustomerParty>
    <cac:Party>
      <cac:PartyIdentification>
        <cbc:ID schemeID="TCKN">{fake_tc(tc9)}</cbc:ID>
      </cac:PartyIdentification>
      <cac:PostalAddress>
        <cbc:StreetName>Adres: {adres}</cbc:StreetName>
        <cbc:CityName>İstanbul</cbc:CityName>
      </cac:PostalAddress>
      <cac:Contact>
        <cbc:Telephone>{tel}</cbc:Telephone>
        <cbc:ElectronicMail>{mail}</cbc:ElectronicMail>
      </cac:Contact>
      <cac:Person>
        <cbc:FirstName>{name.split()[0]}</cbc:FirstName>
        <cbc:FamilyName>{name.split()[1]}</cbc:FamilyName>
      </cac:Person>
    </cac:Party>
  </cac:AccountingCustomerParty>
  <cac:LegalMonetaryTotal>
    <cbc:PayableAmount currencyID="TRY">18.750,00 TL</cbc:PayableAmount>
  </cac:LegalMonetaryTotal>
</Invoice>
"""
    (out / "e-fatura.xml").write_text(xml, encoding="utf-8")


def _tiny_pdf(text: str) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page(width=300, height=200)
    page.insert_text((20, 40), text.encode("ascii", "replace").decode(), fontsize=9)
    data = doc.tobytes()
    doc.close()
    return data


def csv_files(out: Path) -> None:
    rows = ["Ad Soyad;TC Kimlik No;Telefon;E-posta;IBAN;Plaka;Doğum Tarihi;Adres"]
    for name, tc9, tel, mail, bban, plaka, dogum, adres in PEOPLE:
        rows.append(f"{name};{fake_tc(tc9)};{tel};{mail};{fake_iban(bban)};{plaka};{dogum};{adres}")
    text = "\r\n".join(rows) + "\r\n"
    (out / "musteri-listesi.csv").write_bytes(b"\xef\xbb\xbf" + text.encode("utf-8"))
    (out / "musteri-listesi-1254.csv").write_bytes(text.encode("cp1254"))


def server_log(out: Path) -> None:
    lines = [
        "2026-11-04 09:12:03 INFO  oturum açıldı kullanici=ayse.yilmaz@example.com ip=192.168.10.24",
        "2026-11-04 09:12:41 INFO  sepet güncellendi kullanici=ayse.yilmaz@example.com tutar=1.249,90 TL",
        f"2026-11-04 09:13:05 WARN  ödeme denemesi kart={fake_card('411111111111111')} sonuç=RED",
        "2026-11-04 09:13:20 INFO  SMS gönderildi telefon=0532 000 12 34",
        "2026-11-04 09:15:44 ERROR çağrı zaman aşımı istemci=85.105.20.31 süre=30s",
        f"2026-11-04 09:16:02 INFO  kimlik doğrulandı tckn={fake_tc('234567891')}",
        "2026-11-04 09:18:30 INFO  adres güncellendi: Adres: Kızılay Mah. Atatürk Bulvarı No:45 Çankaya/Ankara",
        "2026-11-04 09:20:00 INFO  günlük döndürüldü (sahte veri)",
    ]
    (out / "sunucu-gunlugu.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------- görseller


def _paper(w: int, h: int, lines: list[tuple[str, int, bool]], signature: bool = False) -> Image.Image:
    img = Image.new("RGB", (w, h), (250, 248, 242))
    d = ImageDraw.Draw(img)
    y = 70
    for text, size, bold in lines:
        if text:
            d.text((80, y), text, fill=(30, 32, 40), font=font(size, bold))
        y += int(size * 1.9)
    if signature:
        d.text((w - 420, h - 260), "İmza:", fill=(30, 32, 40), font=font(28))
        _scribble(d, w - 330, h - 230)
    return img


def _scribble(d: ImageDraw.ImageDraw, x: int, y: int) -> None:
    pts = []
    for i in range(80):
        t = i / 79
        pts.append((x + t * 240, y + 30 * math.sin(t * 14) * (1 - t * 0.5) + rng.uniform(-4, 4)))
    d.line(pts, fill=(25, 40, 120), width=4, joint="curve")


def form_photo(out: Path) -> None:
    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[1]
    paper = _paper(1400, 1800, [
        ("MÜŞTERİ BAŞVURU FORMU", 46, True),
        ("(sahte veri - BulutBelge örneği)", 24, False),
        ("", 20, False),
        (f"Ad Soyad: {name}", 34, False),
        (f"TC Kimlik No: {fake_tc(tc9)}", 34, False),
        (f"Doğum tarihi: {dogum}", 34, False),
        (f"Telefon: {tel}", 34, False),
        (f"E-posta: {mail}", 34, False),
        (f"IBAN: {fake_iban(bban)}", 30, False),
        (f"Araç plakası: {plaka}", 34, False),
        ("Adres: Kızılay Mah. Atatürk Bulvarı No:45", 32, False),
        ("Çankaya/Ankara", 32, False),
    ], signature=True)
    paper.paste(draw_face(110).resize((220, 220)), (1100, 60))  # vesikalık (çizim)
    # Masanın üzerinde, hafif eğik çekilmiş fotoğraf görünümü.
    photo = Image.new("RGB", (1600, 2000), (120, 92, 70))
    shadow = Image.new("L", paper.size, 0)
    shadow.paste(90, (0, 0, *paper.size))
    paper_r = paper.rotate(1.8, expand=True, resample=Image.BICUBIC, fillcolor=(120, 92, 70))
    photo.paste(paper_r, (60, 50))
    photo = photo.filter(ImageFilter.GaussianBlur(0.6))
    noise = Image.effect_noise(photo.size, 10).convert("RGB")
    photo = Image.blend(photo, noise, 0.04)
    # Telefon fotoğrafı gibi yan kaydet; yön EXIF'te (6 = 90° döndür).
    sideways = photo.rotate(90, expand=True)
    exif = Image.Exif()
    exif[0x0112] = 6  # Orientation
    exif[0x010F] = "Örnek Telefon Üreticisi"  # Make
    exif[0x0110] = "Sahte Model X"  # Model
    exif[0x0132] = "2026:11:04 09:30:00"  # DateTime
    exif[0x8825] = {1: "N", 2: (39.0, 55.0, 12.0), 3: "E", 4: (32.0, 51.0, 30.0)}  # GPS (Ankara civarı, sahte)
    sideways.save(out / "basvuru-formu.jpg", quality=90, exif=exif)


def screenshot(out: Path) -> None:
    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[2]
    w, h = 1280, 720
    img = Image.new("RGB", (w, h), (244, 246, 250))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, w, 56), fill=(31, 95, 209))
    d.text((24, 16), "ÖrnekCRM  ·  Müşteri kartı (sahte veri)", fill="white", font=font(22, True))
    d.rounded_rectangle((40, 90, 760, 660), 16, fill="white", outline=(225, 228, 235))
    d.ellipse((70, 120, 150, 200), fill=(200, 210, 230))
    d.text((170, 130), name, fill=(28, 31, 38), font=font(30, True))
    d.text((170, 172), "Bireysel müşteri · 2019'dan beri", fill=(120, 126, 138), font=font(18))
    fields = [
        ("TC Kimlik No", fake_tc(tc9)),
        ("Telefon", tel),
        ("E-posta", mail),
        ("IBAN", fake_iban(bban)),
        ("Doğum tarihi", dogum),
        ("Adres", "Alsancak Mah. Kıbrıs Şehitleri Cad. No:8"),
        ("", "Konak/İzmir"),
    ]
    y = 240
    for label, value in fields:
        if label:
            d.text((70, y), label, fill=(120, 126, 138), font=font(17))
        d.text((280, y), value, fill=(28, 31, 38), font=font(21))
        y += 54
    d.rounded_rectangle((800, 90, 1240, 400), 16, fill="white", outline=(225, 228, 235))
    d.text((830, 115), "Son not", fill=(28, 31, 38), font=font(22, True))
    note = ["Müşteri kartının son 4 hanesi", "ile doğrulandı. Geri arama:", "0505 000 90 12"]
    for i, line in enumerate(note):
        d.text((830, 165 + i * 34), line, fill=(60, 64, 72), font=font(19))
    img.save(out / "ekran-goruntusu.png")


# ---------------------------------------------------------------- PDF


def scanned_petition(out: Path) -> None:
    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[3]
    page_img = _paper(1654, 2339, [  # A4, 200 dpi
        ("ÇANKAYA BELEDİYE BAŞKANLIĞINA", 40, True),
        ("(sahte veri - BulutBelge örneği)", 24, False),
        ("", 30, False),
        ("Ekte sunduğum belgeler doğrultusunda ruhsat başvurumun", 32, False),
        ("değerlendirilmesini arz ederim.", 32, False),
        ("", 30, False),
        (f"Ad Soyad: {name}", 32, False),
        (f"TC Kimlik No: {fake_tc(tc9)}", 32, False),
        (f"Telefon: {tel}", 32, False),
        (f"E-posta: {mail}", 32, False),
        ("Adres: Nilüfer Mah. Fatih Sultan Mehmet Bulvarı No:101", 30, False),
        ("Nilüfer/Bursa", 30, False),
    ], signature=True)
    page_img = page_img.rotate(0.6, resample=Image.BICUBIC, fillcolor=(250, 248, 242)).convert("L")
    buf = io.BytesIO()
    page_img.save(buf, "JPEG", quality=80)
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_image(page.rect, stream=buf.getvalue())
    doc.save(out / "taranmis-dilekce.pdf")
    doc.close()


def text_contract(out: Path) -> None:
    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[4]
    doc = pymupdf.open()
    page = doc.new_page()
    f = pymupdf.Font(fontfile=FONT)
    fb = pymupdf.Font(fontfile=FONT_BOLD)
    tw = pymupdf.TextWriter(page.rect)
    tw.append((60, 70), "KİRA SÖZLEŞMESİ (SAHTE VERİ)", font=fb, fontsize=16)
    lines = [
        f"Kiracı: {name}",
        f"TC kimlik no: {fake_tc(tc9)}",
        f"Doğum tarihi: {dogum}",
        f"Telefon: {tel}   E-posta: {mail}",
        f"Kira ödemesi IBAN: {fake_iban(bban)}",
        "Aylık kira: 25.000,00 TL",
        f"Adres: {adres}",
        f"Otopark plakası: {plaka}",
        f"Depozito kartı: {fake_card('545454545454545')}",
    ]
    for i, line in enumerate(lines):
        tw.append((60, 120 + i * 24), line, font=f, fontsize=11)
    tw.append((60, 400), "Kiracı İmza:", font=f, fontsize=11)
    tw.write_text(page)
    shape = page.new_shape()
    pts = [pymupdf.Point(150 + t * 3, 420 + 12 * math.sin(t / 4)) for t in range(0, 60)]
    for a, b, c, e in zip(pts[0::3], pts[1::3], pts[2::3], pts[3::3]):
        shape.draw_bezier(a, b, c, e)
    shape.finish(color=(0.1, 0.15, 0.5), width=1.4)
    shape.commit()
    doc.set_metadata({"author": name, "title": "Kira sözleşmesi"})
    doc.subset_fonts()
    doc.save(out / "kimlikli-sozlesme.pdf")
    doc.close()


def word_contract(out: Path) -> None:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.opc.constants import RELATIONSHIP_TYPE
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Pt, RGBColor

    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[0]
    d = docx.Document()
    d.core_properties.author = name
    d.core_properties.last_modified_by = "Mehmet Demir"
    d.core_properties.title = f"İş sözleşmesi - {name}"
    style = d.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    header = d.sections[0].header.paragraphs[0]
    header.text = "Örnek Bilişim A.Ş. · İnsan Kaynakları · Tel: 0212 000 11 22"
    header.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    d.sections[0].footer.paragraphs[0].text = "SAHTE VERİ - BulutBelge örneği"

    title = d.add_heading("BELİRSİZ SÜRELİ İŞ SÖZLEŞMESİ", 1)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    d.add_paragraph("İşbu sözleşme aşağıda bilgileri yazılı taraflar arasında imzalanmıştır.")

    d.add_heading("1. Taraflar", 2)
    table = d.add_table(rows=0, cols=2)
    table.style = "Light Grid Accent 1"
    for label, value in [
        ("İşçi", name),
        ("TC kimlik no", fake_tc(tc9)),
        ("Doğum tarihi", f"Doğum tarihi: {dogum}"),
        ("Adres", adres),
        ("Telefon", tel),
        ("Maaş hesabı (IBAN)", fake_iban(bban)),
    ]:
        row = table.add_row().cells
        row[0].text = label
        row[1].text = value
        row[0].paragraphs[0].runs[0].bold = True

    d.add_heading("2. İletişim", 2)
    p = d.add_paragraph("İşçi, bildirimlerin ")
    # Bağlantı: görünen metin ve hedef (mailto:) ayrı yerlerde saklanır.
    rid = p.part.relate_to(f"mailto:{mail}", RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    rpr = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "0563C1")
    rpr.append(color)
    run.append(rpr)
    t = OxmlElement("w:t")
    t.text = mail
    run.append(t)
    link.append(run)
    p._p.append(link)
    p.add_run(" adresine yapılmasını kabul eder. Önceki telefon numarası ")
    # İzlenen değişiklik: eski numara silinmiş görünür ama dosyada durur.
    deleted = OxmlElement("w:del")
    deleted.set(qn("w:id"), "1")
    deleted.set(qn("w:author"), "Mehmet Demir")
    deleted.set(qn("w:date"), "2026-11-01T10:00:00Z")
    drun = OxmlElement("w:r")
    dt = OxmlElement("w:delText")
    dt.text = "0505 000 90 12"
    drun.append(dt)
    deleted.append(drun)
    p._p.append(deleted)
    p.add_run(" geçersizdir.")

    d.add_heading("3. Ücret", 2)
    p = d.add_paragraph("Aylık brüt ücret ")
    r = p.add_run("42.500,00 TL")
    r.bold = True
    p.add_run(" olup her ayın son iş günü yukarıdaki hesaba ödenir.")

    d.add_paragraph(f"SGK sicil no: 1234 5678 90123 · Pasaport No: U{tc9[:8]}")
    d.add_heading("4. Kimlik doğrulama", 2)
    p = d.add_paragraph("İşçinin kimlik numarası ")
    tc = fake_tc(tc9)
    # Word'ün sık yaptığı gibi: numara biçim değişikliğiyle iki parçaya bölünmüş.
    r1 = p.add_run(tc[:5])
    r1.font.color.rgb = RGBColor(0xC0, 0x00, 0x00)
    p.add_run(tc[5:])
    p.add_run(" olarak nüfus kayıtlarıyla doğrulanmıştır.")

    d.add_paragraph()
    sig = d.add_table(rows=2, cols=2)
    sig.cell(0, 0).text = "İşveren İmza / Kaşe"
    sig.cell(0, 1).text = "İşçi İmza"
    sig.cell(1, 0).text = "Örnek Bilişim A.Ş."
    sig.cell(1, 1).text = name
    d.save(out / "is-sozlesmesi.docx")


def presentation(out: Path) -> None:
    import io as _io

    import pptx
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt

    p = pptx.Presentation()
    p.slide_width, p.slide_height = Inches(13.333), Inches(7.5)
    p.core_properties.author = "Mehmet Demir"

    s = p.slides.add_slide(p.slide_layouts[0])
    s.shapes.title.text = "Müşteri Portföy Değerlendirmesi"
    s.placeholders[1].text = "Hazırlayan: Zeynep Kaya · Kasım 2026 (sahte veri)"

    name, tc9, tel, mail, bban, plaka, dogum, adres = PEOPLE[0]
    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "Öne çıkan müşteri"
    face = _io.BytesIO()
    draw_face(110).resize((220, 220)).save(face, "PNG")
    s.shapes.add_picture(face, Inches(0.8), Inches(1.8), Inches(2.4), Inches(2.4))
    box = s.shapes.add_textbox(Inches(3.6), Inches(1.8), Inches(8.8), Inches(4)).text_frame
    box.word_wrap = True
    lines = [
        (f"Ad Soyad: {name}", True),
        (f"TC kimlik no: {fake_tc(tc9)}", False),
        (f"Telefon: {tel}", False),
        (f"E-posta: {mail}", False),
        (f"Müşteri No: MS-2026-000{tc9[:3]}", False),
        (f"Adres: {adres}", False),
    ]
    for i, (text, bold) in enumerate(lines):
        para = box.paragraphs[0] if i == 0 else box.add_paragraph()
        r = para.add_run()
        r.text = text
        r.font.size = Pt(22 if bold else 18)
        r.font.bold = bold
        if bold:
            r.font.color.rgb = RGBColor(0x1F, 0x5F, 0xD1)
    s.notes_slide.notes_text_frame.text = f"Not: {name} toplantı sonrası 0505 000 90 12 numarasından aranacak."

    s = p.slides.add_slide(p.slide_layouts[5])
    s.shapes.title.text = "Müşteri listesi"
    rows = len(PEOPLE) + 1
    table = s.shapes.add_table(rows, 3, Inches(0.8), Inches(1.7), Inches(11.7), Inches(4.5)).table
    for c, h in enumerate(("Ad Soyad", "Telefon", "E-posta")):
        table.cell(0, c).text = h
    for r, (n, _tc, t, m, *_rest) in enumerate(PEOPLE, start=1):
        for c, v in enumerate((n, t, m)):
            table.cell(r, c).text = v
    p.save(out / "musteri-sunumu.pptx")


def spreadsheet(out: Path) -> None:
    import openpyxl
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Müşteriler"
    header = ["Ad Soyad", "TC Kimlik No", "Telefon", "E-posta", "Şehir", "Not"]
    ws.append(header)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F5FD1")
    for name, tc9, tel, mail, bban, plaka, dogum, adres in PEOPLE:
        phone_number = int(tel.replace(" ", "")[1:])  # Excel'in çoğu zaman yaptığı gibi: sayı, baştaki 0 yok
        city = adres.rsplit("/", 1)[-1]
        ws.append([name, int(fake_tc(tc9)), phone_number, mail, city, ""])
    ws["F2"] = "VIP müşteri, temsilci: Zeynep Kaya"
    ws["A3"].comment = Comment("Mehmet Demir ile 0505 000 90 12 üzerinden görüşüldü.", "Zeynep Kaya")
    for col, width in zip("ABCDEF", (18, 16, 14, 26, 12, 34)):
        ws.column_dimensions[col].width = width
    ws2 = wb.create_sheet("Ödemeler")
    ws2.append(["Müşteri", "IBAN", "Tutar", "Açıklama"])
    for name, tc9, tel, mail, bban, *_rest in PEOPLE:
        ws2.append([name, fake_iban(bban), 1250.5, f"Poliçe no {tc9[:8]} yenileme"])
    wb.properties.creator = "Zeynep Kaya"
    wb.save(out / "musteri-tablosu.xlsx")


def staff_badge(out: Path) -> None:
    name, tc9, *_rest = PEOPLE[2]
    card = Image.new("RGB", (1000, 620), (246, 248, 252))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle((0, 0, 999, 619), 32, outline=(31, 95, 209), width=6)
    d.rectangle((0, 0, 1000, 110), fill=(31, 95, 209))
    d.text((40, 32), "ÖRNEK BİLİŞİM A.Ş. · PERSONEL KARTI", fill="white", font=font(36, True))
    card.paste(draw_face(130).resize((260, 260)), (50, 170))
    d.text((350, 180), name, fill=(28, 31, 38), font=font(44, True))
    d.text((350, 250), "Yazılım Geliştirme Uzmanı", fill=(90, 96, 110), font=font(28))
    d.text((350, 330), "Sicil no: 2026-0457", fill=(28, 31, 38), font=font(28))
    d.text((350, 380), "SGK sicil no: 1234567890123", fill=(28, 31, 38), font=font(28))
    d.text((350, 470), "(sahte veri - BulutBelge örneği)", fill=(140, 146, 158), font=font(22))
    card.save(out / "personel-karti.png")


def application_file(out: Path) -> None:
    name, tc9, tel, mail, _bban, _plaka, dogum, adres = PEOPLE[2]
    tc = fake_tc(tc9)
    bad = tc[:-1] + str((int(tc[-1]) + 1) % 10)  # kontrol hanesi tutmuyor
    doc = pymupdf.open()
    f = pymupdf.Font(fontfile=FONT)
    fb = pymupdf.Font(fontfile=FONT_BOLD)

    page = doc.new_page()
    tw = pymupdf.TextWriter(page.rect)
    tw.append((60, 70), "KREDİ BAŞVURU FORMU (SAHTE VERİ)", font=fb, fontsize=16)
    lines = [
        f"Başvuran: {name}",
        f"TC kimlik no: {tc}",
        f"Yakınının numarası: {bad}",
        f"Doğum tarihi: {dogum}",
        f"Adres: {adres}",
        f"Cep telefonu: {tel}   E-posta: {mail}",
        "Talep edilen tutar: 150.000,00 TL",
        "",
        "Örnek Finans A.Ş. müşteri hizmetleri santrali: 0212 000 00 00",
    ]
    for i, line in enumerate(lines):
        tw.append((60, 120 + i * 24), line, font=f, fontsize=11)
    tw.write_text(page)

    page = doc.new_page()
    tw = pymupdf.TextWriter(page.rect)
    tw.append((60, 70), "EK-1: KİMLİK KARTI FOTOKOPİSİ", font=fb, fontsize=14)
    card = pymupdf.Rect(60, 100, 400, 310)
    page.draw_rect(card, color=(0.55, 0.6, 0.7), fill=(0.93, 0.95, 0.98), width=1.2)
    page.draw_rect(pymupdf.Rect(75, 140, 165, 250), color=(0.6, 0.6, 0.6), fill=(0.85, 0.86, 0.88))
    card_lines = [
        ("TÜRKİYE CUMHURİYETİ KİMLİK KARTI", fb, 9),
        (f"T.C. Kimlik No: {tc}", f, 10),
        (f"Soyadı / Adı: {name.split()[1].upper()} {name.split()[0].upper()}", f, 10),
        (f"Doğum Tarihi: {dogum}", f, 10),
        ("Seri No: A12B34567", f, 10),
    ]
    for i, (line, fnt, size) in enumerate(card_lines):
        tw.append((180 if i else 75, 125 + i * 26 if i else 122), line, font=fnt, fontsize=size)
    tw.write_text(page)
    doc.subset_fonts()
    doc.save(out / "basvuru-dosyasi.pdf")
    doc.close()


def beklenen_yaz(out: Path) -> None:
    """Metin katmanı olan belgeler için `beklenen.json` yazar (kacak_kontrol.py girdisi, TAKIP 1.2).

    Değerler sahtedir; maskeli kopyada hiçbirinin kalmaması beklenir.
    """
    degerler: list[str] = []
    for _ad, tc9, tel, mail, bban, *_ in PEOPLE:
        degerler += [fake_tc(tc9), tel, mail, fake_iban(bban)]
    expected = {
        name: {"degerler": degerler[:], "not": ["tüm sahte kişiler"]}
        for name in ("musteri-listesi.csv", "musteri-listesi-1254.csv")
    }
    expected["sunucu-gunlugu.txt"] = {"degerler": [fake_tc("234567891"), "0532 000 12 34", fake_card("411111111111111")]}
    p0 = [fake_tc(PEOPLE[0][1]), PEOPLE[0][2], PEOPLE[0][3]]
    expected["is-sozlesmesi.docx"] = {"degerler": p0}
    expected["musteri-sunumu.pptx"] = {"degerler": p0}
    expected["kimlikli-sozlesme.pdf"] = {"degerler": [fake_tc(PEOPLE[4][1]), PEOPLE[4][2], PEOPLE[4][3], fake_card("545454545454545")]}
    expected["basvuru-dosyasi.pdf"] = {"degerler": [fake_tc(PEOPLE[2][1]), PEOPLE[2][2], PEOPLE[2][3]]}
    (out / "beklenen.json").write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    makers = (
        efatura, csv_files, server_log, form_photo, screenshot, scanned_petition, text_contract, word_contract,
        presentation, spreadsheet, staff_badge, application_file,
    )
    for make in makers:
        make(out)
    beklenen_yaz(out)
    for p in sorted(out.iterdir()):
        print(f"{p.name:28} {p.stat().st_size // 1024:>5} KB")


if __name__ == "__main__":
    main()
