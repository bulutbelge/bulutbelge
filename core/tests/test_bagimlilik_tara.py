"""Bağımlılık taraması betiği: SBOM üretimi ve ağ yoksa atlama. Yalnızca sahte veri."""
import importlib.util
import json
from pathlib import Path

YOL = Path(__file__).resolve().parents[1] / "tools" / "bagimlilik_tara.py"


def _yukle():
    spec = importlib.util.spec_from_file_location("bagimlilik_tara", YOL)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def test_ag_yoksa_taramalar_atlanir_sbom_uretilir(tmp_path, capsys):
    m = _yukle()
    assert m.main(["--cikti", str(tmp_path), "--ag-yok"]) == 0
    assert "ağ yok" in capsys.readouterr().out
    belge = json.loads((tmp_path / "sbom-python.cdx.json").read_text(encoding="utf-8"))
    assert belge["bomFormat"] == "CycloneDX"
    assert belge["components"]


def test_npm_ve_cargo_kilit_dosyasindan_bilesen(tmp_path):
    m = _yukle()
    (tmp_path / "package-lock.json").write_text(json.dumps({"packages": {
        "": {"name": "sahte"},
        "node_modules/sahte-paket": {"version": "1.2.3"},
        "node_modules/@sahte/ek": {"version": "0.1.0"},
    }}), encoding="utf-8")
    (tmp_path / "Cargo.lock").write_text(
        '[[package]]\nname = "yerel"\nversion = "0.1.0"\n\n'
        '[[package]]\nname = "sahte-kasa"\nversion = "2.0.0"\nsource = "registry+x"\n',
        encoding="utf-8")
    npm = m.npm_bilesenleri(tmp_path)
    assert {b["purl"] for b in npm} == {"pkg:npm/sahte-paket@1.2.3", "pkg:npm/%40sahte/ek@0.1.0"}
    assert [b["name"] for b in m.cargo_bilesenleri(tmp_path)] == ["sahte-kasa"]


def test_arac_yoksa_tarama_atlanir(tmp_path):
    m = _yukle()
    assert m.tara("sahte", ["yok-boyle-bir-arac-xyz"], tmp_path) is None
