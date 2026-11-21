"""Yerel MCP sunucusu (`bulutbelge mcp`): alt süreçte stdio üzerinden initialize → tools/list → tools/call.

Araçlar CLI ile aynı izin denetimini ve işlem günlüğünü kullanır; dönen içerikte orijinal değer yoktur.
Tüm veriler sahtedir.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from bulutbelge_engine import ajan, journal, mcp, settings
from bulutbelge_engine.protocol import handle_line

TC = "12345678950"  # doğrulamadan geçen sahte numara
AD = "Ayşe Yılmaz"
TELEFON = "0532 000 12 34"
ENGINE = Path(__file__).resolve().parents[1]


def allow(folder: Path, **kw) -> None:
    resp = handle_line(json.dumps({"id": 1, "method": "agent.save", "params": {"folders": [str(folder)], **kw}}))
    assert "error" not in resp


def log_lines() -> list[dict]:
    p = settings.data_dir() / journal.LOG_FILE
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


def session(messages: list[dict], env_extra: dict | None = None) -> list[dict]:
    """`mcp`'yi alt süreçte başlatır, iletileri satır satır yollar, yanıtları döndürür."""
    env = dict(os.environ, BULUTBELGE_GELISTIRME="1", PYTHONIOENCODING="utf-8", **(env_extra or {}))
    proc = subprocess.run(
        [sys.executable, "-m", "bulutbelge_engine.cli", "--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], "mcp"],
        input="".join(json.dumps(m, ensure_ascii=False) + "\n" for m in messages),
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        cwd=ENGINE,
        timeout=180,
    )
    assert proc.returncode == 0, proc.stderr
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


INIT = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "Claude Code", "version": "1.0"}},
}
INITIALIZED = {"jsonrpc": "2.0", "method": "notifications/initialized"}


