"""İşlem günlüğü ve ajan komutu. Tüm veriler sahtedir."""

import io
import json
import os
from pathlib import Path

import pytest

from bulutbelge_engine import cli, journal, settings
from bulutbelge_engine.protocol import EngineError, handle_line


def fake_tc(first9: str = "123456789") -> str:
    d = [int(c) for c in first9]
    d10 = ((d[0] + d[2] + d[4] + d[6] + d[8]) * 7 - (d[1] + d[3] + d[5] + d[7])) % 10
    return first9 + str(d10) + str((sum(d) + d10) % 10)


TC = fake_tc()


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    if "error" in resp:
        raise EngineError(resp["error"]["code"], resp["error"]["message"])
    return resp["result"]


def log_lines() -> list[dict]:
    p = settings.data_dir() / journal.LOG_FILE
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


@pytest.fixture
def note(tmp_path) -> Path:
    d = tmp_path / "belgeler"
    d.mkdir()
    p = d / "not.txt"
    p.write_text(f"Başvuran TC: {TC}\nKonu: deneme\n", encoding="utf-8")
    return p


# ---------- Masaüstü komutları günlüğe girer ----------


def test_scan_and_mask_are_logged_without_values(note):
    rules = {"profile_name": "Müşteriye"}
    call("doc.scan", path=str(note), rules=rules)
    res = call("doc.mask", source=str(note), target=str(note.with_name("not_maskeli.txt")), rules=rules)
    assert res["counts"] == {"tc_kimlik": 1}
    recs = log_lines()
    assert [r["op"] for r in recs] == ["okuma", "maskeleme"]
    assert all(r["caller"] == "kullanici" and r["result"] == "basarili" for r in recs)
    assert recs[0]["counts"] == {"tc_kimlik": 1} and recs[0]["profile"] == "Müşteriye"
    assert recs[1]["target"] == res["target"] and len(recs[1]["target_sha256"]) == 64
    assert recs[0]["source_sha256"] == recs[1]["source_sha256"]
    raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert TC not in raw and "deneme" not in raw
    assert call("log.verify")["ok"] is True


def test_text_scan_logged_without_hash(note):
    call("text.scan", text=f"TC {TC}", rules={})
    rec = log_lines()[-1]
    assert rec["op"] == "okuma" and rec["source_sha256"] is None and rec["counts"] == {"tc_kimlik": 1}


def test_failed_operation_logged_with_code_only(tmp_path):
    with pytest.raises(EngineError):
        call("doc.scan", path=str(tmp_path / "yok.pdf"))
    rec = log_lines()[-1]
    assert rec["result"] == "hata" and rec["error"] == "document"


def test_unwritable_log_blocks_operation(note):
    log_path = settings.data_dir() / journal.LOG_FILE
    log_path.mkdir()  # günlük yerine klasör: yazılamaz
    target = note.with_name("not_maskeli.txt")
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(note), target=str(target), rules={})
    assert e.value.code == "log_unwritable"
    assert not target.exists()


def test_append_failure_after_mask_removes_copy(note, monkeypatch):
    target = note.with_name("not_maskeli.txt")
    real_append = journal.AuditLog.append

    def failing(self, op, **kw):
        if kw.get("result") == "basarili":
            raise journal.AuditError("disk dolu")
        return real_append(self, op, **kw)

    monkeypatch.setattr(journal.AuditLog, "append", failing)
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(note), target=str(target), rules={})
    assert e.value.code == "log_unwritable"
    assert not target.exists()


def test_list_filters_and_csv_export(note, tmp_path):
    call("doc.scan", path=str(note), rules={})
    call("text.scan", text="merhaba", rules={})
    assert call("log.list")["total"] == 2
    only = call("log.list", file="not.txt")
    assert only["total"] == 1 and only["items"][0]["source"] == str(note)
    assert call("log.list", caller="ajan")["total"] == 0
    out = call("log.export", target=str(tmp_path / "gunluk.csv"))
    text = Path(out["target"]).read_text(encoding="utf-8-sig")
    assert text.startswith("seq;at;op") and out["count"] == 2
    assert log_lines()[-1]["op"] == "disa_aktarma"


# ---------- Ajan komutu ----------


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], *argv], out, err)
    return code, out.getvalue(), err.getvalue()


