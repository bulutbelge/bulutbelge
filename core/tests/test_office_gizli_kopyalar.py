"""K2: Office'te kullanıcının göremediği kopyalar (pivot önbelleği, grafik önbelleği, people.xml,
TitlesOfParts, gömülü görsel meta verisi) ve taranamayan görsel uyarıları. Tüm veriler sahtedir."""

from __future__ import annotations

import io
import shutil
import subprocess
import zipfile
from pathlib import Path

import docx
import openpyxl
import pptx
import pytest
from PIL import ExifTags, Image
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from bulutbelge_core import office
from bulutbelge_core.image import strip_metadata
from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules
from bulutbelge_core.udf import scan_udf

from fake_data import fake_tc

TC = fake_tc("123456789")
TC2 = fake_tc("234567891")
AD, AD2 = "Ayşe Yılmaz", "Mehmet Demir"
TELEFON = "0532 000 12 34"


def _rules() -> Rules:
    return Rules.from_dict(None)


def _parts_text(path: Path) -> str:
    """Kopyadaki tüm parçaların ham metni (XML çözülmeden; hiçbir yerde kalmasın)."""
    with zipfile.ZipFile(path) as z:
        return "\n".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def _rewrite(path: Path, changes: dict[str, bytes]) -> None:
    """ZIP içindeki parçaları değiştirir ya da ekler (elle XML parçası koymak için)."""
    with zipfile.ZipFile(path) as z:
        items = {n: z.read(n) for n in z.namelist()}
    items.update(changes)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, data in items.items():
            z.writestr(n, data)


def _mask(src: Path, fmt: office.OfficeFormat, **kw) -> tuple[Path, list[str]]:
    out, _n, warnings = office.mask(src, src.with_name(src.stem + "_maskeli" + src.suffix), fmt, _rules(), **kw)
    return Path(out), warnings


# ---------------------------------------------------------------- pivot önbelleği

S_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PR = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _pivot_xlsx(path: Path) -> Path:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Veri"
    ws.append(["Ad Soyad", "TC", "Tutar"])
    ws.append([AD, TC, 100])
    ws.append([AD2, TC2, 250])
    wb.save(path)
    definition = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pivotCacheDefinition xmlns="{S_NS}" xmlns:r="{R_NS}" r:id="rId1" refreshedBy="{AD}" refreshedDate="45000" createdVersion="6" refreshedVersion="6" minRefreshableVersion="3" recordCount="2">
<cacheSource type="worksheet"><worksheetSource ref="A1:C3" sheet="Veri"/></cacheSource>
<cacheFields count="3">
<cacheField name="Ad Soyad" numFmtId="0"><sharedItems count="2"><s v="{AD}"/><s v="{AD2}"/></sharedItems></cacheField>
<cacheField name="TC" numFmtId="0"><sharedItems count="2"><s v="{TC}"/><s v="{TC2}"/></sharedItems></cacheField>
<cacheField name="Tutar" numFmtId="0"><sharedItems containsSemiMixedTypes="0" containsString="0" containsNumber="1" containsInteger="1" minValue="100" maxValue="250"/></cacheField>
</cacheFields></pivotCacheDefinition>"""
    records = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pivotCacheRecords xmlns="{S_NS}" xmlns:r="{R_NS}" count="2">
<r><x v="0"/><x v="0"/><n v="100"/></r><r><x v="1"/><x v="1"/><n v="250"/></r></pivotCacheRecords>"""
    table = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<pivotTableDefinition xmlns="{S_NS}" name="OzetTablo1" cacheId="1" applyNumberFormats="0" applyBorderFormats="0" applyFontFormats="0" applyPatternFormats="0" applyAlignmentFormats="0" applyWidthHeightFormats="1" dataCaption="Değerler" updatedVersion="6" minRefreshableVersion="3" createdVersion="6" indent="0" outline="1" outlineData="1">
