"""Ajan komutu politika konumunu seçemez (güvenlik taraması F8). Tüm veriler sahtedir.

Geliştirme modu dışında --veri-klasoru reddedilir, BULUTBELGE_DATA_DIR yok sayılır ve masaüstü
uygulamasının klasörü kullanılır. Karar: docs/kararlar/2026-11-21-ajan-cli-veri-klasoru.md.
"""

import io
import json
from pathlib import Path

import pytest

from bulutbelge_engine import cli


@pytest.fixture
def uygulama_klasoru(tmp_path, monkeypatch):
    """Ajan yolu: geliştirme modu kapalı, varsayılan klasör geçici dizine yönlenir."""
    monkeypatch.delenv("BULUTBELGE_GELISTIRME", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "xdg"))
    monkeypatch.setenv("HOME", str(tmp_path / "ev"))
    return cli.default_data_dir()


def _run(*argv):
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(list(argv), out, err)
    return code, out.getvalue(), err.getvalue()


def _sahte_politika(dizin: Path, belge_klasoru: Path) -> None:
    dizin.mkdir(parents=True, exist_ok=True)
    (dizin / "ajan.json").write_text(
        json.dumps({"folders": [str(belge_klasoru)], "allow_write": True, "allow_without_terms": True}),
        encoding="utf-8",
    )


def test_veri_klasoru_bayragi_ajan_yolunda_reddedilir(uygulama_klasoru, tmp_path):
    saldirgan = tmp_path / "saldirgan"
    _sahte_politika(saldirgan, tmp_path)
    code, out, err = _run("--veri-klasoru", str(saldirgan), "folders", "--json")
    assert code == cli.EXIT_USAGE and out == ""
    assert "geliştirme modunda" in err


def test_ortam_degiskeni_ajan_yolunda_yok_sayilir(uygulama_klasoru, tmp_path, monkeypatch):
    saldirgan = tmp_path / "saldirgan"
    _sahte_politika(saldirgan, tmp_path)
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(saldirgan))
    code, out, err = _run("folders", "--json")
    # Saldırganın ajan.json'u değil, uygulamanın (boş) politikası okunur.
    assert code == 0 and json.loads(out) == {"folders": [], "allow_write": False}
    assert "yok sayıldı" in err


def test_ajan_yolu_uygulama_klasorunun_politikasini_kullanir(uygulama_klasoru, tmp_path, monkeypatch):
    monkeypatch.delenv("BULUTBELGE_DATA_DIR", raising=False)
    belgeler = tmp_path / "belgeler"
    belgeler.mkdir()
    _sahte_politika(uygulama_klasoru, belgeler)
    code, out, err = _run("folders", "--json")
    assert code == 0 and err == ""
    assert json.loads(out) == {"folders": [str(belgeler)], "allow_write": True}


def test_gelistirme_modunda_veri_klasoru_kabul_edilir(tmp_path, monkeypatch):
    monkeypatch.setenv("BULUTBELGE_GELISTIRME", "1")
    dizin = tmp_path / "gelistirme"
    _sahte_politika(dizin, tmp_path)
    code, out, _ = _run("--veri-klasoru", str(dizin), "folders", "--json")
    assert code == 0 and json.loads(out)["folders"] == [str(tmp_path)]


def test_gelistirme_bayragi_yalnizca_bir_degeriyle_acilir(uygulama_klasoru, tmp_path, monkeypatch):
    for deger in ("0", "true", "evet", ""):
        monkeypatch.setenv("BULUTBELGE_GELISTIRME", deger)
        code, _, _ = _run("--veri-klasoru", str(tmp_path), "folders")
        assert code == cli.EXIT_USAGE, deger


def test_kilavuz_ayar_klasoru_gerektirmez(uygulama_klasoru):
    code, out, _ = _run("kilavuz", "--yonerge")
    assert code == 0 and out
