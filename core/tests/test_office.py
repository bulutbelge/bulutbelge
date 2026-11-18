"""PowerPoint ve Excel (ortak Office motoru)."""

from pathlib import Path

import openpyxl
import pptx
from openpyxl.comments import Comment

from bulutbelge_core import office
from bulutbelge_core.slides import slide_of_part, slide_preview
from bulutbelge_core.rules import Rules

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()


def _pptx(path: Path) -> Path:
    p = pptx.Presentation()
    s1 = p.slides.add_slide(p.slide_layouts[1])
    s1.shapes.title.text = "Müşteri sunumu (sahte veri)"
    body = s1.placeholders[1].text_frame
    body.text = "Ad Soyad: Ayşe Yılmaz"
    para = body.add_paragraph()
    para.add_run().text = "TC: " + TC[:5]
    para.add_run().text = TC[5:]  # iki parçaya bölünmüş numara
    s1.notes_slide.notes_text_frame.text = "Notlar: müşteriyi 0532 000 12 34 numarasından ara"
    s2 = p.slides.add_slide(p.slide_layouts[1])
    s2.shapes.title.text = "Ödeme"
    s2.placeholders[1].text_frame.text = f"IBAN: {IBAN}"
    p.core_properties.author = "Mehmet Demir"
    p.save(path)
    return path


def _xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Müşteriler"
    ws.append(["Ad Soyad", "TC", "Telefon", "E-posta", "Not"])
    ws.append(["Ayşe Yılmaz", int(TC), "0532 000 12 34", "ayse@example.com", "Ayşe Yılmaz VIP"])
    ws.append(["Mehmet Demir", 23456789140, 5410005678, "m.demir@example.com", ""])
    ws["E3"].comment = Comment("Mehmet Demir aradı: 0505 000 90 12", "Zeynep Kaya")
    ws2 = wb.create_sheet("Ödemeler")
    ws2.append(["IBAN", IBAN])
    wb.properties.creator = "Zeynep Kaya"
    wb.save(path)
    return path


def test_pptx_scan_mask_and_slide_boxes(tmp_path):
    src = _pptx(tmp_path / "sunum.pptx")
    rules = Rules.from_dict(None)
    scan = office.scan(src, office.POWERPOINT, rules)
    types = sorted(f.finding.type for f in scan.findings)
    assert types == ["iban", "kisi_adi", "tc_kimlik", "telefon"]

    # Önizleme: slaytlar sırayla, paragraflar bulgularla aynı birim anahtarını taşır.
    preview = slide_preview(src)
    assert len(preview["slides"]) == 2
    units_on_slide1 = {
        p["unit"] for item in preview["slides"][0]["items"] if item["kind"] == "text" for p in item["paragraphs"]
    }
    name = next(f for f in scan.findings if f.finding.type == "kisi_adi")
    assert f"{name.part}:{name.unit}" in units_on_slide1
    notes_units = {p["unit"] for p in preview["slides"][0]["notes"]}
    phone = next(f for f in scan.findings if f.finding.type == "telefon")
    assert f"{phone.part}:{phone.unit}" in notes_units  # konuşmacı notunda
    assert slide_of_part(src)[phone.part] == 1
    # Yer tutucu kutular konumunu düzenden alır.
    assert all(item["w"] > 0 for item in preview["slides"][0]["items"])

    target, masked, _ = office.mask(src, tmp_path / "out.pptx", office.POWERPOINT, rules)
    assert masked == 4
    everything = office.all_text(Path(target).read_bytes())
    for secret in ("Ayşe Yılmaz", TC, "0532 000 12 34", "Mehmet Demir"):
        assert secret not in everything
    again = pptx.Presentation(target)  # PowerPoint ile açılabilir
    assert "[AD SOYAD]" in again.slides[0].placeholders[1].text_frame.text


