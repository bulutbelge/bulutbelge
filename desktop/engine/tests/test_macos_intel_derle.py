"""macos_intel_derle.py: kilidin Intel Mac için ayrılması ve sabit kaynak özetleri (ağ ve derleme olmadan)."""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

BETIK = Path(__file__).resolve().parents[1] / "macos_intel_derle.py"
spec = importlib.util.spec_from_file_location("macos_intel_derle", BETIK)
mid = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mid)

KILIT = mid.KILIT.read_text(encoding="utf-8")


def _adlar(metin: str) -> set[str]:
    return {ad for ad, _, _ in mid.kilit_bloklari(metin)}


def test_kalan_kilit_derlenen_ve_atlanan_paketleri_cikarir():
    kalan = mid.kalan_kilit(KILIT)
    cikan = {*mid.DERLENEN, *mid.ATLANAN}
    assert cikan <= _adlar(KILIT), "Kilitte beklenen paketler yok; betik güncellenmeli"
    assert not cikan & _adlar(kalan)
    assert _adlar(kalan) == _adlar(KILIT) - cikan
    # Kalan her paket özetli kalır (pip --require-hashes).
    for ad, _, blok in mid.kilit_bloklari(kalan):
        assert re.search(r"--hash=sha256:[0-9a-f]{64}", blok), ad


def test_kalan_paketlerden_hicbiri_cikarilan_pakete_bagli_degil():
    # pip-compile "# via" satırları: kalan bir paket yalnızca çıkarılan bir paket yüzünden kilitteyse uyarı verilmez,
    # ama çıkarılan paketin bağımlısı (ör. pymupdf'e bağlı pymupdf4llm) kalanda olmamalı.
    for ad, _, blok in mid.kilit_bloklari(mid.kalan_kilit(KILIT)):
        assert ad not in ("pymupdf4llm", "pymupdf-layout"), ad


def test_derlenen_paketlerin_kilitte_ozeti_var():
    for paket in mid.DERLENEN:
        surum, ozetler = mid.surum_ve_ozetler(KILIT, paket)
        assert surum and ozetler


def test_sabit_kaynak_ozetleri_gecerli():
    for surum, url, ozet in (mid.MUPDF, mid.OPENSSL):
        assert re.fullmatch(r"[0-9a-f]{64}", ozet)
        assert url.startswith("https://") and surum in url and url.endswith(".tar.gz")


def test_ozet_uyusmazsa_dosya_silinir_ve_durur(tmp_path):
    dosya = tmp_path / "arsiv.tar.gz"
    dosya.write_bytes(b"sahte")
    with pytest.raises(SystemExit):
        mid.indir("https://ornek.invalid/arsiv.tar.gz", dosya, {"0" * 64})
    assert not dosya.exists()


@pytest.mark.skipif(sys.platform == "darwin" and mid.platform.machine() == "x86_64", reason="Intel Mac'te çalışır")
def test_intel_mac_disinda_calismaz(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["macos_intel_derle.py", "--kur"])
    with pytest.raises(SystemExit, match="yalnızca Intel Mac"):
        mid.main()
