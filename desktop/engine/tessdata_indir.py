"""OCR dil dosyalarını indirir (geliştirme ortamı ve paketleme için bir kez).

Kullanım: engine/.venv içindeki Python ile `python tessdata_indir.py`

Dosyalar `desktop/engine/tessdata/` altına iner ve repoya konmaz (.gitignore).
Kaynak: github.com/tesseract-ocr/tessdata_fast (Apache 2.0). Bütünlük için
SHA-256 özetleri aşağıda sabitlenmiştir; uymayan dosya kaydedilmez.
"""

import hashlib
import sys
import urllib.request
from pathlib import Path

BASE = "https://github.com/tesseract-ocr/tessdata_fast/raw/main/"
FILES = {
    "tur.traineddata": "7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7",
    "eng.traineddata": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2",
}
DEST = Path(__file__).resolve().parent / "tessdata"


def main() -> int:
    DEST.mkdir(exist_ok=True)
    for name, sha in FILES.items():
        path = DEST / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            print(f"{name}: zaten var")
            continue
        print(f"{name}: indiriliyor…")
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- sabit https adresi, özet doğrulanır
        with urllib.request.urlopen(BASE + name, timeout=120) as resp:
            data = resp.read()
        if hashlib.sha256(data).hexdigest() != sha:
            print(f"{name}: özet uyuşmadı, kaydedilmedi", file=sys.stderr)
            return 1
        path.write_bytes(data)
        print(f"{name}: tamam ({len(data) // 1024} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
