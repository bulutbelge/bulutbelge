"""Maskelemeyi zorlayan sahte örnek belgeler üretir.

Kullanım (desktop/engine/.venv içindeki Python ile, repo kökünden):

    python core/tools/zor_ornekler_uret.py <hedef-klasör>

`ornek_veri_uret.py` gündelik belgeleri üretir; bu betik bilinen tuzakları:

- karisik-yazim.txt          Aralıklı, noktalı, tam genişlikli, OCR hatalı (O/0, l/1, S/5) TC;
                             satıra bölünmüş IBAN; boşluklu e-posta; farklı telefon yazımları (1.62)
- gizli-katmanli.pdf         Sayfa metni dışında: not (yorum), yer imi, form alanı, meta veri,
                             XMP, gömülü dosya, JavaScript; beyaz kutuyla örtülmüş metin ve
                             artımlı kayıtta kalan eski sürüm (1.57)
- glif-aralikli.pdf          Harf harf konumlanmış TC, iki parçaya ve iki yazı tipine bölünmüş
                             numara, döndürülmüş yazı, çok küçük ve beyaz yazı (1.58)
- Ayşe Yılmaz - dilekçe.pdf  Dosya adında kişi adı (1.60)
- donuk-imza-3.jpg, -6.jpg, -8.jpg
                             EXIF yönü 3 (180°), 6 (90°), 8 (270°) olan imzalı form fotoğrafları (1.74)
- gizli-word.docx            Metin kutusu, dipnot, yorum, köprü ipucu, görsel alternatif metni,
                             üst/alt bilgi ve belge özelliklerinde kişisel veri (1.57)
- bolunmus-tablo.xlsx        Ad ve soyad ayrı hücrede, TC iki hücreye bölünmüş, tarih biçimli
                             doğum tarihi, gizli sayfa ve gizli sütun (1.62, 1.65)
- beklenen.json              Her dosyada maskeli kopyada bulunmaması gereken değerler
                             (kacak_kontrol.py okur)

Hepsi SAHTE veridir: numaralar doğrulamadan geçer ama kimseye ait değildir, e-postalar
ayrılmış example.com alanındadır. Yazı tipi platforma göre bulunur (1.79).
"""

from __future__ import annotations

import io
import json
import math
import random
import sys
from pathlib import Path

import pymupdf
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))
from fake_data import fake_iban, fake_tc  # noqa: E402

rng = random.Random(7)

# Sahte kişiler (ornek_veri_uret.py'dekilerden farklı; aynı TC iki betikte çakışmasın).
AD1, TC1, TEL1, MAIL1, IBAN1 = "Ayşe Yılmaz", fake_tc("198765432"), "0532 000 12 34", "ayse.yilmaz@example.com", fake_iban("0006100519786457841326")
AD2, TC2, TEL2, MAIL2 = "Mehmet Demir", fake_tc("287654321"), "0541 000 56 78", "m.demir@example.com"
AD3, TC3 = "Zeynep Kaya", fake_tc("376543219")

EXPECTED: dict[str, dict[str, list[str]]] = {}


def expect(name: str, *values: str, note: str = "") -> None:
    EXPECTED.setdefault(name, {"degerler": [], "not": []})
    EXPECTED[name]["degerler"].extend(v for v in values if v not in EXPECTED[name]["degerler"])
    if note:
        EXPECTED[name]["not"].append(note)