<location ref="E1:F4" firstHeaderRow="1" firstDataRow="1" firstDataCol="1"/>
<pivotFields count="3">
<pivotField axis="axisRow" showAll="0"><items count="3"><item x="0"/><item x="1"/><item t="default"/></items></pivotField>
<pivotField showAll="0"/>
<pivotField dataField="1" showAll="0"/>
</pivotFields>
<rowFields count="1"><field x="0"/></rowFields>
<rowItems count="3"><i><x/></i><i><x v="1"/></i><i t="grand"><x/></i></rowItems>
<colItems count="1"><i/></colItems>
<dataFields count="1"><dataField name="Toplam Tutar" fld="2" baseField="0" baseItem="0"/></dataFields>
</pivotTableDefinition>"""
    with zipfile.ZipFile(path) as z:
        ct = z.read("[Content_Types].xml").decode()
        wb_xml = z.read("xl/workbook.xml").decode()
        wb_rels = z.read("xl/_rels/workbook.xml.rels").decode()
    ct = ct.replace(
        "</Types>",
        '<Override PartName="/xl/pivotCache/pivotCacheDefinition1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheDefinition+xml"/>'
        '<Override PartName="/xl/pivotCache/pivotCacheRecords1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotCacheRecords+xml"/>'
        '<Override PartName="/xl/pivotTables/pivotTable1.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.pivotTable+xml"/></Types>',
    )
    wb_rels = wb_rels.replace(
        "</Relationships>",
        f'<Relationship Id="rIdPivot1" Type="{PR}/pivotCacheDefinition" Target="pivotCache/pivotCacheDefinition1.xml"/>'
        "</Relationships>",
    )
    wb_xml = wb_xml.replace("</workbook>", '<pivotCaches><pivotCache cacheId="1" r:id="rIdPivot1"/></pivotCaches></workbook>')
    if 'xmlns:r=' not in wb_xml.split(">", 2)[1]:
        wb_xml = wb_xml.replace("<workbook ", f'<workbook xmlns:r="{R_NS}" ', 1)
    _rewrite(
        path,
        {
            "[Content_Types].xml": ct.encode(),
            "xl/workbook.xml": wb_xml.encode(),
            "xl/_rels/workbook.xml.rels": wb_rels.encode(),
            "xl/pivotCache/pivotCacheDefinition1.xml": definition.encode(),
            "xl/pivotCache/pivotCacheRecords1.xml": records.encode(),
            "xl/pivotCache/_rels/pivotCacheDefinition1.xml.rels": (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                f'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                f'Type="{PR}/pivotCacheRecords" Target="pivotCacheRecords1.xml"/></Relationships>'
            ).encode(),
            "xl/pivotTables/pivotTable1.xml": table.encode(),
            "xl/pivotTables/_rels/pivotTable1.xml.rels": (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                f'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                f'Type="{PR}/pivotCacheDefinition" Target="../pivotCache/pivotCacheDefinition1.xml"/></Relationships>'
            ).encode(),
            "xl/worksheets/_rels/sheet1.xml.rels": (
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships '
                f'xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" '
                f'Type="{PR}/pivotTable" Target="../pivotTables/pivotTable1.xml"/></Relationships>'
            ).encode(),
        },
    )
    return path


def test_pivot_records_emptied_definition_refreshes_on_load(tmp_path):
    src = _pivot_xlsx(tmp_path / "ozet.xlsx")
    assert openpyxl.load_workbook(src)["Veri"]._pivots  # sahte dosya geçerli: openpyxl özet tabloyu okuyor
    out, warnings = _mask(src, office.EXCEL)
    text = _parts_text(out)
    for value in (AD, AD2, TC, TC2):
        assert value not in text, value
    with zipfile.ZipFile(out) as z:
        records = z.read("xl/pivotCache/pivotCacheRecords1.xml").decode()
        definition = z.read("xl/pivotCache/pivotCacheDefinition1.xml").decode()
    assert 'count="0"' in records and "<r>" not in records and "<r/>" not in records
    assert 'refreshOnLoad="1"' in definition
    assert definition.count("<s ") == 4  # öğe sayısı korunur (özet tablo sırayla başvurur)
    assert any("özet tablo" in w for w in warnings)
    # Kopya açılır ve özet tablo okunur.
    pivot = openpyxl.load_workbook(out)["Veri"]._pivots[0]
    assert pivot.cache.refreshOnLoad and pivot.cache.records.count == 0


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice yok")
def test_pivot_copy_opens_in_libreoffice(tmp_path):
    out, _ = _mask(_pivot_xlsx(tmp_path / "ozet.xlsx"), office.EXCEL)
    conv = tmp_path / "donusum"
    r = subprocess.run(
        ["soffice", f"-env:UserInstallation=file://{tmp_path / 'lo'}", "--headless", "--convert-to", "csv",
         "--outdir", str(conv), str(out)],
        capture_output=True, timeout=180,
    )
    csv = next(conv.glob("*.csv"), None) if conv.exists() else None
    assert r.returncode == 0 and csv is not None, r.stderr
    content = csv.read_text(encoding="utf-8", errors="replace")
    assert "Ad Soyad" in content and AD not in content and TC not in content


# ---------------------------------------------------------------- grafik önbelleği

C_NS = "http://schemas.openxmlformats.org/drawingml/2006/chart"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"


def _chart_xml() -> bytes:
    return f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<c:chartSpace xmlns:c="{C_NS}" xmlns:a="{A_NS}"><c:chart>
<c:title><c:tx><c:rich><a:bodyPr/><a:p><a:r><a:t>{AD} satışları</a:t></a:r></a:p></c:rich></c:tx></c:title>
<c:plotArea><c:barChart><c:barDir val="col"/><c:ser><c:idx val="0"/><c:order val="0"/>
<c:tx><c:strRef><c:f>Veri!$C$1</c:f><c:strCache><c:ptCount val="1"/><c:pt idx="0"><c:v>Tutar {TELEFON}</c:v></c:pt></c:strCache></c:strRef></c:tx>
<c:cat><c:strRef><c:f>Veri!$A$2:$A$3</c:f><c:strCache><c:ptCount val="2"/>
<c:pt idx="0"><c:v>{AD}</c:v></c:pt><c:pt idx="1"><c:v>{AD2}</c:v></c:pt></c:strCache></c:strRef></c:cat>
<c:val><c:numRef><c:f>Veri!$B$2:$B$3</c:f><c:numCache><c:formatCode>General</c:formatCode><c:ptCount val="2"/>
<c:pt idx="0"><c:v>{TC}</c:v></c:pt><c:pt idx="1"><c:v>250</c:v></c:pt></c:numCache></c:numRef></c:val>
</c:ser></c:barChart></c:plotArea></c:chart></c:chartSpace>""".encode()


