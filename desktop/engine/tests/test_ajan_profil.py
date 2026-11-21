"""K1: ajan için atanan kural takımı üst sınırdır; --profil daha gevşek bir takım seçemez. Veriler sahtedir."""

import io
import json
import os
from pathlib import Path

import pytest

from bulutbelge_engine import cli, journal, settings
from bulutbelge_engine.protocol import handle_line

AD = "Ayşe Yılmaz"  # sahte kişi adı (ad sözlüğünde geçen yaygın ad)
TELEFON = "0532 000 12 34"


def call(method, **params):
    resp = handle_line(json.dumps({"id": 1, "method": method, "params": params}))
    assert "error" not in resp, resp
    return resp["result"]


def run_cli(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["--veri-klasoru", os.environ["BULUTBELGE_DATA_DIR"], *argv], out, err)
    return code, out.getvalue(), err.getvalue()


def log_lines() -> list[dict]:
    p = settings.data_dir() / journal.LOG_FILE
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()] if p.exists() else []


@pytest.fixture
def note(tmp_path) -> Path:
    d = tmp_path / "belgeler"
    d.mkdir()
    p = d / "dilekce.txt"
    p.write_text(f"Başvuran: {AD}\nTelefon: {TELEFON}\n", encoding="utf-8")
    return p


def assign(folder: Path, profile: str | None) -> None:
    settings.load_settings()  # hazır takımlar (musteri, kurum_ici, ...) eklensin
    call("settings.save", **settings.load_settings())
    call("agent.save", folders=[str(folder)], profile=profile)


def test_looser_profile_is_refused_and_logged_without_values(note):
    assign(note.parent, "musteri")
    code, out, err = run_cli("read", str(note), "--profil", "kurum_ici", "--ajan", "deneme")
    assert code == cli.EXIT_REFUSED and out == ""
    assert "gevşek" in err and "Kişi adı" in err and "Telefon" in err
    assert AD not in err and TELEFON not in err
    rec = log_lines()[-1]
    assert rec["result"] == "reddedildi" and rec["error"] == "profile_not_allowed"
    assert rec["caller"] == "ajan" and rec["agent"] == "deneme" and rec["op"] == "okuma"
    raw = (settings.data_dir() / journal.LOG_FILE).read_text(encoding="utf-8")
    assert AD not in raw and TELEFON not in raw


def test_looser_profile_refused_for_mask_too(note):
    assign(note.parent, "musteri")
    call("agent.save", folders=[str(note.parent)], profile="musteri", allow_write=True)
    code, _, _ = run_cli("mask", str(note), "--profil", "kurum_ici")
    assert code == cli.EXIT_REFUSED
    assert not any(p.name.startswith("dilekce_") for p in note.parent.iterdir())


def test_same_profile_is_accepted(note):
    assign(note.parent, "musteri")
    code, out, err = run_cli("read", str(note), "--profil", "musteri")
    assert code == 0, err
    assert AD not in out and TELEFON not in out


def test_stricter_profile_is_accepted(note):
    # Kurum içine (adlar açık) atanmışken Müşteriye (adlar da gizli) daha sıkıdır.
    assign(note.parent, "kurum_ici")
    code, out, err = run_cli("read", str(note), "--profil", "musteri", "--json")
    assert code == 0, err
    data = json.loads(out)
    assert data["summary"]["kural_takimi"] == "Müşteriye" and AD not in data["text"]


def test_without_profil_the_assigned_profile_is_used(note):
    assign(note.parent, "musteri")
    code, out, err = run_cli("read", str(note), "--json")
    assert code == 0, err
    assert json.loads(out)["summary"]["kural_takimi"] == "Müşteriye"


def test_active_profile_is_the_ceiling_when_none_assigned(note):
    assign(note.parent, None)
    s = settings.load_settings()
    call("settings.save", profiles=s["profiles"], active="musteri")
    code, _, _ = run_cli("read", str(note), "--profil", "kurum_ici")
    assert code == cli.EXIT_REFUSED
    code, _, err = run_cli("read", str(note), "--profil", "musteri")
    assert code == 0, err


def test_unknown_profile_is_usage_error(note):
    assign(note.parent, "musteri")
    code, _, err = run_cli("read", str(note), "--profil", "yok_boyle")
    assert code == cli.EXIT_USAGE and "bulunamadı" in err


def test_method_may_differ_but_wider_whitelist_is_looser():
    base = settings.load_settings()["profiles"][0]
    other_method = json.loads(json.dumps(base))
    other_method["id"] = "baska"
    other_method["types"]["kisi_adi"]["method"] = "bas_harf"
    assert settings.looser_than(other_method, base) == []
    wider = json.loads(json.dumps(base))
    wider["whitelist"] = ["Örnek Bilişim"]
    reasons = settings.looser_than(wider, base)
    assert reasons == ["beyaz liste daha geniş"]
    assert "Örnek" not in " ".join(reasons)


def test_missing_custom_pattern_is_looser():
    base = settings.load_settings()["profiles"][0]
    ceiling = json.loads(json.dumps(base))
    ceiling["patterns"] = [{"name": "Dosya no", "pattern": r"DSY-\d{4}"}]
    assert settings.looser_than(base, ceiling) == ["1 özel kalıp yok"]
    assert settings.looser_than(ceiling, base) == []
