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
    uygulama_klasoru.mkdir(parents=True)  # uygulama kurulu, politika boş
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


# ---------- Uygulama kurulu değil (MCPB paketi) ----------
# MCPB paketi içinden çalışan motor da yalnızca masaüstü uygulamasının ayar klasörünü kullanır. Uygulama hiç
# açılmamışsa klasör yoktur: motor klasörü kendisi kurmaz, boş izinle "izinli klasör yok" demek yerine
# uygulamanın kurulu olmadığını söyler (çıkış 3: dur, kullanıcıya ilet).


def _mcp(*mesajlar):
    girdi = io.StringIO("".join(json.dumps(m) + "\n" for m in mesajlar))
    out, err = io.StringIO(), io.StringIO()
    code = cli.run(["mcp"], out, err, stdin=girdi)
    return code, [json.loads(s) for s in out.getvalue().splitlines()], err.getvalue()


@pytest.mark.parametrize("argv", [("folders",), ("folders", "--json"), ("scan", "belge.txt"), ("read", "belge.txt")])
def test_uygulama_kurulu_degilse_komut_anlasilir_hata_verir(uygulama_klasoru, tmp_path, monkeypatch, argv):
    monkeypatch.delenv("BULUTBELGE_DATA_DIR", raising=False)
    belge = tmp_path / "belge.txt"
    belge.write_text("Sahte Kişi 05001112233\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    code, out, err = _run(*argv)
    assert code == cli.EXIT_REFUSED and out == ""
    assert "app_not_installed" in err and "kurulu değil" in err and "bulutbelge.com/indir" in err
    # Klasör kurulmaz, işlem günlüğü açılmaz.
    assert not uygulama_klasoru.exists()


def test_uygulama_kurulu_degilse_mcp_baslar_ama_arac_reddeder(uygulama_klasoru, tmp_path, monkeypatch):
    monkeypatch.delenv("BULUTBELGE_DATA_DIR", raising=False)
    code, yanitlar, _ = _mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "deneme"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "bulutbelge_folders", "arguments": {}}},
        {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "bulutbelge_scan", "arguments": {"path": str(tmp_path / "x.pdf")}}},
    )
    assert code == 0
    # Tanıtım (initialize, tools/list) uygulama olmadan da çalışır: kayıtlar ve istemciler araçları görebilir.
    assert yanitlar[0]["result"]["serverInfo"]["name"] == "bulutbelge"
    assert {t["name"] for t in yanitlar[1]["result"]["tools"]} >= {"bulutbelge_folders", "bulutbelge_scan"}
    for yanit in yanitlar[2:]:
        sonuc = yanit["result"]
        assert sonuc["isError"] is True
        assert sonuc["structuredContent"]["code"] == "app_not_installed"
        assert sonuc["structuredContent"]["exit_code"] == cli.EXIT_REFUSED
        assert "kurulu değil" in sonuc["content"][0]["text"]
    assert not uygulama_klasoru.exists()


def test_uygulama_kuruluysa_mcp_uygulamanin_politikasini_kullanir(uygulama_klasoru, tmp_path, monkeypatch):
    """MCPB'deki motor ortam değişkeniyle başka klasöre yönlendirilemez; uygulamanın ajan.json'u okunur."""
    saldirgan = tmp_path / "saldirgan"
    _sahte_politika(saldirgan, tmp_path)
    monkeypatch.setenv("BULUTBELGE_DATA_DIR", str(saldirgan))
    belgeler = tmp_path / "belgeler"
    belgeler.mkdir()
    _sahte_politika(uygulama_klasoru, belgeler)
    _, yanitlar, err = _mcp(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "bulutbelge_folders", "arguments": {}}},
    )
    sonuc = yanitlar[0]["result"]
    assert sonuc["isError"] is False
    assert sonuc["structuredContent"] == {"folders": [str(belgeler)], "allow_write": True}
    assert "yok sayıldı" in err
