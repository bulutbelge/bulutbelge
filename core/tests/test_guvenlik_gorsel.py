"""Güvenlik taraması F10/F21: çok kareli görselde kare sayısı ve toplam piksel sınırı, kareler tek tek.

Tüm görseller testte üretilen sahte, küçük görsellerdir.
"""

from __future__ import annotations

import inspect
import time
import types
import zipfile

import pytest
from PIL import Image

from bulutbelge_core import image as image_mod
from bulutbelge_core.archive import scan_archive
from bulutbelge_core.image import ImageError, image_bytes_to_doc, image_to_doc
from bulutbelge_core.pdf import PdfError, scan_pdf
from bulutbelge_core.rules import Rules


def _tiff(path, frames: int, size=(64, 64)):
    imgs = [Image.new("RGB", size, (i % 255, 120, 200)) for i in range(frames)]
    imgs[0].save(path, "TIFF", save_all=True, append_images=imgs[1:], compression="tiff_deflate")
    return path


@pytest.fixture
def decoded(monkeypatch):
    """Çözülen kare sayısını sayar (her kare `exif_transpose(img.copy())` ile çözülür)."""
    calls = {"n": 0}
    real = image_mod.ImageOps.exif_transpose

    def counting(img, *a, **kw):
        calls["n"] += 1
        return real(img, *a, **kw)

    # Yalnızca image.py'nin çağrıları sayılır (Pillow TIFF yüklerken kendisi de çağırır).
    monkeypatch.setattr(image_mod, "ImageOps", types.SimpleNamespace(exif_transpose=counting))
    return calls


@pytest.fixture(autouse=True)
def _restore_pillow_limit(monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", Image.MAX_IMAGE_PIXELS)


def test_too_many_frames_rejected_before_decoding(tmp_path, decoded):
    src = _tiff(tmp_path / "cok.tif", image_mod.MAX_FRAMES + 1, size=(1, 1))
    t0 = time.perf_counter()
    with pytest.raises(ImageError, match="kare"):
        image_to_doc(src)
    assert decoded["n"] == 0 and time.perf_counter() - t0 < 10


def test_total_pixel_limit_stops_early(tmp_path, decoded, monkeypatch):
    monkeypatch.setattr(image_mod, "MAX_TOTAL_PIXELS", 3 * 64 * 64)
    src = _tiff(tmp_path / "toplam.tif", 6)
    with pytest.raises(ImageError, match="toplam"):
        image_to_doc(src)
    assert decoded["n"] == 3  # sınırı aşan kare çözülmeden durur


def test_single_frame_size_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(image_mod, "MAX_PIXELS", 1000)
    src = _tiff(tmp_path / "iki.tif", 2, size=(40, 40))  # 1600 px <= 2 x 1000: kabul
    assert image_to_doc(src).page_count == 2
    src = _tiff(tmp_path / "buyuk.tif", 2, size=(50, 50))  # 2500 px > 2 x 1000
    with pytest.raises(ImageError):
        image_to_doc(src)


def test_frames_are_decoded_one_at_a_time(tmp_path):
    with Image.open(_tiff(tmp_path / "a.tif", 3)) as img:
        assert inspect.isgenerator(image_mod._iter_frames(img))


def test_limits_apply_inside_zip(tmp_path, monkeypatch):
    monkeypatch.setattr(image_mod, "MAX_TOTAL_PIXELS", 2 * 64 * 64)
    tif = _tiff(tmp_path / "ek.tif", 5)
    arsiv = tmp_path / "arsiv.zip"
    with zipfile.ZipFile(arsiv, "w") as z:
        z.write(tif, "klasor/ek.tif")
    with pytest.raises(PdfError, match="toplam"):
        scan_archive(arsiv, Rules.default())


def test_limits_apply_to_image_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr(image_mod, "MAX_FRAMES", 2)
    data = _tiff(tmp_path / "b.tif", 3).read_bytes()
    with pytest.raises(ImageError, match="kare"):
        image_bytes_to_doc(data)
    with pytest.raises(ImageError, match="Görsel baytları açılamadı"):
        image_bytes_to_doc(b"gorsel degil")


def test_legit_multipage_and_single_images_unchanged(tmp_path):
    doc = image_to_doc(_tiff(tmp_path / "uc.tif", 3, size=(120, 80)))
    assert doc.page_count == 3 and (doc[0].rect.width, doc[0].rect.height) == (120, 80)
    png = tmp_path / "tek.png"
    Image.new("RGBA", (30, 20), (0, 0, 0, 0)).save(png)
    one = image_to_doc(png)
    assert one.page_count == 1 and (one[0].rect.width, one[0].rect.height) == (30, 20)
    assert scan_pdf(tmp_path / "uc.tif", Rules.default()).pages == 3