def test_excel_chart_cache_values_are_masked(tmp_path):
    src = tmp_path / "grafik.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Veri"
    ws.append(["Ad", "Tutar"])
    wb.save(src)
    _rewrite(src, {"xl/charts/chart1.xml": _chart_xml()})  # önbellek tek kopya: değerler hücrelerde yok
    out, warnings = _mask(src, office.EXCEL)
    text = _parts_text(out)
    for value in (AD, AD2, TC, TELEFON):
        assert value not in text, value
    with zipfile.ZipFile(out) as z:
        chart = z.read("xl/charts/chart1.xml").decode()
    assert "[AD SOYAD]" in chart and "<c:v>250</c:v>" in chart  # bulgusuz değer kalır
    assert chart.count("<c:pt ") == 4  # sayı önbelleğinde maskelenen nokta silindi (5 → 4)
    assert any("grafik" in w for w in warnings)
    openpyxl.load_workbook(out)


def test_pptx_chart_cache_and_title_masked_and_opens(tmp_path):
    src = tmp_path / "sunum.pptx"
    p = pptx.Presentation()
    slide = p.slides.add_slide(p.slide_layouts[5])
    data = CategoryChartData()
    data.categories = [AD, AD2]
    data.add_series(f"Arama {TELEFON}", (10, 20))
    gf = slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(6), Inches(4), data)
    gf.chart.has_title = True
    gf.chart.chart_title.text_frame.text = f"{AD} raporu"
    p.save(src)
    out, _ = _mask(src, office.POWERPOINT)
    text = _parts_text(out)
    for value in (AD, AD2, TELEFON):
        assert value not in text, value
    chart = pptx.Presentation(out).slides[0].shapes[-1].chart
    assert len(chart.plots[0].categories) == 2  # grafik yerinde, önbellekten çiziliyor


