import os
from pathlib import Path

# OCR testleri için masaüstü motorunun indirdiği dil dosyaları (yoksa o testler atlanır).
_TESSDATA = Path(__file__).resolve().parents[2] / "desktop" / "engine" / "tessdata"
if _TESSDATA.is_dir():
    os.environ.setdefault("BULUTBELGE_TESSDATA", str(_TESSDATA))