def allow(folder: Path, **kw):
    call("agent.save", folders=[str(folder)], **kw)


def test_cli_refuses_without_allowed_folder_and_logs(note):
    code, out, err = run_cli("read", str(note), "--ajan", "deneme")
    assert code == cli.EXIT_REFUSED and out == "" and "izinli" in err
    rec = log_lines()[-1]
    assert rec["caller"] == "ajan" and rec["agent"] == "deneme" and rec["result"] == "reddedildi"


def test_cli_read_returns_masked_text_only(note):
    allow(note.parent)
    code, out, err = run_cli("read", str(note), "--ajan", "deneme")
    assert code == 0, err
    assert TC not in out and "Konu: deneme" in out and "BulutBelge özeti" in out
    assert "T.C. Kimlik" in out or "TC" in out
    rec = log_lines()[-1]
    assert rec["op"] == "okuma" and rec["caller"] == "ajan" and rec["counts"] == {"tc_kimlik": 1}
    assert TC not in (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")


def test_cli_read_json(note):
    allow(note.parent)
    code, out, _ = run_cli("read", str(note), "--json")
    data = json.loads(out)
    assert data["ok"] and TC not in data["text"] and data["summary"]["maskelenen"] == 1


def test_cli_rejects_file_outside_allowed(note, tmp_path):
    other = tmp_path / "baska"
    other.mkdir()
    allow(other)
    code, out, _ = run_cli("read", str(note))
    assert code == cli.EXIT_REFUSED and out == ""


def test_cli_rejects_path_escape(note, tmp_path):
    inner = note.parent / "alt"
    inner.mkdir()
    allow(inner)
    code, _, _ = run_cli("read", str(inner / ".." / note.name))
    assert code == cli.EXIT_REFUSED


def test_cli_mask_needs_write_permission(note):
    allow(note.parent)
    code, _, err = run_cli("mask", str(note))
    assert code == cli.EXIT_REFUSED and "yazma" in err.lower()
    assert log_lines()[-1]["error"] == "write_not_allowed"


def test_cli_mask_writes_new_file_never_overwrites(note):
    allow(note.parent, allow_write=True)
    existing = note.with_name("cikti.txt")
    existing.write_text("dokunulmamalı", encoding="utf-8")
    code, out, err = run_cli("mask", str(note), "--hedef", str(existing))
    assert code == 0, err
    assert existing.read_text(encoding="utf-8") == "dokunulmamalı"
    written = [p for p in note.parent.iterdir() if p.name.startswith("cikti_")]
    assert len(written) == 1 and TC not in written[0].read_text(encoding="utf-8")
    assert "Maskeli kopya:" in out and TC not in out
    assert note.read_text(encoding="utf-8").count(TC) == 1  # kaynak değişmedi
    rec = log_lines()[-1]
    assert rec["op"] == "maskeleme" and rec["target"] == str(written[0])


def test_cli_mask_target_outside_folder_refused(note, tmp_path):
    allow(note.parent, allow_write=True)
    code, _, _ = run_cli("mask", str(note), "--hedef", str(tmp_path / "disari.txt"))
    assert code == cli.EXIT_REFUSED and not (tmp_path / "disari.txt").exists()


def test_cli_refuses_when_vault_exists_unless_allowed(note):
    allow(note.parent)
    call("vault.create", password="sahte-parola-123")
    settings.VAULT.lock()
    code, _, err = run_cli("read", str(note))
    assert code == cli.EXIT_REFUSED and "kasa" in err.lower()
    allow(note.parent, allow_without_terms=True)
    code, _, _ = run_cli("read", str(note))
    assert code == 0


def test_cli_stops_when_log_unwritable(note):
    allow(note.parent)
    (settings.data_dir() / journal.LOG_FILE).mkdir()
    code, out, err = run_cli("read", str(note))
    assert code == cli.EXIT_LOG and out == "" and "günlüğü" in err


def test_agent_settings_validation(tmp_path):
    with pytest.raises(EngineError):
        call("agent.save", folders=["göreli/klasor"])
    with pytest.raises(EngineError):
        call("agent.save", folders=[str(tmp_path / "yok")])
    with pytest.raises(EngineError):
        call("agent.save", folders=[str(settings.data_dir())])
    with pytest.raises(EngineError):
        call("agent.save", folders=[Path(tmp_path).anchor])
    assert call("agent.get") == {"folders": [], "allow_write": False, "allow_without_terms": False, "profile": None}


def test_agent_file_with_bom_is_read_and_broken_file_grants_nothing(tmp_path):
    """Windows PowerShell 5.1 / Not Defteri BOM'lu UTF-8 yazar; izinler okunmalı. Bozuk dosya izin vermez."""
    klasor = tmp_path / "izinli"
    klasor.mkdir()
    yol = settings.data_dir() / settings.AGENT_FILE
    yol.write_bytes(b"\xef\xbb\xbf" + json.dumps({"folders": [str(klasor)], "allow_write": True}).encode("utf-8"))
    ajan = call("agent.get")
    assert ajan["folders"] == [str(klasor)] and ajan["allow_write"] is True
    yol.write_bytes(b"\xff\xfe{bozuk")
    assert call("agent.get")["folders"] == []


def test_cli_uses_env_data_dir_when_no_flag(note):
    allow(note.parent)
    out, err = io.StringIO(), io.StringIO()
    assert cli.run(["read", str(note)], out, err) == 0, err.getvalue()
    assert log_lines()[-1]["caller"] == "ajan"


# ---------- Önizleme ve maske kaldırma ----------


def test_preview_logged_once_per_file(note):
    call("doc.text", path=str(note))
    call("doc.text", path=str(note))
    recs = [r for r in log_lines() if r["op"] == "onizleme"]
    assert len(recs) == 1 and recs[0]["source"] == str(note) and len(recs[0]["source_sha256"]) == 64
    note.write_text("değişti\n", encoding="utf-8")  # dosya değişince yeniden kaydedilir
    call("doc.text", path=str(note))
    assert len([r for r in log_lines() if r["op"] == "onizleme"]) == 2


def test_pdf_pages_logged_once(tmp_path):
    import pymupdf

    p = tmp_path / "iki-sayfa.pdf"
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "Sayfa bir")
    doc.new_page().insert_text((72, 72), "Sayfa iki")
    doc.save(p)
    doc.close()
    call("doc.page", path=str(p), page=1)
    call("doc.page", path=str(p), page=2)
    assert len([r for r in log_lines() if r["op"] == "onizleme"]) == 1


