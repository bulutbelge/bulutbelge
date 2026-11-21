"""`bulutbelge scan`: belgeyi değiştirmeden tarar, değer döndürmez (yalnızca sayılar). Veriler sahtedir."""

import io
import json
import os
from pathlib import Path

import pytest

from bulutbelge_engine import cli, journal, kilavuz, settings
from bulutbelge_engine.protocol import handle_line

TC = "12345678950"  # doğrulamadan geçen sahte numara
AD = "Ayşe Yılmaz"
EPOSTA = "ayse.yilmaz@example.com"


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], *argv], out, err)
    return code, out.getvalue(), err.getvalue()


def log_lines() -> list[dict]:
    p = settings.data_dir() / journal.LOG_FILE
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


@pytest.fixture
def doc(tmp_path) -> Path:
    d = tmp_path / "belgeler"
    d.mkdir()
    p = d / "basvuru.txt"
    p.write_text(f"Başvuran: {AD}\nTC: {TC}\nE-posta: {EPOSTA}\n", encoding="utf-8")
    return p


def allow(folder: Path, **kw) -> None:
    resp = handle_line(json.dumps({"id": 1, "method": "agent.save", "params": {"folders": [str(folder)], **kw}}))
    assert "error" not in resp


def test_scan_returns_counts_only_and_leaves_document_untouched(doc):
    allow(doc.parent, allow_write=True)
    before = doc.read_bytes()
    code, out, err = run_cli("scan", str(doc), "--ajan", "deneme")
    assert code == 0, err
    for value in (AD, TC, EPOSTA, "Yılmaz", "ayse"):
        assert value not in out
    assert "tarama özeti" in out and "TC kimlik no: 1" in out and "Sayfa: 1" in out
    assert doc.read_bytes() == before and sorted(p.name for p in doc.parent.iterdir()) == ["basvuru.txt"]
    rec = log_lines()[-1]
    assert rec["op"] == "okuma" and rec["caller"] == "ajan" and rec["agent"] == "deneme"
    assert rec["result"] == "basarili" and rec["counts"]["tc_kimlik"] == 1
    raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert TC not in raw and AD not in raw


def test_scan_json_has_only_schema_fields(doc):
    allow(doc.parent)
    code, out, err = run_cli("scan", str(doc), "--json")
    assert code == 0, err
    data = json.loads(out)
    assert set(data) == {"ok", "summary"} and data["ok"] is True
    assert list(data["summary"]) == [a for a, _, _ in cli.SCAN_FIELDS]
    s = data["summary"]
    assert s["islem"] == "tarama" and s["bulunan"] == sum(s["turler"].values()) >= 2 and s["sayfa"] == 1
    assert TC not in out and AD not in out and EPOSTA not in out


def test_scan_refused_outside_allowed_folder(doc, tmp_path):
    other = tmp_path / "baska"
    other.mkdir()
    allow(other)
    code, out, _ = run_cli("scan", str(doc))
    assert code == cli.EXIT_REFUSED and out == ""
    assert log_lines()[-1]["result"] == "reddedildi"


def test_scan_respects_profile_ceiling(doc):
    settings.save_settings(settings.load_settings())
    allow(doc.parent, profile="musteri")
    code, _, err = run_cli("scan", str(doc), "--profil", "kurum_ici")
    assert code == cli.EXIT_REFUSED and "gevşek" in err


def test_scan_in_guide_and_help(capsys):
    text = kilavuz.guide_text()
    assert "`scan <dosya> [--profil ID] [--ajan AD] [--json]`" in text
    lines = text.split("\n")
    start = lines.index("`scan --json` `summary` nesnesi (değer yok, yalnızca sayılar):")
    i = start + 1
    while not lines[i].startswith("|"):
        i += 1
    rows = []
    while i < len(lines) and lines[i].startswith("|"):
        rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
        i += 1
    assert [(a.strip("`"), t, d) for a, t, d in rows[2:]] == cli.SCAN_FIELDS
    assert run_cli("scan", "--help")[0] == 0
    out = capsys.readouterr().out
    assert "bulunan" in out and "Çıkış kodları:" in out and "ornek_" in out
    assert "scan" in kilavuz.guide_prompt()
