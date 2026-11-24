"""Resmî MCP kaydı için `server.json`'u bir sürümün MCPB paketlerinden doldurur.

Kökteki `server.json` şablondur: ad, başlık, açıklama, depo ve site elle yazılır; `version` ve `packages`
(her platform için bir MCPB: indirme adresi ve SHA-256) bu betikle, GitHub Release'teki dosyalardan
yazılır. Kayıt (registry.modelcontextprotocol.io) MCPB paketinin GitHub Release dosyası olmasını, adresinde
"mcp" geçmesini ve `fileSha256` bulunmasını şart koşar; özeti doğrulamaz, istemci kurmadan önce doğrular.
Bu yüzden özet elle yazılmaz, dosyanın kendisinden hesaplanır ve varsa SHA256SUMS ile karşılaştırılır.

Kullanım (GitHub iş akışı mcp-kayit.yml):
  python desktop/scripts/mcp_server_json.py --surum 0.1.2 --depo bulutbelge/bulutbelge \
      --dosyalar indirilen/ [--sha256sums indirilen/SHA256SUMS] [--sablon server.json] [--cikti server.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
SEMA = "https://static.modelcontextprotocol.io/schemas/2025-12-11/server.schema.json"
AD = "io.github.bulutbelge/bulutbelge"
PLATFORMLAR = ("macos-arm64", "windows-x64", "linux-x64")
SURUM = re.compile(r"\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?")


class SunucuJsonHatasi(Exception):
    pass


def sha256(yol: Path) -> str:
    h = hashlib.sha256()
    with open(yol, "rb") as f:
        while parca := f.read(1 << 20):
            h.update(parca)
    return h.hexdigest()


def sumlari_oku(yol: Path) -> dict[str, str]:
    out = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        if satir.strip():
            ozet, ad = satir.split(maxsplit=1)
            out[ad.lstrip("*")] = ozet.lower()
    return out


def paketler(surum: str, depo: str, klasor: Path, sumlar: dict[str, str] | None) -> list[dict]:
    out = []
    for platform in PLATFORMLAR:
        ad = f"bulutbelge-mcp-{surum}-{platform}.mcpb"
        yol = klasor / ad
        if not yol.is_file():
            raise SunucuJsonHatasi(f"MCPB paketi yok: {ad}")
        ozet = sha256(yol)
        if sumlar is not None and sumlar.get(ad) != ozet:
            raise SunucuJsonHatasi(f"SHA256SUMS ile uyuşmuyor: {ad}")
        out.append({
            "registryType": "mcpb",
            "identifier": f"https://github.com/{depo}/releases/download/v{surum}/{ad}",
            "version": surum,
            "fileSha256": ozet,
            "transport": {"type": "stdio"},
        })
    return out


def denetle(veri: dict) -> None:
    """Kaydın reddedeceği durumları yayından önce yakalar (şema 2025-12-11 ve kayıt doğrulayıcısı)."""
    if veri.get("$schema") != SEMA:
        raise SunucuJsonHatasi(f"$schema {SEMA} olmalı")
    if veri.get("name") != AD:
        raise SunucuJsonHatasi(f"name {AD} olmalı")
    if not 1 <= len(veri.get("description") or "") <= 100:
        raise SunucuJsonHatasi("description 1-100 karakter olmalı")
    if not SURUM.fullmatch(veri.get("version") or ""):
        raise SunucuJsonHatasi("version sabit bir anlamsal sürüm olmalı")
    if not veri.get("packages"):
        raise SunucuJsonHatasi("packages boş")
    for p in veri["packages"]:
        kimlik = p.get("identifier") or ""
        if p.get("registryType") != "mcpb" or p.get("transport") != {"type": "stdio"}:
            raise SunucuJsonHatasi(f"Paket mcpb/stdio olmalı: {kimlik}")
        if not re.fullmatch(r"https://github\.com/[^/]+/[^/]+/releases/download/[^/]+/[^/]+", kimlik) or "mcp" not in kimlik.lower():
            raise SunucuJsonHatasi(f"MCPB adresi GitHub Release dosyası olmalı ve 'mcp' içermeli: {kimlik}")
        if "registryBaseUrl" in p:
            raise SunucuJsonHatasi("MCPB paketinde registryBaseUrl olmaz")
        if not re.fullmatch(r"[0-9a-f]{64}", p.get("fileSha256") or "") or set(p["fileSha256"]) == {"0"}:
            raise SunucuJsonHatasi(f"fileSha256 gerçek bir SHA-256 olmalı: {kimlik}")
        if f"/v{veri['version']}/" not in kimlik:
            raise SunucuJsonHatasi(f"Paket adresi sürümle uyuşmuyor: {kimlik}")


def uret(sablon: dict, surum: str, depo: str, klasor: Path, sumlar: dict[str, str] | None) -> dict:
    veri = {**sablon, "version": surum, "packages": paketler(surum, depo, klasor, sumlar)}
    denetle(veri)
    return veri


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="server.json'u bir sürümün MCPB paketlerinden doldurur")
    ap.add_argument("--surum", required=True, help="ör. 0.1.2 (başında v olmadan)")
    ap.add_argument("--depo", default="bulutbelge/bulutbelge", help="GitHub sahip/depo")
    ap.add_argument("--dosyalar", required=True, type=Path, help="Release'ten indirilen .mcpb dosyalarının klasörü")
    ap.add_argument("--sha256sums", type=Path, help="Release'teki SHA256SUMS (verilirse karşılaştırılır)")
    ap.add_argument("--sablon", type=Path, default=KOK / "server.json")
    ap.add_argument("--cikti", type=Path, default=KOK / "server.json")
    a = ap.parse_args(argv)
    try:
        sablon = json.loads(a.sablon.read_text(encoding="utf-8"))
        sumlar = sumlari_oku(a.sha256sums) if a.sha256sums else None
        veri = uret(sablon, a.surum.removeprefix("v"), a.depo, a.dosyalar, sumlar)
    except (SunucuJsonHatasi, OSError, ValueError) as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    a.cikti.write_text(json.dumps(veri, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"server.json yazıldı: {a.cikti} ({len(veri['packages'])} paket, sürüm {veri['version']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
