"""BulutBelge masaüstü motoru: Tauri kabuğunun yan süreci.

Kabukla stdin/stdout üzerinden satır başına bir JSON mesajla konuşur.
Tespit ve maskeleme işi `core/` kütüphanesine bırakılır; bu paket yalnızca
protokolü ve komut yönlendirmesini taşır.
"""

__version__ = "0.1.2"

import os
import sys
from pathlib import Path


def _tessdata() -> Path:
    # Paketlenmiş motorda dil dosyaları PyInstaller'ın açtığı klasördedir;
    # geliştirmede `desktop/engine/tessdata` (tessdata_indir.py indirir).
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[1]))
    dest = base / "tessdata"
    if not getattr(sys, "_MEIPASS", None) and not (dest / "tur.traineddata").is_file():
        try:
            import subprocess
            script = base / "tessdata_indir.py"
            if script.is_file():
                subprocess.run([sys.executable, str(script)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=90)
        except Exception:
            pass
    return dest


# OCR dil dosyalarının yeri çekirdeğe ortam değişkeniyle bildirilir.
os.environ.setdefault("BULUTBELGE_TESSDATA", str(_tessdata()))
