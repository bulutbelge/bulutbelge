"""scripts/surum_yayinla.py: SHA256SUMS ve surum.json üretimi (TAKIP 1.89)."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

BETIK = Path(__file__).resolve().parents[2] / "scripts" / "surum_yayinla.py"
spec = importlib.util.spec_from_file_location("surum_yayinla", BETIK)
sy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sy)


def test_ozet_ve_surum_json(tmp_path):
    (tmp_path / "BulutBelge_0.2.0_x64.msi").write_bytes(b"sahte kurulum")
    (tmp_path / "notlar.txt").write_text("alınmaz")
    sj = tmp_path / "surum.json"
    sj.write_text(json.dumps({"surum": "0.1.0", "indirme": "https://bulutbelge.com/indir"}))
    assert sy.main([str(tmp_path), "--surum", "0.2.0", "--surum-json", str(sj)]) == 0
    beklenen = hashlib.sha256(b"sahte kurulum").hexdigest()
    assert (tmp_path / "SHA256SUMS").read_text() == f"{beklenen}  BulutBelge_0.2.0_x64.msi\n"
    veri = json.loads(sj.read_text())
    assert veri["surum"] == "0.2.0" and veri["indirme"] == "https://bulutbelge.com/indir"
    assert veri["dosyalar"] == [{"ad": "BulutBelge_0.2.0_x64.msi", "sha256": beklenen, "boyut": 13}]


def test_gecersiz_surum_ve_bos_klasor(tmp_path):
    (tmp_path / "a.msi").write_bytes(b"x")
    assert sy.main([str(tmp_path), "--surum", "abc", "--surum-json", str(tmp_path / "s.json")]) == 2
    bos = tmp_path / "bos"
    bos.mkdir()
    assert sy.main([str(bos), "--surum", "0.2.0", "--surum-json", str(tmp_path / "s.json")]) == 2
    assert not (tmp_path / "s.json").exists()


def test_uygulamanin_okudugu_alanlar_korunur(tmp_path):
    (tmp_path / "a.msi").write_bytes(b"x")
    sj = tmp_path / "s.json"
    sy.uret(tmp_path, "1.0.0", sj)
    veri = json.loads(sj.read_text())
    assert {"surum", "indirme"} <= set(veri)