def test_word_chart_cache_masked(tmp_path):
    src = tmp_path / "rapor.docx"
    d = docx.Document()
    d.add_paragraph("Aylık rapor")
    d.save(src)
    _rewrite(src, {"word/charts/chart1.xml": _chart_xml()})
    out, _ = _mask(src, office.WORD)
    text = _parts_text(out)
    for value in (AD, AD2, TC, TELEFON):
        assert value not in text, value
    docx.Document(out)


# ---------------------------------------------------------------- meta veri

W15_NS = "http://schemas.microsoft.com/office/word/2012/wordml"


def test_word_people_xml_author_and_user_id_removed(tmp_path):
    src = tmp_path / "yorumlu.docx"
    d = docx.Document()
    d.add_paragraph("Sözleşme taslağı")
    d.save(src)
    people = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w15:people xmlns:w15="{W15_NS}"><w15:person w15:author="{AD}">
<w15:presenceInfo w15:providerId="AD" w15:userId="S::ayse.yilmaz@example.com::0000"/></w15:person></w15:people>"""
    _rewrite(src, {"word/people.xml": people.encode()})
    out, _ = _mask(src, office.WORD)
    with zipfile.ZipFile(out) as z:
        cleaned = z.read("word/people.xml").decode()
    assert AD not in cleaned and "ayse.yilmaz" not in cleaned and "presenceInfo" not in cleaned
    assert "w15:person" in cleaned  # yapı korunur (yorumlar yazara başvurur)
    docx.Document(out)


def test_titles_of_parts_masked_and_leak_checked(tmp_path):
    src = tmp_path / "baslikli.docx"
    d = docx.Document()
    d.add_paragraph("Bordro")
    d.save(src)
    app = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>Microsoft Office Word</Application><Company>Örnek Kurum</Company>
<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Başlık</vt:lpstr></vt:variant>
<vt:variant><vt:i4>1</vt:i4></vt:variant></vt:vector></HeadingPairs>
<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>{AD} bordro {TC}</vt:lpstr></vt:vector></TitlesOfParts>
</Properties>"""
    _rewrite(src, {"docProps/app.xml": app.encode()})
    out, _ = _mask(src, office.WORD)
    with zipfile.ZipFile(out) as z:
        props = z.read("docProps/app.xml").decode()
    assert TC not in props and AD not in props and "Örnek Kurum" not in props
    assert "Başlık" in props and "bordro" in props  # yapı ve bulgusuz metin korunur
    docx.Document(out)


