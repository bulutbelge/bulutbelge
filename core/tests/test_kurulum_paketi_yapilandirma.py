"""Windows kurulum paketi türleri (TAKIP 1.111): varsayılan bootstrapper, ayrı çevrimdışı paket."""
import json
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[2]
TAURI = KOK / "desktop" / "src-tauri"
# Bitbucket deposunda kaynak yerinde, açık depoda .github/ altında (TAKIP 1.106)
DERLEME = next((p for p in (KOK / "core" / "tools" / "acik_kaynak" / "github" / "workflows" / "derleme.yml",
                             KOK / ".github" / "workflows" / "derleme.yml") if p.is_file()),
               KOK / ".github" / "workflows" / "derleme.yml")


def _json(ad):
    return json.loads((TAURI / ad).read_text(encoding="utf-8"))


def test_varsayilan_webview2_bootstrapper():
    mod = _json("tauri.conf.json")["bundle"]["windows"]["webviewInstallMode"]
    assert mod["type"] == "downloadBootstrapper"
    assert mod["silent"] is True


def test_cevrimdisi_yapilandirma_yalnizca_webview_modu():
    cfg = _json("tauri.offline.conf.json")
    assert cfg["bundle"] == {"windows": {"webviewInstallMode": {"type": "offlineInstaller"}}}


def test_derleme_yml_gecerli_ve_cevrimdisi_adim_var():
    metin = DERLEME.read_text(encoding="utf-8")
    yaml.safe_load(metin)
    assert "--config src-tauri/tauri.offline.conf.json" in metin
    assert "-cevrimdisi" in metin
    assert "sha256sum" in metin