def _font_path(bold: bool = False) -> str:
    candidates = (
        [r"C:\Windows\Fonts\arialbd.ttf", "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
        if bold
        else [r"C:\Windows\Fonts\arial.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf",
              "/Library/Fonts/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]
    )
    for c in candidates:
        if Path(c).is_file():
            return c
    raise SystemExit("Türkçe karakterli bir TrueType yazı tipi bulunamadı (Arial ya da DejaVu Sans)")


def font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(_font_path(bold), size)


# ---------------------------------------------------------------- 1.62 karışık yazım


def mixed_text(out: Path) -> None:
    fw = TC1.translate(str.maketrans("0123456789", "０１２３４５６７８９"))
    ocr = TC2.replace("0", "O").replace("1", "l").replace("5", "S")
    iban_compact = IBAN1.replace(" ", "")
    lines = [
        "KARIŞIK YAZIM DENEMESİ (sahte veri - BulutBelge)",
        "",
        f"Aralıklı TC: {' '.join(TC1)}",
        f"Noktalı TC: {TC1[:3]}.{TC1[3:6]}.{TC1[6:9]}.{TC1[9:]}",
        f"Tireli TC: {TC1[:3]}-{TC1[3:6]}-{TC1[6:9]}-{TC1[9:]}",
        f"Tam genişlikli TC: {fw}",
        f"OCR hatalı TC: {ocr}",
        f"T.C. No:{TC3}",
        "",
        "IBAN iki satıra bölünmüş:",
        iban_compact[:14],
        iban_compact[14:],
        "",
        f"Telefon (+90): +90 (532) 000-12-34",
        "Telefon (noktalı): 0532.000.12.34",
        "Telefon (bitişik): 05320001234",
        f"E-posta (boşluklu): {MAIL1.replace('@', ' @ ').replace('.', ' . ')}",
        f"E-posta (köşeli): {MAIL2.replace('@', '[at]').replace('.', '[dot]')}",
    ]
    (out / "karisik-yazim.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    expect(
        "karisik-yazim.txt", TC1, TC2, TC3, iban_compact, "05320001234",
        note="Aralıklı/noktalı/tam genişlikli/OCR hatalı yazımlar ham metinde aranır; "
        "kacak_kontrol rakam dışı karakterleri atıp da arar",
    )


# ---------------------------------------------------------------- 1.57 gizli katmanlar (PDF)


def hidden_layers_pdf(out: Path) -> None:
    path = out / "gizli-katmanli.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "GİZLİ KATMAN DENEMESİ (sahte veri)", fontsize=14, fontname="helv")
    page.insert_text((72, 110), f"Başvuran: {AD1}", fontsize=11, fontname="helv")
    page.insert_text((72, 130), f"TC Kimlik No: {TC1}", fontsize=11, fontname="helv")
    # Beyaz kutuyla "kapatılmış" ama silinmemiş metin (görsel örtü tuzağı).
    page.insert_text((72, 160), f"Eski telefon: {TEL2}", fontsize=11, fontname="helv")
    page.draw_rect(pymupdf.Rect(70, 148, 300, 166), color=(1, 1, 1), fill=(1, 1, 1))
    # Yorum notu.
    page.add_text_annot((400, 120), f"Kontrol edildi, müşteri TC {TC2}")
    # Form alanı.
    w = pymupdf.Widget()
    w.field_name, w.field_type = "telefon", pymupdf.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = pymupdf.Rect(72, 200, 300, 220), TEL1
    page.add_widget(w)
    # Gömülü dosya ve yer imi.
    doc.embfile_add("ek-not.txt", f"Ek: {AD3} TC {TC3}".encode("utf-8"), filename="ek-not.txt")
    doc.set_toc([[1, f"Başvuru - {MAIL1}", 1]])
    doc.set_metadata({"author": AD2, "title": f"{AD1} başvurusu", "subject": TC1})
    doc.set_xml_metadata(
        f'<?xpacket begin=""?><x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
        f'<rdf:Description xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:creator>{AD2}</dc:creator></rdf:Description>'
        f"</rdf:RDF></x:xmpmeta><?xpacket end=\"w\"?>"
    )
    doc.set_page_labels([{"startpage": 0, "prefix": "", "style": "D"}])
    doc.save(path)
    doc.close()
    # Artımlı kayıt: eski sürümde kalan satır (yeni sürümde silinmiş görünür).
    doc = pymupdf.open(path)
    page = doc[0]
    page.add_redact_annot(pymupdf.Rect(70, 120, 400, 134))
    page.apply_redactions()
    page.insert_text((72, 130), "TC Kimlik No: (dosyada)", fontsize=11, fontname="helv")
    xref = doc.pdf_catalog()
    doc.xref_set_key(xref, "OpenAction", "<< /S /JavaScript /JS (app.alert\\('Sahte: " + TC3 + "'\\);) >>")
    doc.saveIncr()
    doc.close()
    expect(
        "gizli-katmanli.pdf", AD1, AD2, AD3, TC1, TC2, TC3, TEL1, TEL2, MAIL1,
        note="TC1 ilk sürümde sayfada, artımlı kayıtla silindi: eski sürümde ham baytta durur",
    )
    expect("gizli-katmanli.pdf", note="Eski telefon beyaz kutuyla örtülü; metin katmanında hâlâ var")


# ---------------------------------------------------------------- 1.58 glif konumu


def glyph_pdf(out: Path) -> None:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "GLİF VE KONUM DENEMESİ (sahte veri)", fontsize=14, fontname="helv")
    # Harf harf yerleştirilmiş TC (her rakam ayrı metin işlemi, eşit olmayan aralık).
    x = 160
    page.insert_text((72, 120), "TC Kimlik No:", fontsize=11, fontname="helv")
    for ch in TC1:
        page.insert_text((x, 120), ch, fontsize=11, fontname="helv")
        x += 7 + rng.uniform(-0.6, 1.4)
    # İki parça, iki yazı tipi.
    page.insert_text((72, 150), "Müşteri TC: " + TC2[:5], fontsize=11, fontname="helv")
    page.insert_text((72 + pymupdf.get_text_length("Müşteri TC: " + TC2[:5], "helv", 11), 150), TC2[5:], fontsize=11, fontname="cour")
    # Döndürülmüş yazı (kenar notu).
    page.insert_text((540, 400), f"Onaylayan: {AD2} {TEL2}", fontsize=9, fontname="helv", rotate=90)
    # Çok küçük ve beyaz yazı.
    page.insert_text((72, 760), f"gizli: {MAIL1}", fontsize=1.5, fontname="helv")
    page.insert_text((72, 780), f"beyaz: {TC3}", fontsize=10, fontname="helv", color=(1, 1, 1))
    doc.save(out / "glif-aralikli.pdf")
    doc.close()
    expect(
        "glif-aralikli.pdf", TC1, TC2, TC3, AD2, TEL2, MAIL1,
        note="Kutu genişliği ve rakam arası boşluk değerin uzunluğunu ele vermemeli (1.58, 1.59): gözle kontrol",
    )


# ---------------------------------------------------------------- 1.60 dosya adında kişi adı


def named_file(out: Path) -> None:
    name = f"{AD1} - dilekçe.pdf"
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), "DİLEKÇE (sahte veri)", fontsize=14, fontname="helv")
    page.insert_text((72, 110), f"Adı Soyadı: {AD1}", fontsize=11, fontname="helv")
    page.insert_text((72, 130), f"TC Kimlik No: {TC1}", fontsize=11, fontname="helv")
    page.insert_text((72, 150), f"Telefon: {TEL1}", fontsize=11, fontname="helv")
    doc.save(out / name)
    doc.close()
    expect(
        name, AD1, TC1, TEL1,
        note="Dosya adındaki kişi adı çıktı adında, Son Yapılanlar'da ve işlem günlüğünde görünür (1.60)",
    )


