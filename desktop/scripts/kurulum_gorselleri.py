"""Windows kurulum sihirbazlarının "bb" görsellerini üretir (NSIS ve WiX/MSI).

Kaynak: uygulama simgesi (`src-tauri/icons/icon.png`) ve site logosu (`site/logo.svg`).
Çıktılar depoya girer; simge ya da logo değişince yeniden çalıştırılır:

    desktop/engine/.venv/bin/python desktop/scripts/kurulum_gorselleri.py

Boyutlar Tauri'nin belgelediği değerlerdir: NSIS başlık 150x57, NSIS yan görsel 164x314,
WiX şerit 493x58, WiX karşılama/bitiş 493x312 (sol 164 px görsel, sağı metin alanı, beyaz kalır).
"""

from __future__ import annotations

import io
from pathlib import Path

import pymupdf
from PIL import Image

KOK = Path(__file__).resolve().parents[2]
SIMGE = KOK / "desktop/src-tauri/icons/icon.png"
LOGO = KOK / "site/logo.svg"
NSIS = KOK / "desktop/src-tauri/windows/nsis"
WIX = KOK / "desktop/src-tauri/windows/wix"

BEYAZ = (255, 255, 255)
ACIK = (238, 241, 246)  # logonun mavi-grisinin çok açık tonu


def _logo(genislik: int) -> Image.Image:
    sayfa = pymupdf.open(LOGO)[0]
    olcek = genislik / sayfa.rect.width * 2  # iki kat çiz, sonra küçült (kenarlar yumuşak)
    pix = sayfa.get_pixmap(matrix=pymupdf.Matrix(olcek, olcek), alpha=True)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    return img.resize((genislik, round(img.height * genislik / img.width)), Image.LANCZOS)


def _simge(kenar: int) -> Image.Image:
    return Image.open(SIMGE).convert("RGBA").resize((kenar, kenar), Image.LANCZOS)


def _yapistir(zemin: Image.Image, parca: Image.Image, x: int, y: int) -> None:
    zemin.paste(parca, (x, y), parca)


def _yan_panel(genislik: int, yukseklik: int) -> Image.Image:
    panel = Image.new("RGB", (genislik, yukseklik), ACIK)
    simge = _simge(96)
    _yapistir(panel, simge, (genislik - simge.width) // 2, 56)
    logo = _logo(genislik - 28)
    _yapistir(panel, logo, (genislik - logo.width) // 2, 56 + simge.height + 22)
    return panel


def _kaydet(img: Image.Image, yol: Path) -> None:
    yol.parent.mkdir(parents=True, exist_ok=True)
    img.convert("RGB").save(yol, format="BMP")  # 24 bit, sıkıştırmasız (NSIS ve WiX ikisi de okur)
    print(f"{yol.relative_to(KOK)} {img.width}x{img.height}")


def main() -> None:
    # NSIS sayfa başlığı: beyaz zeminde logo (başlık metni görselin yanında durur).
    baslik = Image.new("RGB", (150, 57), BEYAZ)
    logo = _logo(132)
    _yapistir(baslik, logo, (150 - logo.width) // 2, (57 - logo.height) // 2)
    _kaydet(baslik, NSIS / "baslik.bmp")

    # NSIS karşılama/bitiş sayfasının sol görseli.
    _kaydet(_yan_panel(164, 314), NSIS / "yan.bmp")

    # WiX şeridi: metin solda yazılır, simge sağda.
    serit = Image.new("RGB", (493, 58), BEYAZ)
    simge = _simge(44)
    _yapistir(serit, simge, 493 - simge.width - 10, (58 - simge.height) // 2)
    _kaydet(serit, WIX / "serit.bmp")

    # WiX karşılama/bitiş: sol 164 px panel, sağ taraf metin için beyaz.
    diyalog = Image.new("RGB", (493, 312), BEYAZ)
    diyalog.paste(_yan_panel(164, 312), (0, 0))
    _kaydet(diyalog, WIX / "diyalog.bmp")


if __name__ == "__main__":
    main()
