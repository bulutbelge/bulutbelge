"""Motoru klasör (PyInstaller --onedir) olarak paketler ve Tauri'nin kaynak olarak
alacağı yere (`src-tauri/binaries/engine/`) koyar.

Tek dosya (--onefile) her açılışta ~140 MB'ı geçici klasöre açıyordu (ilk yanıt ~4,3 sn); klasör
biçiminde ~0,1 sn (17 Kasım 2026 ölçümü).

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
    # CI: Rust kurulu olmayan temiz ortamda hedef ortam değişkeninden verilir.
    if os.environ.get("BULUTBELGE_TARGET"):
        return os.environ["BULUTBELGE_TARGET"]
    out = subprocess.run(["rustc", "-vV"], capture_output=True, text=True, check=True).stdout
    for line in out.splitlines():
        if line.startswith("host:"):
            return line.split(":", 1)[1].strip()
    raise RuntimeError("rustc host üçlüsü bulunamadı")


# Pakete girmemesi gereken klasörler: PyMuPDF'nin düzen çözümleme modülü ve model dosyaları
# (~50 MB; yalnızca `get_layout`/`find_tables` kullanır, motor ikisini de çağırmaz) ve C geliştirme
# başlıkları. PyInstaller kancası bunları veri dosyası olarak topluyor.
SILINECEK = ("pymupdf/layout", "pymupdf/mupdf-devel")

# Pakette bulunursa derleme durur. Ad parçası, büyük/küçük harf duyarsız.
# - pymupdf4llm, onnxruntime: kullanılmaz; lisans ve boyut (NOTICE.md).
# - FFmpeg ve GPL kodekleri: OpenCV video modülü olmadan (FFmpeg'siz) derlenmiş olmalı.
YASAK_PARCALAR = (
    "pymupdf4llm", "onnxruntime", "pymupdf_layout",
    "libavcodec", "libavformat", "libavutil", "libswscale", "libswresample", "libpostproc",
    "libx264", "libx265", "librubberband", "libvidstab", "opencv_videoio_ffmpeg", "avcodec-", "avformat-",
)


def paket_icerigini_denetle(kok: Path) -> None:
    """Paketlenmiş motor klasöründe yasak dosya ya da klasör olmadığını doğrular (NOTICE.md, T4)."""
    for yol in SILINECEK:
        hedef = kok / "_internal" / yol
        if hedef.exists():
            shutil.rmtree(hedef)
    bulunan = sorted(
        str(p.relative_to(kok))
        for p in kok.rglob("*")
        if any(parca in p.name.lower() for parca in YASAK_PARCALAR)
    )
    if bulunan:
        raise SystemExit("Pakette olmaması gereken dosyalar var:\n  " + "\n  ".join(bulunan[:40]))


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
            # Ajan komutunun ortak işlevleri ve yerel MCP sunucusu (`bulutbelge-engine mcp`) da ilk kullanımda yüklenir.
            "--hidden-import", "bulutbelge_engine.ajan",
            "--hidden-import", "bulutbelge_engine.mcp",
            "--hidden-import", "lxml.etree",
            # Yüz tespiti modeli (haarcascade xml) OpenCV paketinin veri dosyasıdır.
            "--collect-data", "cv2",
            # OCR dil dosyaları exe'nin içine gömülür (çalışırken _MEIPASS/tessdata).
            "--add-data", f"{tessdata}{os.pathsep}tessdata",
            # Ajan kılavuzu (`bulutbelge-engine kilavuz`) paketin içinde gelir.
            "--add-data", f"{ENGINE_DIR / 'bulutbelge_engine' / 'kilavuz.md'}{os.pathsep}bulutbelge_engine",
            # Claude Code becerisi (`bulutbelge-engine kilavuz --skill`).
            "--add-data", f"{ENGINE_DIR / 'bulutbelge_engine' / 'skill' / 'SKILL.md'}{os.pathsep}bulutbelge_engine/skill",
            str(ENGINE_DIR / "run_engine.py"),
        ],
        check=True,
        cwd=ENGINE_DIR,
    )
    paket_icerigini_denetle(work / "dist" / "bulutbelge-engine")
    ext = ".exe" if sys.platform == "win32" else ""
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = BIN_DIR / "engine"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(work / "dist" / "bulutbelge-engine", dest)
    print(f"Motor paketlendi: {dest / ('bulutbelge-engine' + ext)}")


if __name__ == "__main__":
    main()
