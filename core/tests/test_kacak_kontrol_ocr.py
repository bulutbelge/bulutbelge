"""kacak_kontrol.py: OCR yokken görsel kontrolü sessizce 'temiz' saymaz (TAKIP 1.80)."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

KOK = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location("kacak_kontrol", KOK / "core" / "tools" / "kacak_kontrol.py")
kk = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(kk)


def test_ocr_yoksa_gorsel_kontrolu_basarisiz(tmp_path, monkeypatch, capsys):
    klasor = tmp_path / "ornek"
    klasor.mkdir()
    (klasor / "a.jpg").write_bytes(b"\xff\xd8\xff")
    (klasor / "beklenen.json").write_text(json.dumps({"a.jpg": {"degerler": ["28765432164"]}}), encoding="utf-8")
    cikti = klasor / "a_maskeli.jpg"
    cikti.write_bytes(b"\xff\xd8\xff")
    monkeypatch.setattr(kk, "_mask", lambda *a, **k: cikti)
    monkeypatch.setattr(kk, "is_image", lambda p: True)
    monkeypatch.setattr(kk, "_layers", lambda p: {})
    monkeypatch.setattr(kk, "scan_pdf", lambda *a, **k: SimpleNamespace(findings=[], warnings=["Görselde metin katmanı yok ve OCR dil dosyaları kurulu değil."]))
    assert kk.check(klasor, tmp_path / "cikti") == 1
    assert "KONTROL YAPILAMADI" in capsys.readouterr().out
