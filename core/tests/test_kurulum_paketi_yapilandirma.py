"""Windows kurulum paketi türleri: varsayılan bootstrapper, ayrı çevrimdışı paket."""
import json
from pathlib import Path

import yaml

KOK = Path(__file__).resolve().parents[2]
TAURI = KOK / "desktop" / "src-tauri"
# Bitbucket deposunda kaynak yerinde, açık depoda .github/ altında
DERLEME = next((p for p in (KOK / "core" / "tools" / "acik_kaynak" / "github" / "workflows" / "derleme.yml",
                             KOK / ".github" / "workflows" / "derleme.yml") if p.is_file()),
               KOK / ".github" / "workflows" / "derleme.yml")


def _json(ad):
    return json.loads((TAURI / ad).read_text(encoding="utf-8"))


def test_varsayilan_webview2_bootstrapper():
    mod = _json("tauri.conf.json")["bundle"]["windows"]["webviewInstallMode"]
    assert mod["type"] == "downloadBootstrapper"
    assert mod["silent"] is True


def test_kaldiricilar_kurulum_yeri_anahtarini_siler():
    """W.2: kalıntı HKCU anahtarı sonraki MSI kurulumunu %LOCALAPPDATA%'ya yönlendiriyordu."""
    anahtar = "Software\\proteksistem\\BulutBelge"
    wix = _json("tauri.conf.json")["bundle"]["windows"]["wix"]
    assert wix["fragmentPaths"] == ["windows/wix/kayit-temizle.wxs"]
    assert wix["componentRefs"] == ["KayitAnahtariTemizle"]
    parca = (TAURI / "windows" / "wix" / "kayit-temizle.wxs").read_text(encoding="utf-8")
    assert '<Component Id="KayitAnahtariTemizle"' in parca
    assert f'<RemoveRegistryKey Id="KayitAnahtariKaldir" Root="HKCU" Key="{anahtar}" Action="removeOnUninstall"' in parca
    kanca = (TAURI / "windows" / "hooks.nsh").read_text(encoding="utf-8")
    kaldirma = kanca.split("!macro NSIS_HOOK_POSTUNINSTALL", 1)[1]
    assert f'DeleteRegKey HKCU "{anahtar}"' in kaldirma


def test_kurulum_metinleri_w5():
    """W.5: NSIS karşılama metnindeki yazım hatası ve lisans alt metni ile düğme ('Katılıyorum') uyumu;
    MSI tek lisans dosyası aldığı için KOSULLAR.rtf İngilizce bölüm de taşır."""
    nsis = _json("tauri.conf.json")["bundle"]["windows"]["nsis"]
    assert nsis["customLanguageFiles"] == {
        "Turkish": "windows/nsis/Turkish.nsh",
        "English": "windows/nsis/English.nsh",
    }
    kanca = (TAURI / "windows" / "hooks.nsh").read_text(encoding="utf-8")
    once = kanca.split("!macro", 1)[0]
    assert '!define MUI_WELCOMEPAGE_TEXT "$(bbKarsilama)"' in once
    assert '!define MUI_LICENSEPAGE_TEXT_BOTTOM "$(bbLisansAlt)"' in once
    for dil, sabit in (("Turkish", "LANG_TURKISH"), ("English", "LANG_ENGLISH")):
        metin = (TAURI / "windows" / "nsis" / f"{dil}.nsh").read_text(encoding="utf-8")
        assert "{{" not in metin, "Tauri dil dosyalarını işlemez; yer tutucu metinde görünür"
        for ad in ("bbKarsilama", "bbLisansAlt", "deleteAppData", "webview2AbortError"):
            assert f"LangString {ad} ${{{sabit}}} " in metin, (dil, ad)
    tr = (TAURI / "windows" / "nsis" / "Turkish.nsh").read_text(encoding="utf-8")
    assert "diğer programları kapatmanızı" in tr and "'Katılıyorum' düğmesine" in tr
    rtf = (TAURI / "windows" / "KOSULLAR.rtf").read_bytes().decode("ascii")
    assert "Before you start (English)" in rtf and rtf.rstrip().endswith("}")

def test_cevrimdisi_yapilandirma_yalnizca_webview_modu():
    cfg = _json("tauri.offline.conf.json")
    assert cfg["bundle"] == {"windows": {"webviewInstallMode": {"type": "offlineInstaller"}}}


def test_derleme_yml_gecerli_ve_cevrimdisi_adim_var():
    metin = DERLEME.read_text(encoding="utf-8")
    yaml.safe_load(metin)
    assert "--config src-tauri/tauri.offline.conf.json" in metin
    assert "-cevrimdisi" in metin
    assert "sha256sum" in metin