def test_xlsx_numbers_formulas_comments_and_grid(tmp_path):
    src = _xlsx(tmp_path / "liste.xlsx")
    rules = Rules.from_dict(None)
    scan = office.scan(src, office.EXCEL, rules)
    types = sorted(f.finding.type for f in scan.findings)
    assert "tc_kimlik" in types  # sayı hücresindeki TC de bulunur
    assert "telefon" in types and "eposta" in types and "iban" in types and "kisi_adi" in types

    grid = office.sheet_preview(src)
    assert [s["name"] for s in grid] == ["Müşteriler", "Ödemeler"]
    first = grid[0]["rows"][1]["cells"]
    assert first[0]["text"] == "Ayşe Yılmaz" and first[0]["unit"]
    assert first[1]["text"] == TC and first[1]["unit"]  # sayı hücresi de birim

    target, _masked, _ = office.mask(src, tmp_path / "out.xlsx", office.EXCEL, rules)
    everything = office.all_text(Path(target).read_bytes())
    for secret in (TC, "Ayşe Yılmaz", "Mehmet Demir", "Zeynep Kaya", "ayse@example.com", "0505 000 90 12"):
        assert secret not in everything
    wb = openpyxl.load_workbook(target)  # Excel ile açılabilir
    ws = wb["Müşteriler"]
    assert ws["B2"].value == "█████"  # sayı hücresi metne çevrildi
    assert ws["A1"].value == "Ad Soyad"
    assert wb.properties.creator in (None, "")


def test_xlsx_split_cells_tc_masked(tmp_path):
    tc = fake_tc("198765432")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Ad", "a", "b", "c", "d"])
    ws.append(["Ali", tc[:3], tc[3:6], tc[6:9], tc[9:]])  # metin hücreleri (paylaşılan metin)
    ws.append(["Veli", "12", "34", "56", "78"])
    src = tmp_path / "bolunmus.xlsx"
    wb.save(src)
    rules = Rules.from_dict(None)
    scan = office.scan(src, office.EXCEL, rules)
    assert sorted(f.finding.type for f in scan.findings) == ["tc_kimlik"] * 4
    target, _n, _w = office.mask(src, tmp_path / "out.xlsx", office.EXCEL, rules)
    ws2 = openpyxl.load_workbook(target).active
    assert [c.value for c in ws2[2][1:]] != [tc[:3], tc[3:6], tc[6:9], tc[9:]]
    assert all(c.value not in (tc[:3], tc[3:6], tc[6:9], tc[9:]) for c in ws2[2][1:])
    assert [c.value for c in ws2[3][1:]] == ["12", "34", "56", "78"]


def test_excel_dis_kitap_baglantisi_ve_makro_silinir(tmp_path):
    import io
    import zipfile

    import openpyxl

    from bulutbelge_core import office

    wb = openpyxl.Workbook()
    wb.active["A1"] = "ornek"
    src = tmp_path / "k.xlsx"
    wb.save(src)
    kotu = tmp_path / "kotu.xlsx"
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(kotu, "w") as zo:
        for info in zi.infolist():
            data = zi.read(info.filename)
            if info.filename == "xl/workbook.xml":
                data = data.replace(b"</workbook>", b'<externalReferences><externalReference xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" r:id="rIdE"/></externalReferences></workbook>')
            if info.filename == "xl/_rels/workbook.xml.rels":
                data = data.replace(
                    b"</Relationships>",
                    b'<Relationship Id="rIdE" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/externalLink" Target="externalLinks/externalLink1.xml"/>'
                    b'<Relationship Id="rIdV" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/></Relationships>',
                )
            zo.writestr(info.filename, data)
        zo.writestr("xl/externalLinks/externalLink1.xml", b"<externalLink>sahte</externalLink>")
        zo.writestr("xl/externalLinks/_rels/externalLink1.xml.rels", b"<Relationships/>")
        zo.writestr("xl/vbaProject.bin", b"SAHTE-MAKRO")
    out, _, _ = office.mask(kotu, tmp_path / "c.xlsx", office.EXCEL, Rules.from_dict({}))
    with zipfile.ZipFile(out) as z:
        adlar = z.namelist()
        tum = b"".join(z.read(n) for n in adlar)
    assert not [n for n in adlar if "externalLink" in n or "vba" in n]
    assert b"externalReference" not in tum and b"SAHTE-MAKRO" not in tum
    assert office.aktif_icerik_kaldi(open(out, "rb").read()) == []