# ---------------------------------------------------------------- 1.74 EXIF yönlü imza


def _form(signature_label: str) -> Image.Image:
    img = Image.new("RGB", (1200, 1500), (250, 248, 242))
    d = ImageDraw.Draw(img)
    y = 80
    for text, size, bold in [
        ("TESLİM TUTANAĞI", 44, True),
        ("(sahte veri - BulutBelge örneği)", 22, False),
        ("", 20, False),
        (f"Teslim alan: {AD2}", 32, False),
        (f"TC Kimlik No: {TC2}", 32, False),
        (f"Telefon: {TEL2}", 32, False),
    ]:
        if text:
            d.text((80, y), text, fill=(30, 32, 40), font=font(size, bold))
        y += int(size * 1.9)
    d.text((700, 1150), signature_label, fill=(30, 32, 40), font=font(28))
    pts = [(760 + i * 3.2, 1230 + 30 * math.sin(i / 5) + rng.uniform(-3, 3)) for i in range(80)]
    d.line(pts, fill=(25, 40, 120), width=4, joint="curve")
    return img


def rotated_signatures(out: Path) -> None:
    # EXIF yönü: 3 = 180°, 6 = saat yönünde 90° göster, 8 = saat yönünün tersine 90° göster.
    for orientation, angle in ((3, 180), (6, 90), (8, 270)):
        img = _form("Teslim alan imza:").rotate(angle, expand=True)
        exif = Image.Exif()
        exif[0x0112] = orientation
        name = f"donuk-imza-{orientation}.jpg"
        img.save(out / name, quality=90, exif=exif)
        expect(name, TC2, TEL2, note="İmza silinmeli ve karartma kutusu doğru yerde olmalı: gözle kontrol (1.74)")


# ---------------------------------------------------------------- 1.57 Word gizli yerler


