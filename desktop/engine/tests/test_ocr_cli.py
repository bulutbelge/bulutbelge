"""K3: OCR kullanılamıyorsa ajan `mask` hata koduyla reddedilir, `read` uyarıyla sürer. Veriler sahtedir."""

import io
import json
import os

import pymupdf
import pytest
from PIL import Image, ImageDraw

from bulutbelge_core import ocr, pdf
from bulutbelge_engine import cli, journal, settings
from bulutbelge_engine.protocol import handle_line

TC = "12345678950"  # doğrulamadan geçen sahte numara


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], *argv], out, err)
    return code, out.getvalue(), err.getvalue()


@pytest.fixture
def scanned(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr, "ocr_available", lambda: False)
    monkeypatch.setattr(pdf, "ocr_available", lambda: False)
    d = tmp_path / "belgeler"
    d.mkdir()
    img = Image.new("RGB", (900, 200), "white")
    ImageDraw.Draw(img).text((20, 80), f"TC {TC}", fill="black")
    buf = io.BytesIO()
    img.save(buf, "PNG")
    doc = pymupdf.open()
    doc.new_page().insert_image(pymupdf.Rect(40, 100, 560, 220), stream=buf.getvalue())
    path = d / "tarama.pdf"
    doc.save(path)
    doc.close()
    resp = handle_line(json.dumps({"id": 1, "method": "agent.save", "params": {"folders": [str(d)], "allow_write": True}}))
    assert "error" not in resp
    return path


def test_cli_mask_refused_with_error_code_when_ocr_missing(scanned):
    code, out, err = run_cli("mask", str(scanned), "--ajan", "deneme")
    assert code == cli.EXIT_ERROR and out == ""
    assert "Hata (ocr_unavailable)" in err and "OCR kullanılamıyor" in err
    assert [p.name for p in scanned.parent.iterdir()] == ["tarama.pdf"]
    rec = json.loads((settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8").splitlines()[-1])
    assert rec["op"] == "maskeleme" and rec["result"] == "hata" and rec["error"] == "ocr_unavailable"


def test_cli_read_continues_with_warning_when_ocr_missing(scanned):
    code, out, err = run_cli("read", str(scanned), "--json")
    assert code == 0, err
    data = json.loads(out)
    assert TC not in data["text"]
    assert any("OCR dil dosyaları kurulu değil" in w for w in data["summary"]["uyarilar"])
