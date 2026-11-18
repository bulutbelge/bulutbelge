"""core/tools/belge_denetle.py: pre-push belge denetimi mantığı (TAKIP D.4)."""
import importlib.util
from pathlib import Path

BETIK = Path(__file__).resolve().parents[2] / "core" / "tools" / "belge_denetle.py"
spec = importlib.util.spec_from_file_location("belge_denetle", BETIK)
bd = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bd)

KOD = "server/bulutbelge_server/api.py"


def test_kod_var_belge_yok_uyarir():
    assert bd.belge_uyarisi_gerekli([KOD, "docs/TAKIP.md", "docs/kararlar/x.md"], "sahte: ek")


def test_belge_ya_da_readme_varsa_uyarmaz():
    assert not bd.belge_uyarisi_gerekli([KOD, "docs/sunucu/isletme.md"], "m")
    assert not bd.belge_uyarisi_gerekli(["web/src/a.tsx", "web/README.md"], "m")


def test_muafiyet_ve_kodsuz_degisiklik():
    assert not bd.belge_uyarisi_gerekli([KOD], "ek\n\nBelge: gerek yok")
    assert not bd.belge_uyarisi_gerekli(["core/x.py", "scripts/y.py"], "m")
    assert bd.belge_uyarisi_gerekli(["desktop/engine/a.py"], "m")
    assert bd.belge_uyarisi_gerekli(["desktop/src/A.tsx"], "m")


def test_uretim_denetimi_kapsami():
    assert bd.uretim_denetimi_gerekli(["core/x.py"])
    assert not bd.uretim_denetimi_gerekli(["docs/a.md", "web/src/a.tsx"])


def test_eski_belge_durdurur(monkeypatch, capsys):
    monkeypatch.setattr(bd, "_git", lambda *a: "core/x.py\n" if a[0] == "diff" else "m")
    monkeypatch.setattr(bd, "uretilen_eski_mi", lambda: True)
    assert bd.main(["a..b"]) == 1
    monkeypatch.setattr(bd, "uretilen_eski_mi", lambda: False)
    assert bd.main(["a..b"]) == 0


def test_uyari_durdurmaz(monkeypatch, capsys):
    monkeypatch.setattr(bd, "_git", lambda *a: KOD + "\n" if a[0] == "diff" else "m")
    assert bd.main(["a..b"]) == 0
    assert "UYARI" in capsys.readouterr().out
