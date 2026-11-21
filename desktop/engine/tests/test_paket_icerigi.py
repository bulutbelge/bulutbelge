"""Paketleme sonrası içerik denetimi (build.py): yasak dosyalar derlemeyi durdurur, düzen modülü silinir.

Yalnızca sahte dosya adları; gerçek paketleme yapılmaz.
"""

import importlib.util
from pathlib import Path

import pytest

_BUILD = Path(__file__).resolve().parents[1] / "build.py"
_spec = importlib.util.spec_from_file_location("bb_build", _BUILD)
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def _paket(kok: Path, dosyalar: list[str]) -> Path:
    for ad in dosyalar:
        yol = kok / ad
        yol.parent.mkdir(parents=True, exist_ok=True)
        yol.write_bytes(b"sahte")
    return kok


def test_temiz_paket_gecer_ve_duzen_modulu_silinir(tmp_path):
    kok = _paket(tmp_path, [
        "_internal/cv2/cv2.abi3.so",
        "_internal/pymupdf/_mupdf.so",
        "_internal/pymupdf/layout/onnx/model.onnx",
        "_internal/pymupdf/mupdf-devel/include/fitz.h",
    ])
    build.paket_icerigini_denetle(kok)
    assert not (kok / "_internal/pymupdf/layout").exists()
    assert not (kok / "_internal/pymupdf/mupdf-devel").exists()
    assert (kok / "_internal/cv2/cv2.abi3.so").exists()


@pytest.mark.parametrize("yasak", [
    "_internal/cv2/.dylibs/libx264.164.dylib",
    "_internal/cv2/.dylibs/libavcodec.61.19.101.dylib",
    "_internal/cv2/opencv_videoio_ffmpeg4140_64.dll",
    "_internal/opencv_python_headless.libs/libavformat-1a2b3c.so.61",
    "_internal/onnxruntime/capi/onnxruntime.so",
    "_internal/pymupdf4llm/__init__.py",
])
def test_yasak_dosya_derlemeyi_durdurur(tmp_path, yasak):
    kok = _paket(tmp_path, ["_internal/cv2/cv2.abi3.so", yasak])
    with pytest.raises(SystemExit) as hata:
        build.paket_icerigini_denetle(kok)
    assert Path(yasak).name in str(hata.value) or Path(yasak).parent.name in str(hata.value)