def call(i: int, name: str, **arguments) -> dict:
    return {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": name, "arguments": arguments}}


@pytest.fixture
def doc(tmp_path) -> Path:
    d = tmp_path / "belgeler"
    d.mkdir()
    p = d / "dilekce.txt"
    p.write_text(f"Başvuran: {AD}\nTC: {TC}\nTelefon: {TELEFON}\nKonu: deneme\n", encoding="utf-8")
    return p


def test_initialize_list_and_call_flow_without_original_values(doc):
    allow(doc.parent, allow_write=True)
    out = session([
        INIT,
        INITIALIZED,
        {"jsonrpc": "2.0", "id": 2, "method": "ping"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        call(4, "bulutbelge_folders"),
        call(5, "bulutbelge_scan", path=str(doc)),
        call(6, "bulutbelge_read", path=str(doc)),
        call(7, "bulutbelge_mask", path=str(doc)),
    ])
    by_id = {m["id"]: m for m in out}
    assert sorted(by_id) == [1, 2, 3, 4, 5, 6, 7]  # bildirime yanıt yok
    init = by_id[1]["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "bulutbelge"
    assert init["capabilities"] == {"tools": {"listChanged": False}}
    assert by_id[2]["result"] == {}
    names = [t["name"] for t in by_id[3]["result"]["tools"]]
    assert names == ["bulutbelge_folders", "bulutbelge_scan", "bulutbelge_read", "bulutbelge_mask"]
    assert all(t["inputSchema"]["type"] == "object" for t in by_id[3]["result"]["tools"])

    folders = by_id[4]["result"]
    assert folders["isError"] is False and folders["structuredContent"]["allow_write"] is True

    scan = by_id[5]["result"]
    assert scan["isError"] is False
    s = scan["structuredContent"]["summary"]
    assert s["islem"] == "tarama" and s["turler"]["TC kimlik no"] == 1 and s["bulunan"] >= 3

    read = by_id[6]["result"]
    assert read["isError"] is False and "Konu: deneme" in read["content"][0]["text"]
    mask = by_id[7]["result"]
    assert mask["isError"] is False
    target = Path(mask["structuredContent"]["summary"]["hedef"])
    assert target.is_file() and target.parent == doc.parent and TC not in target.read_text(encoding="utf-8")

    raw = json.dumps(out, ensure_ascii=False)
    for value in (TC, AD, TELEFON):
        assert value not in raw, value
    assert doc.read_text(encoding="utf-8").count(TC) == 1  # kaynak değişmedi

    recs = log_lines()
    assert [r["op"] for r in recs[-3:]] == ["okuma", "okuma", "maskeleme"]
    assert all(r["caller"] == "ajan" and r["agent"] == "Claude-Code" for r in recs[-3:])
    log_raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert TC not in log_raw and AD not in log_raw


def test_disallowed_folder_is_refused_and_logged(doc, tmp_path):
    other = tmp_path / "baska"
    other.mkdir()
    allow(other)
    out = session([INIT, INITIALIZED, call(2, "bulutbelge_read", path=str(doc)), call(3, "bulutbelge_mask", path=str(doc))])
    for res in (out[1]["result"], out[2]["result"]):
        assert res["isError"] is True
        assert res["structuredContent"]["code"] == "not_allowed" and res["structuredContent"]["exit_code"] == 3
        assert "izinli" in res["content"][0]["text"]
    assert TC not in json.dumps(out, ensure_ascii=False)
    assert [r["result"] for r in log_lines()[-2:]] == ["reddedildi", "reddedildi"]


def test_mask_needs_write_permission_and_profile_ceiling_applies(doc):
    settings.save_settings(settings.load_settings())
    allow(doc.parent, profile="musteri")
    out = session([
        INIT,
        call(2, "bulutbelge_mask", path=str(doc)),
        call(3, "bulutbelge_read", path=str(doc), profile="kurum_ici"),
    ])
    assert out[1]["result"]["structuredContent"]["code"] == "write_not_allowed"
    assert out[2]["result"]["structuredContent"]["code"] == "profile_not_allowed"
    assert AD not in json.dumps(out, ensure_ascii=False)


def test_agent_name_from_env_and_protocol_errors(doc):
    allow(doc.parent)
    out = session(
        [
            {"jsonrpc": "2.0", "id": 9, "method": "bilinmeyen/yontem"},
            INIT,
            call(2, "yok_boyle_arac"),
            call(3, "bulutbelge_scan"),
            call(4, "bulutbelge_scan", path=str(doc)),
        ],
        env_extra={"BULUTBELGE_AJAN": "kod asistanı!"},
    )
    by_id = {m["id"]: m for m in out}
    assert by_id[9]["error"]["code"] == -32601
    assert by_id[2]["error"]["code"] == -32602
    assert by_id[3]["result"]["isError"] is True and by_id[3]["result"]["structuredContent"]["exit_code"] == 2
    assert log_lines()[-1]["agent"] == "kod-asistan"


def test_parse_error_and_clean_agent_name():
    server = mcp.Server()
    assert server.handle("{bozuk")["error"]["code"] == -32700
    assert server.handle(json.dumps({"jsonrpc": "2.0", "method": "notifications/cancelled", "params": {}})) is None
    assert ajan.clean_agent_name("Claude Code") == "Claude-Code"
    assert ajan.clean_agent_name("../../etc") == "etc"
    assert ajan.clean_agent_name("ş") == "ajan" and ajan.clean_agent_name(None, "mcp") == "mcp"
    assert all(ajan.valid_agent_name(ajan.clean_agent_name(x)) for x in ("a b", "-x", "=1+2", "x" * 200))


def test_mcp_opens_no_network_port():
    """Sunucu yalnızca stdio kullanır: modülde soket ya da ağ kütüphanesi yok."""
    src = (ENGINE / "bulutbelge_engine" / "mcp.py").read_text(encoding="utf-8")
    for banned in ("import socket", "http.server", "asyncio.start_server", "urllib", "requests"):
        assert banned not in src, banned


def test_mcp_documented_in_guide_skill_and_help(capsys):
    import io

    from bulutbelge_engine import cli, kilavuz

    text = kilavuz.guide_text()
    for needle in ("## MCP sunucusu (yerel, yalnızca stdio)", "claude mcp add bulutbelge -- bulutbelge mcp", '"mcpServers"'):
        assert needle in text, needle
    assert all(t["name"] in text and t["name"] in kilavuz.skill_text() for t in mcp.TOOLS)
    out, err = io.StringIO(), io.StringIO()
    assert cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], "mcp", "--help"], out, err) == 0
    assert "stdio" in capsys.readouterr().out
