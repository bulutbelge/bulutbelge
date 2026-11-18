import io
import zipfile
from pathlib import Path

import docx
import pytest
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

from bulutbelge_core.pdf import PdfError
from bulutbelge_core.rules import Rules
from bulutbelge_core.word import all_text, mask_word, scan_word

from fake_data import fake_iban, fake_tc

TC = fake_tc()
IBAN = fake_iban()


def _hyperlink(paragraph, url: str, text: str) -> None:
    rid = paragraph.part.relate_to(url, docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    link = OxmlElement("w:hyperlink")
    link.set(qn("r:id"), rid)
    run = OxmlElement("w:r")
    t = OxmlElement("w:t")
    t.text = text
    run.append(t)
    link.append(run)
    paragraph._p.append(link)


@pytest.fixture
def word_file(tmp_path: Path) -> Path:
    d = docx.Document()
    d.core_properties.author = "Ayşe Yılmaz"
    d.core_properties.title = "Gizli sözleşme"
    d.sections[0].header.paragraphs[0].text = "İletişim: 0532 000 12 34"
    d.add_heading("Sözleşme (sahte veri)", 1)
    p = d.add_paragraph("TC kimlik no: ")
    # TC numarası iki ayrı biçim parçasına bölünmüş (Word bunu sık yapar).
    p.add_run(TC[:4]).bold = True
    p.add_run(TC[4:])
    p.add_run(" (kalın kısım dahil)")
    table = d.add_table(rows=1, cols=2)
    table.cell(0, 0).text = "IBAN"
    table.cell(0, 1).text = IBAN
    link_p = d.add_paragraph("Bize yazın: ")
    _hyperlink(link_p, "mailto:ayse.yilmaz@example.com", "ayse.yilmaz@example.com")
    d.add_paragraph("Adres: Caferağa Mah. Moda Cad. No:12 Kadıköy/İstanbul")
    path = tmp_path / "sozlesme.docx"
    d.save(path)
    return path


def test_scan_finds_split_runs_header_table_and_link(word_file):
    scan = scan_word(word_file, Rules.from_dict(None))
    types = sorted(f.finding.type for f in scan.findings)
    assert types == ["adres", "eposta", "iban", "tc_kimlik", "telefon"]
    tc = next(f for f in scan.findings if f.finding.type == "tc_kimlik")
    assert tc.finding.value == TC


def test_mask_removes_everywhere_and_keeps_word_valid(word_file, tmp_path):
    target, masked, _ = mask_word(word_file, tmp_path / "out.docx", Rules.from_dict(None))
    assert masked == 5
    data = Path(target).read_bytes()
    everything = all_text(data)
    for secret in (TC, "0532 000 12 34", "ayse.yilmaz@example.com", "Ayşe Yılmaz", "Gizli sözleşme", "Moda Cad."):
        assert secret not in everything
    assert IBAN.replace(" ", "")[-4:] in everything  # IBAN: son 4 hane açık
    assert "İstanbul" in everything  # adres: sadece il (Türkçe harf korunur)

    # Word ile açılabilir olmalı; biçim (kalın) ve tablo korunur.
    out = docx.Document(target)
    body = "\n".join(p.text for p in out.paragraphs)
    assert "TC kimlik no: █████ (kalın kısım dahil)" in body
    assert any(r.bold for r in out.paragraphs[1].runs)
    assert out.tables[0].cell(0, 0).text == "IBAN"
    assert out.core_properties.author == ""


def test_tracked_deletion_is_removed(tmp_path):
    d = docx.Document()
    p = d.add_paragraph("Güncel metin. ")
    deleted = OxmlElement("w:del")
    deleted.set(qn("w:id"), "1")
    deleted.set(qn("w:author"), "Mehmet Demir")
    run = OxmlElement("w:r")
    dt = OxmlElement("w:delText")
    dt.text = f"Eski TC: {TC}"
    run.append(dt)
    deleted.append(run)
    p._p.append(deleted)
    src = tmp_path / "izli.docx"
    d.save(src)

    scan = scan_word(src, Rules.from_dict(None))
    assert any("izlenen değişiklik" in w for w in scan.warnings)
    target, _, _ = mask_word(src, tmp_path / "o.docx", Rules.from_dict(None))
    everything = all_text(Path(target).read_bytes())
    assert TC not in everything and "Mehmet Demir" not in everything


def test_not_a_word_file(tmp_path):
    p = tmp_path / "x.docx"
    p.write_bytes(b"bu bir zip degil")
    with pytest.raises(PdfError):
        scan_word(p, Rules.from_dict(None))


def test_old_doc_binary_gives_clear_error(tmp_path):
    # Eski ikili .doc (OLE) dosyası; uzantı .docx'e çevrilmiş olsa bile açık hata verilir.
    p = tmp_path / "eski.docx"
    p.write_bytes(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1" + b"\x00" * 512)
    with pytest.raises(PdfError, match="desteklenmiyor"):
        scan_word(p, Rules.from_dict(None))


def test_old_doc_extension_is_rejected_with_message(tmp_path):
    from bulutbelge_core.documents import kind_of

    with pytest.raises(PdfError, match=r"\.doc.*desteklenmiyor"):
        kind_of(tmp_path / "eski.doc")


def test_attribute_texts_are_masked(tmp_path):
    """Görsel alternatif metni ve köprü ipucundaki kişisel veri de maskelenir (TAKIP 1.57)."""
    from docx.oxml import parse_xml
    from docx.oxml.ns import nsdecls

    tc2 = fake_tc("287654321")
    src = tmp_path / "ozellik.docx"
    d = docx.Document()
    d.add_paragraph(f"Ana metin: TC {TC}")
    rid = d.part.relate_to("https://example.com/", docx.opc.constants.RELATIONSHIP_TYPE.HYPERLINK, is_external=True)
    p = d.add_paragraph("Bağlantı: ")
    p._p.append(parse_xml(
        f'<w:hyperlink {nsdecls("w", "r")} r:id="{rid}" w:tooltip="TC {tc2}"><w:r><w:t>buraya</w:t></w:r></w:hyperlink>'
    ))
    d.save(src)
    out = tmp_path / "ozellik_maskeli.docx"
    mask_word(src, out, Rules.from_dict(None))
    with zipfile.ZipFile(out) as z:
        raw = z.read("word/document.xml").decode("utf-8")
    assert TC not in raw and tc2 not in raw


def _kotu_office(src: Path, dst: Path, ana: str, iliski_yolu: str, ana_parca: str, ekler: dict[str, bytes]) -> None:
    """Yalnızca yapı: makro, OLE, ActiveX, dış bağlantı parçaları sahte baytlarla eklenir."""
    with zipfile.ZipFile(src) as zi, zipfile.ZipFile(dst, "w") as zo:
        for info in zi.infolist():
            data = zi.read(info.filename)
            if info.filename == "[Content_Types].xml":
                data = data.replace(
                    b"application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml",
                    b"application/vnd.ms-word.document.macroEnabled.main+xml",
                )
                data = data.replace(
                    b"</Types>", b'<Override PartName="/word/vbaProject.bin" ContentType="application/vnd.ms-office.vbaProject"/></Types>'
                )
            if info.filename == iliski_yolu:
                extra = (
                    b'<Relationship Id="rIdV" Type="http://schemas.microsoft.com/office/2006/relationships/vbaProject" Target="vbaProject.bin"/>'
                    b'<Relationship Id="rIdO" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/oleObject" Target="embeddings/oleObject1.bin"/>'
                    b'<Relationship Id="rIdA" Type="http://schemas.microsoft.com/office/2006/relationships/activeXControl" Target="activeX/activeX1.xml"/>'
                    b'<Relationship Id="rIdT" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/attachedTemplate" Target="http://sahte.invalid/sablon.dotm" TargetMode="External"/>'
                    b'<Relationship Id="rIdH" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://ornek.invalid/" TargetMode="External"/>'
                )
                data = data.replace(b"</Relationships>", extra + b"</Relationships>")
            if info.filename == ana_parca:
                data = data.replace(
                    b"</w:body>",
                    b'<w:p><w:r><w:object><o:OLEObject xmlns:o="urn:schemas-microsoft-com:office:office" r:id="rIdO" '
                    b'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/></w:object></w:r></w:p>'
                    b'<w:p><w:r><w:instrText>DDEAUTO sahte-komut</w:instrText></w:r></w:p></w:body>',
                )
            zo.writestr(info.filename, data)
        for name, content in ekler.items():
            zo.writestr(name, content)


def test_word_aktif_icerik_makro_ole_activex_dis_baglanti_silinir(word_file, tmp_path):
    kotu = tmp_path / "kotu.docx"
    _kotu_office(
        word_file, kotu, "word", "word/_rels/document.xml.rels", "word/document.xml",
        {
            "word/vbaProject.bin": b"SAHTE-MAKRO",
            "word/embeddings/oleObject1.bin": b"SAHTE-OLE",
            "word/activeX/activeX1.xml": b"<ax/>",
            "word/activeX/activeX1.bin": b"SAHTE-AX",
        },
    )
    out, _, _ = mask_word(kotu, tmp_path / "cikti.docx", Rules.from_dict({}))
    with zipfile.ZipFile(out) as z:
        adlar = z.namelist()
        tum = b"".join(z.read(n) for n in adlar)
    assert not [n for n in adlar if "vba" in n.lower() or "embeddings" in n or "activeX" in n]
    for iz in (b"SAHTE-MAKRO", b"SAHTE-OLE", b"SAHTE-AX", b"macroEnabled", b"vbaProject", b"oleObject", b"attachedTemplate",
               b"DDEAUTO", b"OLEObject"):
        assert iz not in tum, iz
    assert b"https://ornek.invalid/" in tum  # köprü hedefi kalabilir
    assert docx.Document(out).paragraphs  # dosya hâlâ açılır
