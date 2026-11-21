"""Motoru klasör (PyInstaller --onedir) olarak paketler ve Tauri'nin kaynak olarak
alacağı yere (`src-tauri/binaries/engine/`) koyar.

Tek dosya (--onefile) her açılışta ~140 MB'ı geçici klasöre açıyordu (ilk yanıt ~4,3 sn); klasör
biçiminde ~0,1 sn (TAKIP 1.90, 17 Kasım 2026 ölçümü).

Kullanım: engine/.venv içindeki Python ile `python build.py`
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent
BIN_DIR = ENGINE_DIR.parent / "src-tauri" / "binaries"
CORE_DIR = ENGINE_DIR.parent.parent / "core"


def target_triple() -> str:
    # CI (TAKIP 1.87): Rust kurulu olmayan temiz ortamda hedef ortam değişkeninden verilir.
    if os.environ.get("BULUTBELGE_TARGET"):
        return os.environ["BULUTBELGE_TARGET"]
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("rustc host üçlüsü bulunamadı")


def main() -> None:
    work = ENGINE_DIR / "build"
    tessdata = ENGINE_DIR / "tessdata"
    if not (tessdata / "tur.traineddata").is_file():
        raise SystemExit("OCR dil dosyaları yok; önce `python tessdata_indir.py` çalıştırın")
    subprocess.run(
        [
            sys.executable, "-m", "PyInstaller",
            "--onedir", "--noconfirm", "--clean",
            "--name", "bulutbelge-engine",
            "--distpath", str(work / "dist"),
            "--workpath", str(work / "work"),
            "--specpath", str(work),
            # Çekirdek düzenlenebilir kurulumla gelir; PyInstaller kaynağı doğrudan görsün.
            "--paths", str(CORE_DIR),
            # Belge komutları ilk kullanımda yüklenir, statik analiz göremez.
            "--hidden-import", "bulutbelge_engine.commands",
            "--hidden-import", "lxml.etree",
            # Yüz tespiti modeli (haarcascade xml) OpenCV paketinin veri dosyasıdır.
            "--collect-data", "cv2",
            # OCR dil dosyaları exe'nin içine gömülür (çalışırken _MEIPASS/tessdata).
            "--add-data", f"{tessdata}{os.pathsep}tessdata",
            # Ajan kılavuzu (`bulutbelge-engine kilavuz`) paketin içinde gelir.
            "--add-data", f"{ENGINE_DIR / 'bulutbelge_engine' / 'kilavuz.md'}{os.pathsep}bulutbelge_engine",
            str(ENGINE_DIR / "run_engine.py"),
        ],
        check=True,
        cwd=ENGINE_DIR,
    )
    ext = ".exe" if sys.platform == "win32" else ""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = BIN_DIR / "engine"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(work / "dist" / "bulutbelge-engine", dest)
    print(f"Motor paketlendi: {dest / ('bulutbelge-engine' + ext)}")


if __name__ == "__main__":
    main()
