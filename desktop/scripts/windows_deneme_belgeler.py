"""Windows denemesi iş akışı için sahte belgeler üretir ve maskeli çıktıyı denetler.

Gerçek kişi ya da kurum yoktur: yüz kodla çizilir (core/tests/fake_face.py), numaralar sahtedir.

    python desktop/scripts/windows_deneme_belgeler.py uret <klasör>
    python desktop/scripts/windows_deneme_belgeler.py denetle <maskeli-pdf>
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(KOK / "core" / "tests"))

BASLIK = "SAHTE BASVURU FORMU"
ACIKLAMA = "Bu belge tamamen sahtedir ve gercek kisi icermez."

FATURA = (
    "ORNEK TICARET A.S.\n"
    "Tel: 0850 000 00 00\n"
    "Web Sitesi: https://ornek-ticaret.com.tr\n"
    "MERSİS No: 0000000000000001\n"
    "Ticaret Sicil No: 00001\n"
    "SAYIN DENEME KISI\n"
    "Tel: 905000000000\n"
)


def uret(klasor: Path) -> None:
    import pymupdf
    from fake_face import draw_face

    klasor.mkdir(parents=True, exist_ok=True)
    (klasor / "sahte-fatura.txt").write_text(FATURA, encoding="utf-8")

    # Deneme 6, D1: yüze sıkı kırpılmış fotoğraf metnin hemen altında.
    buf = io.BytesIO()
    draw_face(200).crop((90, 40, 310, 330)).save(buf, "PNG")
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), BASLIK, fontsize=14)
    page.insert_text((72, 95), ACIKLAMA, fontsize=10)
    page.insert_image(pymupdf.Rect(72, 99, 182, 244), stream=buf.getvalue())
    doc.save(klasor / "sahte-yuz.pdf")
    print("üretildi:", ", ".join(p.name for p in sorted(klasor.iterdir())))


def denetle(maskeli: Path) -> int:
    import pymupdf

    metin = pymupdf.open(maskeli)[0].get_text()
    tamam = BASLIK in metin and ACIKLAMA in metin
    print(f"başlık ve açıklama maskeli kopyada tam: {tamam}")
    return 0 if tamam else 1


if __name__ == "__main__":
    komut, yol = sys.argv[1], Path(sys.argv[2])
    if komut == "uret":
        uret(yol)
    else:
        sys.exit(denetle(yol))
