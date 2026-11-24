"""MCPB paketi ve server.json (resmî MCP kaydı). Motorun yerine kaynak koddan çalışan sahte bir giriş dosyası
kullanılır; paketin açılınca çalıştığı, izinlerin korunduğu ve kayıt kurallarının denetlendiği doğrulanır."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import zipfile
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[3]
BETIKLER = KOK / "desktop" / "scripts"


def _yukle(ad: str):
    spec = importlib.util.spec_from_file_location(ad, BETIKLER / f"{ad}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[ad] = mod
    spec.loader.exec_module(mod)
    return mod


mcpb = _yukle("mcpb_paketle")
sj = _yukle("mcp_server_json")

posix = pytest.mark.skipif(os.name == "nt", reason="sahte motor POSIX kabuk betiği")


def _sahte_motor(klasor: Path) -> Path:
    """Gerçek motor gibi `mcp` alt komutunu çalıştıran kabuk betiği (kaynak koddan)."""
    klasor.mkdir(parents=True)
    (klasor / "_internal").mkdir()
    (klasor / "_internal" / "veri.txt").write_text("sahte\n", encoding="utf-8")
    motor = klasor / "bulutbelge-engine"
    yollar = os.pathsep.join([str(KOK / "desktop" / "engine"), str(KOK / "core")])
    motor.write_text(f'#!/bin/sh\nPYTHONPATH="{yollar}" exec "{sys.executable}" -m bulutbelge_engine "$@"\n', encoding="utf-8")
    motor.chmod(0o755)
    return klasor


@posix
def test_mcpb_paketi_uretilir_acilir_ve_mcp_olarak_yanit_verir(tmp_path):
    from bulutbelge_engine import __version__
    from bulutbelge_engine.mcp import TOOLS

    motor = _sahte_motor(tmp_path / "engine")
    paket = mcpb.paketle(motor, "macos-arm64", tmp_path / "cikti", surum=__version__, epoch=1_700_000_000)
    assert paket.name == f"bulutbelge-mcp-{__version__}-macos-arm64.mcpb" and "mcp" in paket.name

    with zipfile.ZipFile(paket) as z:
        adlar = z.namelist()
        mani = json.loads(z.read("manifest.json"))
        giris = z.getinfo("server/bulutbelge-engine")
    assert adlar[0] == "manifest.json" and "server/_internal/veri.txt" in adlar and "icon.png" in adlar
    assert (giris.external_attr >> 16) & 0o777 == 0o755
    assert mani["manifest_version"] == "0.3" and mani["version"] == __version__
    assert mani["server"] == {
        "type": "binary",
        "entry_point": "server/bulutbelge-engine",
        "mcp_config": {"command": "${__dirname}/server/bulutbelge-engine", "args": ["mcp"], "env": {}},
    }
    assert [t["name"] for t in mani["tools"]] == [t["name"] for t in TOOLS]
    assert mani["compatibility"] == {"platforms": ["darwin"]}
    assert "kurulu olmalı" in mani["long_description"]

    # Açılan paketteki motor da sunucu gibi yanıt verir.
    acik = tmp_path / "acik"
    mcpb.ac(paket, acik)
    tanitim = mcpb.mcp_tanit(acik / "server" / "bulutbelge-engine")
    assert tanitim["surum"] == __version__ and len(tanitim["araclar"]) == len(TOOLS)


@posix
def test_mcpb_belirlenimli(tmp_path):
    motor = _sahte_motor(tmp_path / "engine")
    a = mcpb.paketle(motor, "linux-x64", tmp_path / "a", epoch=1_700_000_000)
    b = mcpb.paketle(motor, "linux-x64", tmp_path / "b", epoch=1_700_000_000)
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()


@posix
def test_mcpb_surum_uyusmazsa_durur(tmp_path):
    motor = _sahte_motor(tmp_path / "engine")
    with pytest.raises(mcpb.PaketHatasi, match="Sürüm uyuşmuyor"):
        mcpb.paketle(motor, "macos-arm64", tmp_path / "cikti", surum="9.9.9")


@posix
def test_mcpb_sembolik_bag_reddedilir(tmp_path):
    motor = _sahte_motor(tmp_path / "engine")
    (motor / "_internal" / "bag").symlink_to(motor / "_internal" / "veri.txt")
    with pytest.raises(mcpb.PaketHatasi, match="sembolik bağ"):
        mcpb.paketle(motor, "macos-arm64", tmp_path / "cikti")


def test_windows_giris_dosyasi_exe():
    mani = mcpb.manifest("1.2.3", "windows-x64", [{"name": "x", "description": "y"}])
    assert mani["server"]["entry_point"] == "server/bulutbelge-engine.exe"
    assert mani["server"]["mcp_config"]["command"] == "${__dirname}/server/bulutbelge-engine.exe"
    assert mani["compatibility"]["platforms"] == ["win32"]


# ---------- server.json ----------


def _sablon() -> dict:
    return json.loads((KOK / "server.json").read_text(encoding="utf-8"))


def _paketler(klasor: Path, surum: str = "1.2.3") -> dict[str, str]:
    klasor.mkdir(parents=True, exist_ok=True)
    sumlar = {}
    for p in sj.PLATFORMLAR:
        ad = f"bulutbelge-mcp-{surum}-{p}.mcpb"
        (klasor / ad).write_bytes(f"sahte {p}".encode())
        sumlar[ad] = hashlib.sha256(f"sahte {p}".encode()).hexdigest()
    return sumlar


def test_kok_server_json_sablonu():
    s = _sablon()
    assert s["name"] == "io.github.bulutbelge/bulutbelge"
    assert s["$schema"].endswith("/2025-12-11/server.schema.json")
    assert 1 <= len(s["description"]) <= 100
    assert s["packages"] == []  # sürüm hattı doldurur; şablonla yayın denetimden geçemez
    with pytest.raises(sj.SunucuJsonHatasi):
        sj.denetle(s)


def test_server_json_her_platform_icin_mcpb_paketi(tmp_path):
    sumlar = _paketler(tmp_path)
    veri = sj.uret(_sablon(), "1.2.3", "bulutbelge/bulutbelge", tmp_path, sumlar)
    assert veri["version"] == "1.2.3" and len(veri["packages"]) == 3
    for p, plat in zip(veri["packages"], sj.PLATFORMLAR):
        ad = f"bulutbelge-mcp-1.2.3-{plat}.mcpb"
        assert p == {
            "registryType": "mcpb",
            "identifier": f"https://github.com/bulutbelge/bulutbelge/releases/download/v1.2.3/{ad}",
            "version": "1.2.3",
            "fileSha256": sumlar[ad],
            "transport": {"type": "stdio"},
        }


def test_server_json_sha256sums_uyusmazsa_durur(tmp_path):
    sumlar = _paketler(tmp_path)
    sumlar["bulutbelge-mcp-1.2.3-linux-x64.mcpb"] = "0" * 64
    with pytest.raises(sj.SunucuJsonHatasi, match="SHA256SUMS"):
        sj.uret(_sablon(), "1.2.3", "bulutbelge/bulutbelge", tmp_path, sumlar)


def test_server_json_eksik_platformda_durur(tmp_path):
    _paketler(tmp_path)
    (tmp_path / "bulutbelge-mcp-1.2.3-windows-x64.mcpb").unlink()
    with pytest.raises(sj.SunucuJsonHatasi, match="windows-x64"):
        sj.uret(_sablon(), "1.2.3", "bulutbelge/bulutbelge", tmp_path, None)


def test_server_json_komut_satiri_ve_sha256sums_dosyasi(tmp_path):
    sumlar = _paketler(tmp_path / "rel")
    (tmp_path / "rel" / "SHA256SUMS").write_text("".join(f"{v}  {k}\n" for k, v in sumlar.items()), encoding="utf-8")
    cikti = tmp_path / "server.json"
    kod = sj.main(["--surum", "v1.2.3", "--dosyalar", str(tmp_path / "rel"), "--sha256sums",
                   str(tmp_path / "rel" / "SHA256SUMS"), "--cikti", str(cikti)])
    assert kod == 0 and json.loads(cikti.read_text(encoding="utf-8"))["version"] == "1.2.3"
