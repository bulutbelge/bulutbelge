"""Bilgi taşımayan "bulanık" dolgu.

Orijinal metni ya da görseli bulanıklaştırmak ya da pikselleştirmek güvenli
değildir: Depix ve Unredacter gibi araçlar bu tür örtülerden metni geri
okuyabilir. Bu yüzden "Bulanık" yöntemi önce değeri gerçekten siler, sonra
yerine yalnızca rastgele üretilmiş, buzlu cam görünümlü bir görsel koyar.
Görsel orijinal içerikten hiçbir piksel kullanmaz; yalnızca kutunun boyutu
(diğer yöntemlerde de görünen) ortaktır.
"""

from __future__ import annotations

import io
import secrets

from PIL import Image, ImageDraw, ImageFilter

_SCALE = 4  # pt başına piksel
_MAX_PX = 1600


def blur_png(width_pt: float, height_pt: float, kind: str = "metin") -> bytes:
    w = max(8, min(_MAX_PX, int(width_pt * _SCALE)))
    h = max(8, min(_MAX_PX, int(height_pt * _SCALE)))
    rng = secrets.SystemRandom()

    img = Image.new("RGBA", (w, h), (236, 236, 238, 255))
    draw = ImageDraw.Draw(img)

    if kind == "metin":
        # Sözcük benzeri gri lekeler: genişlikleri rastgele, orijinal metinden bağımsız.
        x = rng.uniform(0, h * 0.4)
        while x < w:
            word = rng.uniform(h * 0.8, h * 3.2)
            shade = rng.randint(120, 165)
            draw.rounded_rectangle(
                (x, h * 0.28, min(w, x + word), h * 0.72), radius=h * 0.2, fill=(shade, shade, shade + 6, 255)
            )
            x += word + rng.uniform(h * 0.3, h * 0.7)
    else:
        # İmza/kaşe: birkaç yumuşak leke.
        for _ in range(rng.randint(4, 7)):
            cx, cy = rng.uniform(0, w), rng.uniform(h * 0.2, h * 0.8)
            rx, ry = rng.uniform(w * 0.1, w * 0.3), rng.uniform(h * 0.15, h * 0.35)
            shade = rng.randint(110, 170)
            draw.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=(shade, shade, shade + 8, 255))

    img = img.filter(ImageFilter.GaussianBlur(radius=max(2.0, h * 0.18)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()
