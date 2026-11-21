"""OpenCV'yi (opencv-python-headless) FFmpeg'siz derleyip motor ortamına kurar.

Neden: PyPI'daki hazır tekerlek, OpenCV'nin video modülü için FFmpeg'i ve (macOS'ta) GPL lisanslı
kodekleri (x264, x265 vb.) taşıyor. Motor video işlemez; yüz, plaka, QR/barkod, kaşe ve MRZ tespiti
için yalnızca görüntü işleme modülleri gerekir. FFmpeg'siz derleme lisansı sadeleştirir ve paketi
küçültür (macOS'ta `cv2` 119 MB'tan 44 MB'a). Karar: docs/kararlar/2026-11-21-sunucu-acik-kaynak-ve-opencv.md

Güvence: kaynak arşivi (sdist) PyPI'dan indirilir ve SHA-256 özeti `requirements.lock` içindeki
özetlerden biriyle eşleşmezse derleme yapılmaz. Derlenen tekerlek önbellek klasöründe tutulur;
aynı sürüm ve aynı derleme ayarıyla ikinci kez derlenmez.

Kullanım (motor sanal ortamındaki Python ile, kilit kurulduktan sonra):
    python desktop/engine/opencv_derle.py [--onbellek KLASOR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

PAKET = "opencv-python-headless"
KILIT = Path(__file__).resolve().parent / "requirements.lock"
CMAKE_ARGS = " ".join(
    (
        "-DWITH_FFMPEG=OFF",
        "-DWITH_GSTREAMER=OFF",
        # Intel IPP (x86) açık kaynak değil; ITT izleme gereksiz. İkisi de yalnızca hız içindir.
        "-DWITH_IPP=OFF",
        "-DWITH_ITT=OFF",
        "-DBUILD_TESTS=OFF",
        "-DBUILD_PERF_TESTS=OFF",
        "-DBUILD_EXAMPLES=OFF",
        "-DBUILD_opencv_java=OFF",
        "-DBUILD_DOCS=OFF",
    )
)


def kilitten_oku() -> tuple[str, set[str]]:
    """Kilit dosyasındaki sürüm ve izin verilen SHA-256 özetleri."""
    metin = KILIT.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(PAKET)}==(\S+)((?:\s*\\\n\s+--hash=sha256:[0-9a-f]{{64}})+)", metin, re.M)
    if not m:
        raise SystemExit(f"{PAKET} kilit dosyasında bulunamadı: {KILIT}")
    return m.group(1), set(re.findall(r"sha256:([0-9a-f]{64})", m.group(2)))


def kaynagi_indir(surum: str, izinli: set[str], klasor: Path) -> Path:
    with urllib.request.urlopen(f"https://pypi.org/pypi/{PAKET}/{surum}/json", timeout=60) as yanit:
        bilgi = json.load(yanit)
    sdist = next((u for u in bilgi["urls"] if u["packagetype"] == "sdist"), None)
    if sdist is None:
        raise SystemExit(f"{PAKET} {surum} için kaynak arşivi yok")
    if sdist["digests"]["sha256"] not in izinli:
        raise SystemExit("PyPI'daki kaynak arşivinin özeti kilit dosyasında yok; derleme durduruldu")
    hedef = klasor / sdist["filename"]
    if not hedef.is_file():
        with urllib.request.urlopen(sdist["url"], timeout=300) as yanit:
            hedef.write_bytes(yanit.read())
    ozet = hashlib.sha256(hedef.read_bytes()).hexdigest()
    if ozet not in izinli:
        hedef.unlink(missing_ok=True)
        raise SystemExit(f"İndirilen arşivin özeti ({ozet}) kilit dosyasıyla uyuşmuyor; derleme durduruldu")
    return hedef


def ffmpegsiz_mi() -> bool:
    bilgi = subprocess.run(
        [sys.executable, "-c", "import cv2; print(cv2.getBuildInformation())"],
        capture_output=True, text=True, check=True,
    ).stdout
    return not re.search(r"FFMPEG:\s+YES", bilgi)


# opencv-python'ın setup.py dosyası Windows'ta FFmpeg DLL'ini zorunlu paket dosyası sayar; FFmpeg'siz
# derlemede dosya olmadığı için paketleme "Not found" ile durur. Bu kural kaldırılır (diğer platformlarda
# zaten boştur). Yama tutmazsa (ör. yeni sürümde satır değiştiyse) derleme bilerek durur.
FFMPEG_DLL_KURALI = '[r"bin/opencv_videoio_ffmpeg\\d{4}%s\\.dll" % ("_64" if is64 else "")]'


def kaynagi_ac_ve_yamala(arsiv: Path, hedef: Path) -> Path:
    """Özeti doğrulanmış arşivi açar, setup.py'deki FFmpeg DLL kuralını kaldırır, kaynak klasörünü döndürür."""
    import tarfile

    if hedef.exists():
        shutil.rmtree(hedef)
    hedef.mkdir(parents=True)
    with tarfile.open(arsiv) as tar:
        tar.extractall(hedef, filter="data")
    kok = next(p for p in hedef.iterdir() if p.is_dir())
    setup = kok / "setup.py"
    metin = setup.read_text(encoding="utf-8")
    if metin.count(FFMPEG_DLL_KURALI) != 1:
        raise SystemExit("setup.py'de FFmpeg DLL kuralı beklenen biçimde bulunamadı; opencv_derle.py güncellenmeli")
    setup.write_text(metin.replace(FFMPEG_DLL_KURALI, "[]"), encoding="utf-8")
    return kok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--onbellek", type=Path, default=Path.home() / ".cache" / "bb-opencv")
    args = ap.parse_args()

    surum, izinli = kilitten_oku()
    ayar_ozeti = hashlib.sha256(CMAKE_ARGS.encode()).hexdigest()[:12]
    klasor = args.onbellek / f"{surum}-{ayar_ozeti}"
    klasor.mkdir(parents=True, exist_ok=True)

    tekerlek = next(klasor.glob("*.whl"), None)
    if tekerlek is None:
        arsiv = kaynagi_indir(surum, izinli, klasor)
        kaynak = kaynagi_ac_ve_yamala(arsiv, klasor / "kaynak")
        ortam = dict(os.environ, ENABLE_HEADLESS="1", CMAKE_ARGS=CMAKE_ARGS)
        if sys.platform == "darwin":
            ortam.setdefault("MACOSX_DEPLOYMENT_TARGET", "13.0")
        print(f"{PAKET} {surum} kaynaktan derleniyor (FFmpeg'siz); bu birkaç on dakika sürebilir", flush=True)
        subprocess.run(
            [sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir", str(kaynak), "-w", str(klasor)],
            env=ortam, check=True,
        )
        shutil.rmtree(kaynak.parent, ignore_errors=True)
        tekerlek = next(klasor.glob("*.whl"))
    else:
        print(f"Önbellekteki tekerlek kullanılıyor: {tekerlek.name}", flush=True)

    subprocess.run([sys.executable, "-m", "pip", "install", "--no-deps", "--force-reinstall", str(tekerlek)], check=True)
    if not ffmpegsiz_mi():
        raise SystemExit("Kurulan OpenCV FFmpeg ile derlenmiş görünüyor; durduruldu")
    print(f"OpenCV {surum} FFmpeg'siz kuruldu", flush=True)


if __name__ == "__main__":
    main()