def test_preview_blocked_when_log_unwritable(note):
    (settings.data_dir() / journal.LOG_FILE).mkdir()
    with pytest.raises(EngineError) as e:
        call("doc.text", path=str(note))
    assert e.value.code == "log_unwritable"


def test_unmask_logged_without_label_or_value(note):
    call("vault.create", password="sahte-parola-123")
    rules = {"types": {"tc_kimlik": {"enabled": True, "method": "takma_ad"}}}
    found = call("text.scan", text=f"TC {TC}", rules=rules)["findings"]
    label = found[0]["replacement"]
    res = call("vault.pseudonym_lookup", label=label)
    assert res["value"] == TC
    rec = log_lines()[-1]
    assert rec["op"] == "maske_kaldirma" and rec["result"] == "basarili" and rec["counts"] == {"tc_kimlik": 1}
    raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert TC not in raw and label not in raw
    with pytest.raises(EngineError):
        call("vault.pseudonym_lookup", label="Kişi-999")
    assert log_lines()[-1]["result"] == "hata"


def test_restore_text_logged_without_text_or_values(note):
    with pytest.raises(EngineError) as e:
        call("vault.pseudonym_restore_text", text="Kişi-1 aradı")
    assert e.value.code == "vault_locked"
    call("vault.create", password="sahte-parola-123")
    rules = {"types": {"tc_kimlik": {"enabled": True, "method": "takma_ad"}}}
    label = call("text.scan", text=f"TC {TC}", rules=rules)["findings"][0]["replacement"]
    res = call("vault.pseudonym_restore_text", text=f"{label} ve Kişi-999 geldi")
    assert res == {"text": f"{TC} ve Kişi-999 geldi", "count": 1}
    rec = log_lines()[-1]
    assert rec["op"] == "maske_kaldirma" and rec["result"] == "basarili" and rec["counts"] == {"takma_ad": 1}
    raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert TC not in raw and label not in raw and "geldi" not in raw
    with pytest.raises(EngineError) as e:
        call("vault.pseudonym_restore_text", text="  ")
    assert e.value.code == "invalid_params"


