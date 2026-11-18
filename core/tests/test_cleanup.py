"""Temizlik özeti (TAKIP 1.67): yalnızca sahte yazar ve yorumlarla."""

import docx
import openpyxl
import pymupdf
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from openpyxl.comments import Comment

from bulutbelge_core.cleanup import cleanup_summary

AUTHOR = "Sahte Yazar"


def test_word_tracked_changes_authors_and_meta(tmp_path):
    d = docx.Document()
    p = d.add_paragraph("Metin")
    for tag, text_tag in (("w:del", "w:delText"), ("w:ins", "w:t")):
        el = OxmlElement(tag)
        el.set(qn("w:id"), "1")
        el.set(qn("w:author"), AUTHOR)
        run = OxmlElement("w:r")
        t = OxmlElement(text_tag)
        t.text = "x"
        run.append(t)
        el.append(run)
        p._p.append(el)
    d.core_properties.author = AUTHOR
    d.core_properties.title = "Sahte başlık"
    src = tmp_path / "a.docx"
    d.save(src)
    s = cleanup_summary(src)
    assert s["izlenen_silme"] == 1 and s["izlenen_ekleme"] == 1 and s["yazar"] == 1
    assert "yazar" in s["meta"] and "başlık" in s["meta"]
    assert AUTHOR not in str(s)


def test_excel_comment_and_author(tmp_path):
    wb = openpyxl.Workbook()
    wb.active["A1"] = "x"
    wb.active["A1"].comment = Comment("sahte not", AUTHOR)
    src = tmp_path / "a.xlsx"
    wb.save(src)
    s = cleanup_summary(src)
    assert s["yorum"] == 1 and s["yazar"] == 1
    assert AUTHOR not in str(s) and "sahte not" not in str(s)


def test_pdf_metadata_and_annotation(tmp_path):
    doc = pymupdf.open()
    page = doc.new_page()
    note = page.add_text_annot((50, 50), "sahte yorum")
    note.set_info(title=AUTHOR)
    note.update()
    doc.set_metadata({"author": AUTHOR, "title": "Sahte"})
    src = tmp_path / "a.pdf"
    doc.save(src)
    s = cleanup_summary(src)
    assert s["yorum"] == 1 and s["yazar"] == 1 and {"yazar", "başlık"} <= set(s["meta"])
    assert AUTHOR not in str(s)


def test_unsupported_or_broken_returns_none(tmp_path):
    t = tmp_path / "a.txt"
    t.write_text("x")
    assert cleanup_summary(t) is None
    bad = tmp_path / "b.docx"
    bad.write_bytes(b"degil")
    assert cleanup_summary(bad) is None