def hidden_word(out: Path) -> None:
    import docx
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    d = docx.Document()
    d.core_properties.author = AD2
    d.core_properties.title = f"{AD1} dosyası"
    d.core_properties.comments = f"Hazırlayan TC {TC2}"
    d.sections[0].header.paragraphs[0].text = f"Dosya sahibi: {AD1}"
    d.sections[0].footer.paragraphs[0].text = f"İletişim: {MAIL1}"
    d.add_heading("GİZLİ YERLER DENEMESİ (sahte veri)", 1)
    p = d.add_paragraph("Ana metin: başvuran TC ")
    p.add_run(TC1[:6])
    p.add_run(TC1[6:]).bold = True  # biçimle bölünmüş numara
    # Köprü ipucu (tooltip) ve adresinde e-posta.
    part = d.part
    r_id = part.relate_to(f"mailto:{MAIL2}", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink", is_external=True)
    p = d.add_paragraph("Bağlantı: ")
    p._p.append(parse_xml(
        f'<w:hyperlink {nsdecls("w", "r")} r:id="{r_id}" w:tooltip="{AD3} {TEL2}"><w:r><w:t>buraya yazın</w:t></w:r></w:hyperlink>'
    ))
    # Metin kutusu (VML/DrawingML yerine basit: çerçeveli paragraf + w:txbxContent).
    p = d.add_paragraph()
    p._p.append(parse_xml(
        f'<w:r {nsdecls("w")}><w:pict><v:shape xmlns:v="urn:schemas-microsoft-com:vml" style="width:200pt;height:40pt">'
        f'<v:textbox><w:txbxContent><w:p><w:r><w:t>Kutudaki not: {TEL1}</w:t></w:r></w:p></w:txbxContent></v:textbox>'
        f"</v:shape></w:pict></w:r>"
    ))
    # Görsel ve alternatif metni.
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), (200, 200, 210)).save(buf, "PNG")
    buf.seek(0)
    d.add_picture(buf)
    for el in d.element.body.iter():
        if el.tag.endswith("}docPr"):
            el.set("descr", f"{AD1} kimlik fotoğrafı, TC {TC3}")
    # Yorum (python-docx 1.2+).
    if hasattr(d, "add_comment"):
        para = d.add_paragraph("Yorumlu paragraf.")
        d.add_comment(para.runs, text=f"Kontrol: {AD2} {TC2}", author=AD2, initials="MD")
    d.save(out / "gizli-word.docx")
    expect(
        "gizli-word.docx", AD1, AD2, AD3, TC1, TC2, TC3, TEL1, TEL2, MAIL1, MAIL2,
        note="Ad soyadlar etiketsiz geçtiği yerlerde (üst bilgi, ipucu, alternatif metin) bulunamayabilir: hangilerinin kaçtığını raporla",
    )


# ---------------------------------------------------------------- 1.62 / 1.65 bölünmüş tablo


def split_sheet(out: Path) -> None:
    import datetime

    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Liste"
    ws.append(["Ad", "Soyad", "TC (ilk 6)", "TC (son 5)", "Doğum tarihi", "Telefon", "Not"])
    rows = [
        ("Ayşe", "Yılmaz", TC1[:6], TC1[6:], datetime.date(1987, 3, 14), 5320001234, ""),
        ("Mehmet", "Demir", TC2[:6], TC2[6:], datetime.date(1979, 11, 2), 5410005678, f"yedek TC {TC3}"),
    ]
    for r in rows:
        ws.append(list(r))
    for c in ws["E"][1:]:
        c.number_format = "DD.MM.YYYY"
    ws.column_dimensions["G"].hidden = True
    gizli = wb.create_sheet("Arşiv")
    gizli.sheet_state = "hidden"
    gizli.append(["Eski kayıt", AD3, TC3, MAIL1])
    wb.save(out / "bolunmus-tablo.xlsx")
    expect(
        "bolunmus-tablo.xlsx", TC3, MAIL1, "5320001234",
        note="TC iki hücreye bölünmüş (birleşik değer aranır); tarih biçimli doğum tarihi bilinen sınır; gizli sayfa ve sütun da taranmalı",
    )
    expect("bolunmus-tablo.xlsx", TC1, TC2)


def main() -> None:
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    for make in (mixed_text, hidden_layers_pdf, glyph_pdf, named_file, rotated_signatures, hidden_word, split_sheet):
        make(out)
    (out / "beklenen.json").write_text(json.dumps(EXPECTED, ensure_ascii=False, indent=2), encoding="utf-8")
    for p in sorted(out.iterdir()):
        print(f"{p.name:30} {p.stat().st_size // 1024:>5} KB")


if __name__ == "__main__":
    main()
