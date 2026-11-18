"""Ajan kılavuzu: paketteki kopya, `kilavuz` komutu, `agent.guide`, paketli exe'den CLI çağrısı."""

import importlib.util
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from bulutbelge_engine import cli, kilavuz, settings
from bulutbelge_engine.protocol import handle_line

ROOT = Path(__file__).resolve().parents[3]


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], *argv], out, err)
    return code, out.getvalue(), err.getvalue()


def test_guide_copies_are_in_sync_with_source():
    spec = importlib.util.spec_from_file_location("kilavuz_esitle", ROOT / "desktop" / "scripts" / "kilavuz-esitle.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    for path, content in mod.outputs().items():
        assert path.read_text(encoding="utf-8") == content, (
            f"{path.relative_to(ROOT)} eski; `python desktop/scripts/kilavuz-esitle.py` çalıştırın"
        )


def test_guide_prompt_has_the_rules_agents_must_follow():
    prompt = kilavuz.guide_prompt()
    for needle in ("bulutbelge read", "bulutbelge mask", "bulutbelge folders", "3 (izin yok)", "Kaçak tespiti", "OCR"):
        assert needle in prompt, needle
    assert "```" not in prompt and "yonerge-basla" not in prompt


def test_kilavuz_command_prints_guide_without_touching_settings_or_log():
    code, out, _ = run_cli("kilavuz")
    assert code == 0 and out == kilavuz.guide_text()
    code, prompt, _ = run_cli("kilavuz", "--yonerge")
    assert code == 0 and prompt == kilavuz.guide_prompt(kilavuz.command_here())
    assert not (settings.data_dir() / "islem-gunlugu.jsonl").exists()


def test_agent_guide_protocol_method():
    resp = handle_line(json.dumps({"id": 1, "method": "agent.guide", "params": {}}))
    assert resp["result"]["prompt"] == kilavuz.guide_prompt(kilavuz.command_here())
    assert resp["result"]["command"] == kilavuz.command_here()


def test_engine_with_arguments_runs_as_cli(tmp_path):
    """Paketli exe `bulutbelge-engine kilavuz ...` ile CLI olarak çalışır; argümansız protokol sunar."""
    env = dict(os.environ, BULUTBELGE_DATA_DIR=str(tmp_path))
    r = subprocess.run(
        [sys.executable, "-m", "bulutbelge_engine", "kilavuz", "--yonerge"], capture_output=True, text=True, env=env, timeout=60
    )
    # Yönergedeki komut, bu kurulumdaki gerçek komutla yazılır (geliştirmede python -m bulutbelge_engine.cli).
    assert r.returncode == 0 and ("bulutbelge read" in r.stdout or "bulutbelge_engine.cli read" in r.stdout)
    r = subprocess.run(
        [sys.executable, "-m", "bulutbelge_engine", "cli", "folders", "--json"], capture_output=True, text=True, env=env, timeout=60
    )
    assert r.returncode == 0 and json.loads(r.stdout) == {"folders": [], "allow_write": False}


def test_prompt_uses_the_real_command_of_this_installation():
    p = kilavuz.guide_prompt(r'"C:\Users\Ayse Hanim\AppData\Local\BulutBelge\bulutbelge-engine.exe"')
    assert 'bulutbelge-engine.exe" folders' in p and 'bulutbelge-engine.exe" read "<dosya>"' in p
    assert "\nbulutbelge " not in p and "bulutbelge read" not in p
    # Komut adı olmayan geçişler (ör. dosya adı, "BulutBelge" markası) değişmez.
    assert "BulutBelge komutu" in p or "BulutBelge" in p


def test_command_here_in_development_points_to_this_python(monkeypatch):
    monkeypatch.setattr(kilavuz.shutil, "which", lambda _n: None)
    assert kilavuz.command_here().endswith("-m bulutbelge_engine.cli")
    monkeypatch.setattr(kilavuz.shutil, "which", lambda _n: "/usr/local/bin/bulutbelge")
    assert kilavuz.command_here() == "bulutbelge"


def _guide_table(heading: str) -> list[list[str]]:
    """Kılavuzda başlığın altındaki ilk tablonun gövde satırları."""
    lines = kilavuz.guide_text().split("\n")
    i = lines.index(heading)
    while not lines[i].startswith("|"):
        i += 1
    rows = []
    while i < len(lines) and lines[i].startswith("|"):
        rows.append([c.strip() for c in re.split(r"(?<!\\)\|", lines[i].strip().strip("|"))])
        i += 1
    return rows[2:]


def test_exit_code_dict_matches_guide_table():
    rows = _guide_table("### Çıkış kodları")
    assert {int(k): (a, b) for k, a, b in rows} == cli.EXIT_CODES


def test_json_summary_fields_match_guide_schema():
    rows = _guide_table("## JSON çıktı şeması")  # ilk tablo: read alanları
    assert [r[0].strip("`") for r in rows] == [a for a, _, _ in cli.JSON_OUTPUTS["read"]]
    lines = kilavuz.guide_text().split("\n")
    start = lines.index("`summary` nesnesi (read ve mask için aynı):")
    summary = _guide_table(lines[start])
    assert [(a.strip("`"), t.replace("\\|", "|"), d.replace("\\|", "|")) for a, t, d in summary] == cli.SUMMARY_FIELDS


def help_of(capsys, *argv):
    code = run_cli(*argv, "--help")[0]
    return code, capsys.readouterr().out


def test_help_has_examples_exit_codes_and_json_fields(capsys):
    for argv in ([], ["read"], ["mask"], ["folders"], ["kilavuz"]):
        code, out = help_of(capsys, *argv)
        assert code == 0
        assert "Örnekler:" in out and "bulutbelge" in out and "Çıkış kodları:" in out
        for k in cli.EXIT_CODES:
            assert f"\n  {k}  " in out
        assert "ornek_" in out or argv in ([], ["folders"], ["kilavuz"])
    for argv, fields in (("read", ["text", "summary"]), ("mask", ["summary", "kural_takimi"]), ("folders", ["allow_write"])):
        _, out = help_of(capsys, argv)
        assert all(f in out for f in fields) and "--json çıktısı" in out
    _, out = help_of(capsys, "read")
    assert all(f in out for f, _, _ in cli.SUMMARY_FIELDS)


def test_help_does_not_change_exit_codes(capsys):
    assert run_cli("--help")[0] == 0
    assert run_cli("read")[0] == 2  # dosya yok: kullanım hatası
    assert run_cli("yok")[0] == 2