# ---------- Excel satır/sütun seçimi ----------


def test_doc_mask_manual_cells(tmp_path):
    import openpyxl

    src = tmp_path / "tablo.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Ad", "Kod"])
    wb.active.append(["Sahte Kişi", "KOD-90001"])
    wb.save(src)
    res = call("doc.mask", source=str(src), target=str(tmp_path / "tablo_maskeli.xlsx"), rules={},
               manual_cells=[{"sheet": "Sheet", "axis": "col", "index": 1}])
    assert res["counts"].get("elle") == 2
    assert log_lines()[-1]["counts"].get("elle") == 2
    with pytest.raises(EngineError):
        call("doc.mask", source=str(src), target=str(tmp_path / "x.xlsx"), rules={},
             manual_cells=[{"sheet": "Sheet", "axis": "col", "index": -1}])


def test_manual_cells_rejected_for_non_excel(note):
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(note), target=str(note.with_name("x.txt")), rules={},
             manual_cells=[{"sheet": "S", "axis": "row", "index": 1}])
    assert e.value.code == "invalid_params"


def test_manual_cells_method_and_vault(tmp_path):
    import openpyxl

    src = tmp_path / "tablo.xlsx"
    wb = openpyxl.Workbook()
    wb.active.append(["Kod"])
    wb.active.append(["KOD-90001"])
    wb.save(src)
    cells = [{"sheet": "Sheet", "axis": "col", "index": 0, "method": "takma_ad"}]
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(src), target=str(tmp_path / "a.xlsx"), rules={}, manual_cells=cells)
    assert e.value.code == "vault_locked"
    call("vault.create", password="sahte-parola-123")
    res = call("doc.mask", source=str(src), target=str(tmp_path / "b.xlsx"), rules={}, manual_cells=cells)
    assert res["counts"]["elle"] == 2
    assert call("vault.pseudonyms")["counts"].get("elle") == 2  # eşleme kasaya yazıldı
    with pytest.raises(EngineError):
        call("doc.mask", source=str(src), target=str(tmp_path / "c.xlsx"), rules={},
             manual_cells=[{"sheet": "Sheet", "axis": "col", "index": 0, "method": "bulanik"}])


def test_cli_mask_adds_entry_to_recent_list_with_agent_label(note):
    allow(note.parent, allow_write=True)
    assert settings.history_list() == []
    code, out, _ = run_cli("mask", str(note), "--ajan", "claude-code", "--json")
    assert code == 0
    target = json.loads(out)["summary"]["hedef"]
    items = settings.history_list()
    assert len(items) == 1
    item = items[0]
    assert item["target"] == target and item["path"] == str(note)
    assert item["agent"] == "claude-code"
    assert item["count"] >= 1 and item["byType"][0]["count"] >= 1
    # Orijinal değer son yapılanlara girmez.
    assert TC not in json.dumps(items, ensure_ascii=False)


def test_cli_read_and_refused_calls_do_not_touch_recent_list(note):
    code, _, _ = run_cli("read", str(note))  # izin yok: reddedilir
    assert code != 0
    allow(note.parent)
    run_cli("read", str(note))
    assert settings.history_list() == []


def test_user_history_entries_have_no_agent_label():
    settings.history_add({"entry": {"path": "/a/x.pdf", "target": "/a/x_maskeli.pdf", "count": 2}})
    assert "agent" not in settings.history_list()[0]


def test_mask_purpose_goes_to_log_and_report(note):
    target = note.with_name("not_maskeli.txt")
    res = call(
        "doc.mask",
        source=str(note),
        target=str(target),
        rules={"profile_name": "Müşteriye"},
        purpose="  Denetçiye paylaşım  ",
        report=True,
    )
    rec = log_lines()[-1]
    assert rec["op"] == "maskeleme" and rec["purpose"] == "Denetçiye paylaşım"
    text = Path(res["report"]).read_text(encoding="utf-8")
    assert "Denetçiye paylaşım" in text and rec["target_sha256"] in text and rec["source_sha256"] in text
    assert "tc_kimlik: 1 adet" in text and TC not in text
    assert call("log.verify")["ok"] is True


def test_mask_without_purpose_or_report(note):
    res = call("doc.mask", source=str(note), target=str(note.with_name("m.txt")), rules={})
    assert "report" not in res and log_lines()[-1]["purpose"] is None
    assert not list(note.parent.glob("*.gizleme-raporu.txt"))


