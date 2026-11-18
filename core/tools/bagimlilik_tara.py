"""Bağımlılık taraması ve CycloneDX SBOM üretimi (TAKIP 1.88).

Yalnızca standart kütüphane. SBOM kilit dosyalarından ve kurulu Python paketlerinden
üretilir; yalnızca paket adı ve sürümü yazılır. npm audit, cargo audit ve pip-audit
araç kurulu değilse ya da ağ yoksa atlanır.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tomllib
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from urllib.parse import quote

KOK = Path(__file__).resolve().parents[2]


def _bilesen(tur_purl: str, ad: str, surum: str) -> dict:
    return {
        "type": "library",
        "name": ad,
        "version": surum,
        "purl": f"pkg:{tur_purl}/{quote(ad, safe='/')}@{surum}",
    }


def npm_bilesenleri(dizin: Path) -> list[dict]:
    kilit = Path(dizin) / "package-lock.json"
    if not kilit.is_file():
        return []
    veri = json.loads(kilit.read_text(encoding="utf-8"))
    sonuc = {}
    for yol, bilgi in veri.get("packages", {}).items():
        if not yol or "node_modules/" not in yol:
            continue
        ad = yol.rsplit("node_modules/", 1)[1]
        surum = bilgi.get("version")
        if surum:
            sonuc[(ad, surum)] = _bilesen("npm", ad, surum)
    return [sonuc[k] for k in sorted(sonuc)]


def cargo_bilesenleri(dizin: Path) -> list[dict]:
    kilit = Path(dizin) / "Cargo.lock"
    if not kilit.is_file():
        return []
    veri = tomllib.loads(kilit.read_text(encoding="utf-8"))
    return [
        _bilesen("cargo", p["name"], p["version"])
        for p in veri.get("package", [])
        if p.get("source")  # kaynağı olmayanlar yerel kasalar
    ]


def python_bilesenleri() -> list[dict]:
    sonuc = {}
    for d in metadata.distributions():
        ad = d.metadata["Name"]
        if not ad or ad.lower().startswith("bulutbelge"):
            continue
        sonuc[ad.lower()] = _bilesen("pypi", ad.lower(), d.version)
    return [sonuc[k] for k in sorted(sonuc)]


def sbom_yaz(cikti: Path, ad: str, bilesenler: list[dict]) -> Path:
    belge = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {"timestamp": datetime.now(timezone.utc).isoformat(),
                     "component": {"type": "application", "name": ad}},
        "components": bilesenler,
    }
    yol = Path(cikti) / f"sbom-{ad}.cdx.json"
    yol.write_text(json.dumps(belge, ensure_ascii=False, indent=2), encoding="utf-8")
    return yol


def tara(ad: str, komut: list[str], cwd: Path):
    """Taramayı çalıştırır. Araç yoksa None (atlandı), aksi halde çıkış kodu."""
    if shutil.which(komut[0]) is None:
        print(f"[{ad}] atlandı: {komut[0]} kurulu değil")
        return None
    try:
        s = subprocess.run(komut, cwd=cwd, capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        print(f"[{ad}] atlandı: çalıştırılamadı ({type(e).__name__})")
        return None
    print(f"[{ad}] çıkış kodu {s.returncode}")
    if s.returncode:
        print((s.stdout + s.stderr)[-2000:])
    return s.returncode


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Bağımlılık taraması ve SBOM")
    p.add_argument("--cikti", default=str(KOK / "sbom"), help="SBOM dizini")
    p.add_argument("--sadece-sbom", action="store_true")
    p.add_argument("--ag-yok", action="store_true")
    a = p.parse_args(argv)
    ag_yok = a.ag_yok or os.environ.get("BULUTBELGE_AG_YOK") == "1"

    cikti = Path(a.cikti)
    cikti.mkdir(parents=True, exist_ok=True)
    sbom_yaz(cikti, "npm-desktop", npm_bilesenleri(KOK / "desktop"))
    sbom_yaz(cikti, "npm-web", npm_bilesenleri(KOK / "web"))
    sbom_yaz(cikti, "cargo-masaustu", cargo_bilesenleri(KOK / "desktop" / "src-tauri"))
    sbom_yaz(cikti, "python", python_bilesenleri())
    print(f"SBOM yazıldı: {cikti}")

    if a.sadece_sbom:
        return 0
    if ag_yok:
        print("ağ yok: bağımlılık taramaları atlandı")
        return 0
    sonuclar = [
        tara("npm-desktop", ["npm", "audit", "--audit-level=high"], KOK / "desktop"),
        tara("npm-web", ["npm", "audit", "--audit-level=high"], KOK / "web"),
        tara("cargo", ["cargo", "audit"], KOK / "desktop" / "src-tauri"),
        tara("pip", ["pip-audit"], KOK),
    ]
    return 1 if any(s for s in sonuclar if s) else 0


if __name__ == "__main__":
    sys.exit(main())
