"""Intel Mac (x86_64) için hazır tekerleği olmayan motor bağımlılıklarını kaynaktan derleyip kurar.

Neden: kilitteki sürümlerin PyPI'da Intel Mac tekerleği yok: pymupdf 2.x (son Intel tekerleği 1.28.2),
cryptography 49+ (son 48.0.1) ve onnxruntime 1.24+ (kaynak arşivi de yok). Maskeleme motoru Apple Silicon ile
birebir aynı kalsın diye sürüm düşürülmez; aynı sürümler Intel makinede derlenir:

- pymupdf: kilitteki kaynak arşivi + PyMuPDF'in beklediği MuPDF kaynağı (özeti aşağıda sabit). Yalnızca çekirdek
  pymupdf paketi (`pymupdf-lite`) derlenir; motorun kullanmadığı pymupdf4llm, pymupdf-layout ve onnxruntime
  kurulmaz (PyInstaller zaten dışlıyor, build.py; NOTICE.md).
- cryptography: kilitteki kaynak arşivi, aşağıda özeti sabit OpenSSL kaynağından durağan (static) derlenen
  OpenSSL ile. Sistemdeki (Homebrew) OpenSSL'e bağlanmaz; paket macOS 13'te de açılır.

Güvence: her kaynak arşivi indirildikten sonra SHA-256 özeti doğrulanır (PyPI arşivleri `requirements.lock`
özetleriyle, MuPDF ve OpenSSL aşağıdaki sabitlerle); uyuşmazsa derleme yapılmaz. Derlenen tekerlekler önbellekte
tutulur. Derleme araçları (setuptools, maturin, swig, libclang) pip'in yalıtılmış derleme ortamına PyPI'dan gelir,
opencv_derle.py ile aynı yol.

Kullanım (motor ortamındaki Python ile, Intel Mac'te):
    python desktop/engine/macos_intel_derle.py --onbellek ~/.cache/bb-intel --kilit-yaz kalan.lock
    python -m pip install --require-hashes -r kalan.lock -r desktop/engine/requirements-macos.lock
    python desktop/engine/macos_intel_derle.py --onbellek ~/.cache/bb-intel --kur
Birinci çağrı tekerlekleri derler ve kilidin geri kalanını (derlenen ve atlanan paketler çıkarılmış) yazar;
üçüncü çağrı derlenen tekerlekleri kurar ve doğrular.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

KILIT = Path(__file__).resolve().parent / "requirements.lock"
HEDEF_MACOS = "13.0"

# Kilitten çıkarılıp kaynaktan derlenenler ve hiç kurulmayanlar.
DERLENEN = ("pymupdf", "cryptography")
ATLANAN = ("onnxruntime", "pymupdf-layout", "pymupdf4llm")

# MuPDF: pymupdf 2.1 setup.py'deki `version_mupdf`. Özet mupdf.com/releases sayfasındakiyle aynı (25 Kasım 2026).
MUPDF = (
    "1.28.6",
    "https://mupdf.com/downloads/archive/mupdf-1.28.6-source.tar.gz",
    "dc85000640a45d90ca9b77b061f6ca67cce0c4d4fbecf8819647baf573eef101",
)
# OpenSSL 3.5 (uzun destekli). Özet openssl.org ve GitHub sürüm sayfasındaki .sha256 dosyalarıyla aynı.
OPENSSL = (
    "3.5.9",
    "https://github.com/openssl/openssl/releases/download/openssl-3.5.9/openssl-3.5.9.tar.gz",
    "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a",
)


def kilit_bloklari(metin: str) -> list[tuple[str, str, str]]:
    """Kilit dosyasını (ad, sürüm, blok metni) parçalarına ayırır; ilk paketten önceki başlık atlanır."""
    out = []
    for blok in re.split(r"\n(?=[A-Za-z0-9_.\-]+==)", metin):
        m = re.match(r"([A-Za-z0-9_.\-]+)==([^\s;\\]+)", blok)
        if m:
            out.append((m.group(1).lower(), m.group(2), blok.rstrip("\n")))
    return out


def kalan_kilit(metin: str) -> str:
    """Derlenen ve atlanan paketler çıkarılmış kilit metni."""
    cikar = {*DERLENEN, *ATLANAN}
    kalan = [blok for ad, _, blok in kilit_bloklari(metin) if ad not in cikar]
    return "# macos_intel_derle.py ile üretildi: " + ", ".join(sorted(cikar)) + " çıkarıldı.\n" + "\n".join(kalan) + "\n"


def surum_ve_ozetler(metin: str, paket: str) -> tuple[str, set[str]]:
    for ad, surum, blok in kilit_bloklari(metin):
        if ad == paket:
            return surum, set(re.findall(r"sha256:([0-9a-f]{64})", blok))
    raise SystemExit(f"{paket} kilit dosyasında bulunamadı: {KILIT}")


def indir(url: str, hedef: Path, izinli: set[str]) -> Path:
    """Dosyayı indirir (önbellekte yoksa); özeti izinli kümede değilse siler ve durur."""
    if not hedef.is_file():
        with urllib.request.urlopen(url, timeout=600) as yanit:
            hedef.write_bytes(yanit.read())
    ozet = hashlib.sha256(hedef.read_bytes()).hexdigest()
    if ozet not in izinli:
        hedef.unlink(missing_ok=True)
        raise SystemExit(f"{hedef.name}: özet ({ozet}) beklenenle uyuşmuyor; derleme durduruldu")
    return hedef


def pypi_kaynak(paket: str, surum: str, izinli: set[str], klasor: Path) -> Path:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{paket}/{surum}/json", timeout=60) as yanit:
        bilgi = json.load(yanit)
    sdist = next((u for u in bilgi["urls"] if u["packagetype"] == "sdist"), None)
    if sdist is None:
        raise SystemExit(f"{paket} {surum} için kaynak arşivi yok")
    if sdist["digests"]["sha256"] not in izinli:
        raise SystemExit(f"{paket}: PyPI'daki kaynak arşivinin özeti kilit dosyasında yok; derleme durduruldu")
    return indir(sdist["url"], klasor / sdist["filename"], izinli)


def ac(arsiv: Path, hedef: Path) -> Path:
    if hedef.exists():
        shutil.rmtree(hedef)
    hedef.mkdir(parents=True)
    with tarfile.open(arsiv) as tar:
        tar.extractall(hedef, filter="data")
    return next(p for p in hedef.iterdir() if p.is_dir())


def ortam(**ek: str) -> dict[str, str]:
    return dict(os.environ, MACOSX_DEPLOYMENT_TARGET=HEDEF_MACOS, ARCHFLAGS="-arch x86_64", **ek)


def tekerlek_derle(kaynak: Path, klasor: Path, env: dict[str, str]) -> None:
    subprocess.run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir", str(kaynak), "-w", str(klasor)],
        env=env, check=True,
    )


def openssl_derle(onbellek: Path) -> Path:
    surum, url, ozet = OPENSSL
    onek = onbellek / f"openssl-{surum}-{HEDEF_MACOS}"
    if (onek / "lib" / "libcrypto.a").is_file():
        return onek
    is_klasoru = onbellek / "is-openssl"
    is_klasoru.mkdir(parents=True, exist_ok=True)
    kaynak = ac(indir(url, is_klasoru / f"openssl-{surum}.tar.gz", {ozet}), is_klasoru / "kaynak")
    env = ortam()
    print(f"OpenSSL {surum} kaynaktan derleniyor (durağan, macOS {HEDEF_MACOS})", flush=True)
    subprocess.run(
        ["./Configure", "darwin64-x86_64-cc", "no-shared", "no-tests", "no-docs",
         f"--prefix={onek}", f"--openssldir={onek}/ssl", "--libdir=lib"],
        cwd=kaynak, env=env, check=True,
    )
    subprocess.run(["make", f"-j{os.cpu_count() or 2}"], cwd=kaynak, env=env, check=True)
    subprocess.run(["make", "install_sw"], cwd=kaynak, env=env, check=True)
    shutil.rmtree(is_klasoru, ignore_errors=True)
    return onek


def derle(onbellek: Path) -> Path:
    metin = KILIT.read_text(encoding="utf-8")
    pm_surum, pm_ozet = surum_ve_ozetler(metin, "pymupdf")
    cr_surum, cr_ozet = surum_ve_ozetler(metin, "cryptography")
    anahtar = hashlib.sha256(
        json.dumps([pm_surum, cr_surum, MUPDF, OPENSSL, HEDEF_MACOS]).encode()
    ).hexdigest()[:12]
    klasor = onbellek / f"tekerlek-{anahtar}"
    klasor.mkdir(parents=True, exist_ok=True)
    is_klasoru = onbellek / "is"
    is_klasoru.mkdir(parents=True, exist_ok=True)

    if not list(klasor.glob("pymupdf*.whl")):
        mupdf = ac(indir(MUPDF[1], is_klasoru / f"mupdf-{MUPDF[0]}-source.tar.gz", {MUPDF[2]}), is_klasoru / "mupdf")
        kaynak = ac(pypi_kaynak("pymupdf", pm_surum, pm_ozet, is_klasoru), is_klasoru / "pymupdf")
        print(f"pymupdf {pm_surum} (MuPDF {MUPDF[0]}) kaynaktan derleniyor; uzun sürebilir", flush=True)
        # MuPDF yerel klasörden alınır: setup.py'nin kendi (özetsiz) indirmesi çalışmaz.
        tekerlek_derle(kaynak, klasor, ortam(PYMUPDF_SETUP_MUPDF_BUILD=str(mupdf)))
    if not list(klasor.glob("cryptography*.whl")):
        onek = openssl_derle(onbellek)
        kaynak = ac(pypi_kaynak("cryptography", cr_surum, cr_ozet, is_klasoru), is_klasoru / "cryptography")
        print(f"cryptography {cr_surum} kaynaktan derleniyor (OpenSSL {OPENSSL[0]}, durağan)", flush=True)
        tekerlek_derle(kaynak, klasor, ortam(OPENSSL_DIR=str(onek), OPENSSL_STATIC="1"))
    shutil.rmtree(is_klasoru, ignore_errors=True)
    for t in sorted(klasor.glob("*.whl")):
        print(f"Tekerlek: {t.name}", flush=True)
    return klasor


DOGRULA = r"""
import pathlib, subprocess, sys
import pymupdf
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
anahtar = AESGCM.generate_key(bit_length=256)
assert AESGCM(anahtar).decrypt(b"0" * 12, AESGCM(anahtar).encrypt(b"0" * 12, b"deneme", None), None) == b"deneme"
belge = pymupdf.open()
belge.new_page().insert_text((50, 50), "Deneme")
assert "Deneme" in belge[0].get_text()
assert hasattr(pymupdf.Page, "get_textpage_ocr")
import cryptography.hazmat.bindings._rust as r
bag = subprocess.run(["otool", "-L", r.__file__], capture_output=True, text=True, check=True).stdout
assert "libssl" not in bag and "libcrypto" not in bag, "cryptography sistemdeki OpenSSL'e bağlı: " + bag
print("pymupdf", pymupdf.VersionBind, "MuPDF", pymupdf.mupdf_version, "| cryptography tamam")
"""


def kur(onbellek: Path) -> None:
    klasorler = sorted(onbellek.glob("tekerlek-*"), key=lambda p: p.stat().st_mtime)
    if not klasorler:
        raise SystemExit("Derlenmiş tekerlek yok; önce --kilit-yaz ile derleyin")
    tekerlekler = sorted(str(t) for t in klasorler[-1].glob("*.whl"))
    if len(tekerlekler) != len(DERLENEN):
        raise SystemExit(f"Beklenen {len(DERLENEN)} tekerlek, bulunan {len(tekerlekler)}")
    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", *tekerlekler], check=True)
    subprocess.run([sys.executable, "-c", DOGRULA], check=True)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onbellek", type=Path, default=Path.home() / ".cache" / "bb-intel")
    ap.add_argument("--kilit-yaz", type=Path, help="Derle ve kilidin geri kalanını bu dosyaya yaz")
    ap.add_argument("--kur", action="store_true", help="Derlenmiş tekerlekleri kur ve doğrula")
    args = ap.parse_args()
    if not args.kilit_yaz and not args.kur:
        ap.error("--kilit-yaz ya da --kur gerekli")
    if sys.platform != "darwin" or platform.machine() != "x86_64":
        raise SystemExit("Bu betik yalnızca Intel Mac'te (x86_64) çalışır")
    if args.kilit_yaz:
        derle(args.onbellek)
        args.kilit_yaz.write_text(kalan_kilit(KILIT.read_text(encoding="utf-8")), encoding="utf-8")
        print(f"Kilidin geri kalanı yazıldı: {args.kilit_yaz}", flush=True)
    if args.kur:
        kur(args.onbellek)


if __name__ == "__main__":
    main()
