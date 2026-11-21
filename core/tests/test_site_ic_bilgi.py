"""Herkese açık site (site/, bulutbelge.com) iç ağ bilgisi içermez (TAKIP D.6, İ.7).

Kalıplar açık kaynak dışa aktarımının yasak listesinden gelir (core/tools/acik_kaynak/yasak.txt). Sunucu
belgeleri iç adres ve güvenlik duvarı ayrıntısı içerdiği için panelin içinde (web/public/yardim) yayımlanır.
"""

import re
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
# Kurumun herkese açık iletişim adresleri sitede bulunabilir (aydınlatma metni, güvenlik bildirimi).
IZINLI_SATIR = re.compile(r"(?i)\b(?:kvkk|info|guvenlik|güvenlik|security|destek)@proteksistem\.com\b")


def _yasak_kaliplar():
    for satir in (KOK / "core/tools/acik_kaynak/yasak.txt").read_text(encoding="utf-8").splitlines():
        if satir.startswith("yasak\t"):
            _d, ad, desen = satir.split("\t", 2)
            yield ad, re.compile(desen, re.IGNORECASE)


def test_herkese_acik_sitede_ic_bilgi_yok():
    bulgular = []
    kaliplar = list(_yasak_kaliplar())
    for yol in sorted((KOK / "site").rglob("*")):
        if not yol.is_file() or yol.suffix.lower() not in {".html", ".md", ".txt", ".json", ".css", ".svg", ".xml", ""}:
            continue
        goreli = yol.relative_to(KOK / "site")
        if goreli.parts[0] == "deploy" or goreli.as_posix() == "README.md":
            continue  # yayında hariç: rsync --exclude deploy --exclude README.md (site/deploy/KURULUM.md)
        for no, satir in enumerate(yol.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            temiz = IZINLI_SATIR.sub("", satir)
            for ad, rx in kaliplar:
                if rx.search(temiz):
                    bulgular.append(f"{yol.relative_to(KOK)}:{no}: {ad}")
    assert not bulgular, "\n".join(bulgular)


def test_herkese_acik_urun_belgesi_uygulamasinda_ic_bilgi_yok():
    """dokuman/apps/urun-dokuman bulutbelge.com için derlenir (API belgesi kurum içidir, taranmaz)."""
    kaliplar = list(_yasak_kaliplar())
    bulgular = []
    for kok in (KOK / "dokuman" / "apps" / "urun-dokuman", KOK / "dokuman" / "pages-hub"):
        for yol in sorted(kok.rglob("*")):
            if not yol.is_file() or {"node_modules", "dist"} & set(yol.parts):
                continue
            if yol.suffix.lower() not in {".ts", ".tsx", ".html", ".md", ".json", ".css", ".svg"}:
                continue
            for no, satir in enumerate(yol.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                temiz = IZINLI_SATIR.sub("", satir)
                bulgular += [f"{yol.relative_to(KOK)}:{no}: {ad}" for ad, rx in kaliplar if rx.search(temiz)]
    assert not bulgular, "\n".join(bulgular)


def test_sunucu_belgeleri_acik_sitede_degil_panelde():
    acik = {p.name for p in (KOK / "site" / "belgeler").glob("*.html")}
    assert not acik & {"sunucu-kurulum.html", "sunucu-isletme.html", "panel.html", "api-rehberi.html", "guvenlik-kvkk.html"}
    assert (KOK / "web" / "public" / "yardim" / "sunucu-kurulum.html").is_file()
