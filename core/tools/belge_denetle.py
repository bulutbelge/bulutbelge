"""pre-push belge denetimi (TAKIP D.4).

Kullanım: python core/tools/belge_denetle.py <aralık>
- Kod değişmiş, belge değişmemişse UYARI yazar (push'u durdurmaz).
- Commit mesajlarında "belge: gerek yok" varsa uyarmaz.
- belge_uret.py çıktıları eskiyse 1 döner (push durur).
"""
import subprocess
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
KOD_ONEKLERI = ("server/bulutbelge_server/", "web/src/", "desktop/src/", "desktop/engine/")
URETIM_ONEKLERI = ("core/", "server/")
MUAFIYET = "belge: gerek yok"


def _git(*args: str) -> str:
    sonuc = subprocess.run(["git", *args], cwd=KOK, capture_output=True, text=True)
    return sonuc.stdout


def _belge_mi(yol: str) -> bool:
    if yol.startswith("docs/"):
        return yol != "docs/TAKIP.md" and not yol.startswith("docs/kararlar/")
    return yol.endswith("README.md")


def belge_uyarisi_gerekli(dosyalar: list[str], mesajlar: str) -> bool:
    if MUAFIYET in mesajlar.lower():
        return False
    if not any(d.startswith(KOD_ONEKLERI) for d in dosyalar):
        return False
    return not any(_belge_mi(d) for d in dosyalar)


def uretim_denetimi_gerekli(dosyalar: list[str]) -> bool:
    return any(d.startswith(URETIM_ONEKLERI) for d in dosyalar)


def uretilen_eski_mi() -> bool:
    """belge_uret.py --denetle başarısızsa eski sayılır; çalışamıyorsa uyarır, durdurmaz."""
    try:
        sonuc = subprocess.run(
            [sys.executable, str(KOK / "core/tools/belge_uret.py"), "--denetle"],
            cwd=KOK, capture_output=True, text=True,
        )
    except OSError as e:
        print(f"UYARI: belge_uret.py çalıştırılamadı ({e}); üretilen belgeler denetlenmedi.")
        return False
    if sonuc.returncode == 0:
        return False
    if "ModuleNotFoundError" in sonuc.stderr or "ImportError" in sonuc.stderr:
        print("UYARI: belge_uret.py bağımlılık eksiği nedeniyle çalışmadı; üretilen belgeler denetlenmedi.")
        return False
    print(sonuc.stdout + sonuc.stderr)
    return True


def main(argv: list[str]) -> int:
    aralik = argv[0]
    dosyalar = [d for d in _git("diff", "--name-only", aralik).splitlines() if d]
    if not dosyalar:
        return 0
    mesajlar = _git("log", "--format=%B", aralik)
    if belge_uyarisi_gerekli(dosyalar, mesajlar):
        print("UYARI: Kod değişti ama ilgili belge (docs/, README) değişmedi.")
        print("Belgeyi güncelleyin; gerek yoksa commit mesajına 'belge: gerek yok' yazın.")
    if uretim_denetimi_gerekli(dosyalar) and uretilen_eski_mi():
        print("HATA: Üretilen belgeler eski. 'python core/tools/belge_uret.py' çalıştırıp commit edin.")
        print("Atlamak için (bilinçli): SKIP_BELGE=1 git push")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
