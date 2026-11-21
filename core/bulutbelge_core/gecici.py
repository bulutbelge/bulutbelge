"""Geçici klasörler: işlenirken kısa süre maskesiz içerik barındırabilirler (arşiv içinden çıkarılan
dosya, e-posta eki, Office içindeki görsel).

Klasör adı ".noindex" ile biter: macOS Spotlight bu adlı klasörleri dizinlemez, bu yüzden maskesiz içerik aranabilir
ya da Quick Look önizlemesine girmez. Klasör yalnızca sahibine açık (0700) açılır ve her durumda silinir.
Bunun dışında hiçbir yerde kalıcı kopya yazılmaz.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

DIZINLEME_EKI = ".noindex"


def klasor_ac(prefix: str) -> Path:
    """Sahibine özel, dizinlenmeyen geçici klasör açar; silmek çağıranın işidir (`gecici_klasor` kullanın)."""
    yol = Path(tempfile.mkdtemp(prefix=prefix, suffix=DIZINLEME_EKI))
    # nosemgrep: python.lang.security.audit.insecure-file-permissions.insecure-file-permissions -- 0o700 yalnızca sahibine açık geçici klasör
    os.chmod(yol, 0o700)
    return yol


@contextmanager
def gecici_klasor(prefix: str) -> Iterator[Path]:
    """Blok bitince (hata olsa da) klasörü içindekilerle siler."""
    yol = klasor_ac(prefix)
    try:
        yield yol
    finally:
        shutil.rmtree(yol, ignore_errors=True)
