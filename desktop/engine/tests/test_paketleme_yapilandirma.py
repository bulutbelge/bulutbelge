"""Paketleme yapılandırması: lisans dosyası yolu ve Windows'a özgü hash'li bağımlılıklar (TAKIP 1.106)."""

from __future__ import annotations

import json
import re
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
TAURI = ENGINE.parent / "src-tauri"


def test_lisans_dosyasi_bundle_altinda_ve_var():
    conf = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    bundle = conf["bundle"]
    windows = bundle.get("windows", {})
    assert "licenseFile" not in windows.get("nsis", {})
    assert "licenseFile" not in windows.get("wix", {})
    assert (TAURI / bundle["licenseFile"]).is_file()


def test_csp_satir_ici_stil_ve_betik_izni_vermez():
    """TAKIP 1.90: Word önizlemesinin stilleri CSSOM ile uygulanır (WordPreview.adoptRenderedStyles); politika gevşetilmez."""
    csp = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["app"]["security"]["csp"]
    yonergeler = {p.split()[0]: p.split()[1:] for p in (x.strip() for x in csp.split(";")) if p}
    assert "'unsafe-inline'" not in csp and "'unsafe-eval'" not in csp
    assert yonergeler["style-src"] == ["'self'"]
    assert yonergeler["object-src"] == ["'none'"] and yonergeler["frame-ancestors"] == ["'none'"]


def test_deb_paketi_man_sayfasini_icerir():
    """D.8: belge_uret.py'nin ürettiği man sayfası .deb'e /usr/share/man/man1 altında girer."""
    deb = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))["bundle"]["linux"]["deb"]["files"]
    kaynak = deb["/usr/share/man/man1/bulutbelge.1"]
    assert (TAURI / kaynak).resolve().is_file()
    assert ".TH BULUTBELGE 1" in (TAURI / kaynak).read_text(encoding="utf-8")
    # Komut satırı kısa adı: motorun .deb'deki yerine (engine.rs aday yolu) yönlendirir, LF satır sonlu.
    kisa = (TAURI / deb["/usr/bin/bulutbelge"]).read_bytes()
    assert kisa.startswith(b"#!/bin/sh") and b"\r" not in kisa
    assert b"/usr/lib/BulutBelge/engine/bulutbelge-engine" in kisa
    assert '"lib").join("BulutBelge").join("engine")' in (TAURI / "src" / "engine.rs").read_text(encoding="utf-8")


def _girdi(ad: str) -> str:
    metin = (ENGINE / "requirements.lock").read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(ad)}==[^\n]*(?:\n[ \t]+[^\n]*)*", metin, re.M)
    assert m, f"{ad} kilitte yok"
    return m.group(0)


def test_kilitte_windows_bagimliliklari_hashli_ve_isaretli():
    for ad in ("pefile", "pywin32-ctypes"):
        girdi = _girdi(ad)
        ilk = girdi.splitlines()[0]
        assert '; sys_platform == "win32"' in ilk
        assert len(re.findall(r"--hash=sha256:[0-9a-f]{64}\b", girdi)) >= 2


def test_wix_turkce_yerellestirme_dosyasi_var_ve_launchapp_tanimli():
    """MSI bitiş sayfasındaki 'Launch' kutusu Türkçe olsun (TAKIP 1.110)."""
    conf = json.loads((TAURI / "tauri.conf.json").read_text(encoding="utf-8"))
    dil = conf["bundle"]["windows"]["wix"]["language"]
    assert isinstance(dil, dict) and "en-US" in dil
    yol = TAURI / dil["tr-TR"]["localePath"]
    assert yol.is_file()
    metin = yol.read_text(encoding="utf-8")
    assert 'Culture="tr-TR"' in metin
    assert re.search(r'<String Id="LaunchApp">[^<]+</String>', metin)