def test_report_has_cleanup_section_for_word(tmp_path):
    docx = pytest.importorskip("docx")
    d = docx.Document()
    d.add_paragraph(f"TC: {TC}")
    d.core_properties.author = "Sahte Yazar"
    src = tmp_path / "a.docx"
    d.save(src)
    res = call("doc.mask", source=str(src), target=str(tmp_path / "m.docx"), rules={}, report=True)
    text = Path(res["report"]).read_text(encoding="utf-8")
    assert "Temizlenen gizli bilgiler" in text and "meta veri alanları:" in text and "yazar" in text.split("meta veri alanları:")[1]
    assert "Sahte Yazar" not in text and TC not in text


def test_purposes_list_and_purpose_id_in_log_and_report(note):
    lst = call("purposes.list")
    assert {"id": "yapay_zeka", "name": "Yapay zekâya gönderme", "profile": "musteri"} in lst
    target = note.with_name("not_amac.txt")
    res = call("doc.mask", source=str(note), target=str(target), rules={}, purpose_id="yapay_zeka", purpose="Sahte proje", report=True)
    assert log_lines()[-1]["purpose"] == "Yapay zekâya gönderme — Sahte proje"
    assert "Yapay zekâya gönderme" in Path(res["report"]).read_text(encoding="utf-8")
    assert call("log.verify")["ok"] is True


def test_unknown_purpose_id_is_rejected(note):
    import pytest as _p
    with _p.raises(Exception):
        call("doc.mask", source=str(note), target=str(note.with_name("x.txt")), rules={}, purpose_id="yok")


def _pdf_with_tc(path: Path) -> Path:
    import pymupdf

    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), f"TC {TC}")
    doc.save(path)
    doc.close()
    return path


def test_pdf_password_copy_opens_only_with_password_and_is_not_logged(tmp_path):
    import pymupdf

    src = _pdf_with_tc(tmp_path / "kaynak.pdf")
    dst = tmp_path / "kopya.pdf"
    res = call("doc.mask", source=str(src), target=str(dst), password="sahte-parola-123")
    assert res["target"] == str(dst)
    doc = pymupdf.open(dst)
    try:
        assert doc.needs_pass and doc.authenticate("sahte-parola-123")
        assert TC not in doc[0].get_text()
    finally:
        doc.close()
    # Parola ve özgün değer işlem günlüğüne girmez.
    p = settings.data_dir() / journal.LOG_FILE
    raw = p.read_text(encoding="utf-8") if p.exists() else ""
    assert "sahte-parola-123" not in raw and TC not in raw


def test_pdf_password_too_short_rejected_and_non_pdf_refused(tmp_path, note):
    src = _pdf_with_tc(tmp_path / "kaynak.pdf")
    with pytest.raises(EngineError):
        call("doc.mask", source=str(src), target=str(tmp_path / "k.pdf"), password="123")
    assert not (tmp_path / "k.pdf").exists()
    with pytest.raises(EngineError) as e:
        call("doc.mask", source=str(note), target=str(tmp_path / "n.txt"), password="sahte-parola-123")
    assert e.value.code


@pytest.mark.parametrize("ad", ['=WEBSERVICE("http://ornek.invalid")', "-ajan", "ajan adı", "a;b", "@x", "ajan\n"])
def test_cli_rejects_unsafe_agent_name(note, ad):
    """Güvenlik taraması F15: --ajan yalnızca güvenli karakter kümesinden olur, günlüğe girmez."""
    allow(note.parent)
    before = len(log_lines()) if (settings.data_dir() / journal.LOG_FILE).exists() else 0
    code, out, err = run_cli("read", str(note), f"--ajan={ad}")
    assert code == cli.EXIT_USAGE and out == "" and "--ajan" in err
    after = len(log_lines()) if (settings.data_dir() / journal.LOG_FILE).exists() else 0
    assert after == before


@pytest.mark.parametrize("ad", ["claude-code", "deneme", "Kod.Asistani_2", "ornek-ajan"])
def test_cli_accepts_safe_agent_name(note, ad):
    allow(note.parent)
    code, _, err = run_cli("read", str(note), "--ajan", ad)
    assert code == 0, err
    assert log_lines()[-1]["agent"] == ad
