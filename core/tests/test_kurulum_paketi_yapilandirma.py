"""Windows kurulum paketi türleri: varsayılan bootstrapper, ayrı çevrimdışı paket."""
import json
import re
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


def test_nsis_turkce_mui_hatalari_dil_dosyasinda_duzeltilir():
    """24 Kasım ekran kontrolü: NSIS'in Türkçe MUI dosyasındaki "bilgisayariniza" (çift boşluklu),
    "Litfen", "Tamamlandır", "Programi" metinleri kendi dil dosyamızda aynı adla yeniden tanımlanır.
    Kaldırma iletisi de kurulum dilinde (LangString) gösterilir."""
    tr = (TAURI / "windows" / "nsis" / "Turkish.nsh").read_text(encoding="utf-8")
    for ad in (
        "MUI_TEXT_FINISH_INFO_TEXT",
        "MUI_TEXT_FINISH_INFO_REBOOT",
        "MUI_UNTEXT_UNINSTALLING_SUBTITLE",
        "MUI_UNTEXT_FINISH_TITLE",
        "MUI_UNTEXT_ABORTWARNING",
    ):
        assert f"LangString {ad} ${{LANG_TURKISH}} " in tr, ad
    for hatali in ("bilgisayariniza", "Litfen", "Tamamlandır\"", "Programi ", "  bilgisayar", "gerekiyor.B"):
        assert hatali not in tr, hatali
    kanca = (TAURI / "windows" / "hooks.nsh").read_text(encoding="utf-8")
    kaldirma = kanca.split("!macro NSIS_HOOK_POSTUNINSTALL", 1)[1]
    assert 'MessageBox MB_OK|MB_ICONINFORMATION "$(bbVeriKaldi)"' in kaldirma
    assert "Ayarlarınız" not in kanca
    for dil, sabit in (("Turkish", "LANG_TURKISH"), ("English", "LANG_ENGLISH")):
        metin = (TAURI / "windows" / "nsis" / f"{dil}.nsh").read_text(encoding="utf-8")
        assert f"LangString bbVeriKaldi ${{{sabit}}} " in metin, dil
        assert "$APPDATA\\com.proteksistem.bulutbelge" in metin, dil

def test_cevrimdisi_yapilandirma_yalnizca_webview_modu():
    cfg = _json("tauri.offline.conf.json")
    assert cfg["bundle"] == {"windows": {"webviewInstallMode": {"type": "offlineInstaller"}}}


def test_derleme_yml_gecerli_ve_cevrimdisi_adim_var():
    metin = DERLEME.read_text(encoding="utf-8")
    yaml.safe_load(metin)
    assert "--config src-tauri/tauri.offline.conf.json" in metin
    assert "-cevrimdisi" in metin
    assert "sha256sum" in metin


def test_derleme_yml_intel_mac_satiri():
    """Intel Mac paketi: Intel makinede (macos-15-intel) x86_64 hedefiyle derlenir; motor bağımlılıkları
    macos_intel_derle.py ile kurulur (önbellekli); imza, notarize ve mühür adımları iki Mac satırında da çalışır."""
    metin = DERLEME.read_text(encoding="utf-8")
    satir = re.search(r"mac_intel='(\{.*\})'", metin)
    assert satir, "Intel Mac matris satırı yok"
    intel = json.loads(satir.group(1))
    assert intel["calistirici"] == "macos-15-intel" and intel["hedef"] == "x86_64-apple-darwin"
    assert intel["intel"] is True and intel["paketler"] == "dmg" and intel["mcpb"] == ""
    assert 'liste="[$win,$mac,$mac_intel,$lin]"' in metin
    assert "macos_intel_derle.py --onbellek ~/.cache/bb-intel --kilit-yaz" in metin and "--kur" in metin
    assert "matrix.ad == 'macos'" not in metin, "macOS adımları startsWith(matrix.ad, 'macos') ile iki satırı da kapsamalı"
    assert metin.count("startsWith(matrix.ad, 'macos')") == 3
    assert "if: matrix.mcpb != ''" in metin


def test_testler_yml_cekme_isteginde_guvenli_ve_sabit():
    """Çekme isteği testleri: dış katkıcı kodu çalışır, bu yüzden salt okuma ve pull_request_target yok.
    İş adı `Testler` dal kuralında zorunlu kontroldür (scripts/github_koruma.sh)."""
    testler = DERLEME.with_name("testler.yml")
    metin = testler.read_text(encoding="utf-8")
    yml = yaml.safe_load(metin)
    tetik = yml.get("on", yml.get(True))  # YAML 1.1: "on" anahtarı True okunabilir
    assert set(tetik) == {"pull_request", "push"} and tetik["push"]["branches"] == ["main"]
    assert "secrets." not in metin  # pull_request_target yukarıdaki tetikleyici kümesiyle dışlandı
    assert yml["permissions"] == {"contents": "read"}
    assert [i["name"] for i in yml["jobs"].values()] == ["Testler"]
    assert "pytest" in metin and "tauri build" not in metin

    # Her iş akışında eylemler 40 haneli commit SHA'sıyla sabit; testler.yml derleme.yml ile aynı SHA'yı kullanır.
    # Yorum satırları (ör. SignPath yer tutucusu) sayılmaz.
    kalip = re.compile(r"^\s*-?\s*uses:\s*([\w.-]+/[\w.-]+)@(\S+)", re.MULTILINE)
    derleme = dict(kalip.findall(DERLEME.read_text(encoding="utf-8")))
    for yol in DERLEME.parent.glob("*.yml"):
        for eylem, ref in kalip.findall(yol.read_text(encoding="utf-8")):
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (yol.name, eylem)
    assert kalip.findall(metin)
    for eylem, ref in kalip.findall(metin):
        assert derleme.get(eylem) == ref, eylem

    koruma = KOK / "scripts" / "github_koruma.sh"  # yalnızca Bitbucket deposunda
    if koruma.is_file():
        assert '{"context": "Testler"}' in koruma.read_text(encoding="utf-8")