def test_leak_check_covers_values_found_in_hidden_parts(tmp_path):
    """TitlesOfParts'ta maskelenen değer başka bir gizli parçada kalırsa dosya yazılmaz."""
    src = tmp_path / "kacak.docx"
    d = docx.Document()
    d.add_paragraph("Bordro")
    d.save(src)
    app = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"
 xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<TitlesOfParts><vt:vector size="1" baseType="lpstr"><vt:lpstr>TC {TC}</vt:lpstr></vt:vector></TitlesOfParts></Properties>"""
    # Taranmayan bir parçada (customXml kapsam dışı) aynı değer.
    _rewrite(src, {"docProps/app.xml": app.encode(), "customXml/item1.xml": f"<kayit><no>{TC}</no></kayit>".encode()})
    with pytest.raises(PdfError, match="Kaçak tespiti"):
        _mask(src, office.WORD)
    assert not list(tmp_path.glob("kacak_maskeli*"))


# ---------------------------------------------------------------- gömülü görsel meta verisi


def _exif_jpeg(orientation: int | None = None) -> bytes:
    img = Image.new("RGB", (240, 120), (40, 120, 200))
    exif = Image.Exif()
    exif[ExifTags.Base.Artist] = "Ornek Kisi"
    exif[ExifTags.Base.Make] = "OrnekKamera"
    exif[ExifTags.Base.Model] = "Model-0000"
    if orientation:
        exif[ExifTags.Base.Orientation] = orientation
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif.tobytes(), quality=90)
    return buf.getvalue()


def test_embedded_jpeg_exif_removed_without_findings(tmp_path):
    jpeg = _exif_jpeg()
    src = tmp_path / "fotolu.docx"
    d = docx.Document()
    d.add_paragraph("Ek fotoğraf")
    d.add_picture(io.BytesIO(jpeg))
    d.save(src)
    out, _ = _mask(src, office.WORD)
    with zipfile.ZipFile(out) as z:
        media = [z.read(n) for n in z.namelist() if "/media/" in n]
    assert len(media) == 1 and media[0] != jpeg
    assert b"Ornek Kisi" not in media[0] and b"OrnekKamera" not in media[0]
    with Image.open(io.BytesIO(media[0])) as im, Image.open(io.BytesIO(jpeg)) as orig:
        assert not im.getexif()
        assert im.tobytes() == orig.tobytes()  # yeniden kodlanmadı: pikseller aynı
    docx.Document(out)


def test_strip_metadata_keeps_orientation_and_png_pixels():
    clean = strip_metadata(_exif_jpeg(orientation=6), ".jpg")
    with Image.open(io.BytesIO(clean)) as im:
        exif = im.getexif()
        assert exif.get(ExifTags.Base.Orientation) == 6 and ExifTags.Base.Artist not in exif
    from PIL.PngImagePlugin import PngInfo

    info = PngInfo()
    info.add_text("Author", "Ornek Kisi")
    buf = io.BytesIO()
    Image.new("RGB", (20, 10), (1, 2, 3)).save(buf, "PNG", pnginfo=info)
    png = strip_metadata(buf.getvalue(), ".png")
    assert b"Ornek Kisi" not in png
    with Image.open(io.BytesIO(png)) as im:
        assert im.getpixel((0, 0)) == (1, 2, 3) and not im.text


# ---------------------------------------------------------------- uyarılar


def test_unscannable_office_images_are_warned(tmp_path):
    src = tmp_path / "gifli.docx"
    d = docx.Document()
    d.add_paragraph("Logo")
    d.save(src)
    _rewrite(src, {"word/media/image9.gif": b"GIF89a" + b"\x00" * 20, "word/media/image8.emf": b"\x01\x00\x00\x00"})
    scan = office.scan(src, office.WORD, _rules())
    warning = next(w for w in scan.warnings if "taranamayan" in w)
    assert "2 görsel" in warning and "GIF" in warning and "EMF" in warning and "kontrol edin" in warning


def test_udf_images_are_warned(tmp_path):
    src = tmp_path / "dilekce.udf"
    content = (
        '<?xml version="1.0" encoding="UTF-8"?><template format_id="1.8"><content><![CDATA[Dilekçe metni]]>'
        '</content><elements resolver="hvl-default"><paragraph><content startOffset="0" length="13"/>'
        "</paragraph></elements></template>"
    )
    with zipfile.ZipFile(src, "w") as z:
        z.writestr("content.xml", content)
        z.writestr("resim1.png", b"\x89PNG\r\n\x1a\n")
    warnings = scan_udf(src, _rules()).warnings
    assert any("1 görsel" in w and "taranmadı" in w and "kontrol edin" in w for w in warnings)


def test_excel_options_do_not_restore_original_hidden_parts(tmp_path):
    """Güvenli temizlik seçenekleri açıkken yazar listesi ve pivot önbelleği özgün hâline dönmemeli."""
    src = _pivot_xlsx(tmp_path / "secenekli.xlsx")
    person = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><personList '
        'xmlns="http://schemas.microsoft.com/office/spreadsheetml/2018/threadedcomments">'
        f'<person displayName="{AD}" id="{{00000000-0000-0000-0000-000000000001}}" userId="ayse@example.com" '
        'providerId="None"/></personList>'
    )
    _rewrite(src, {"xl/persons/person.xml": person.encode()})
    out, _ = _mask(src, office.EXCEL, options={"strip_comments": True, "unhide_sheets": True})
    text = _parts_text(out)
    for value in (AD, AD2, TC, "ayse@example.com"):
        assert value not in text, value
