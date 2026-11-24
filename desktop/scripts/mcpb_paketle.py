"""Yerel MCP sunucusunu (`bulutbelge-engine mcp`) MCPB paketi (`.mcpb`) olarak paketler.

MCPB (MCP Bundle) bir zip arşividir: kökte `manifest.json`, yanında sunucunun kendisi. Resmî MCP kaydı
(registry.modelcontextprotocol.io) yerel sunucuları yalnızca paket olarak listeler; .dmg/.exe listelenemez,
MCPB kabul edilir. Smithery de yerel sunucu için aynı dosyayı ister. Bkz. docs/kararlar/2026-11-24-mcp-kaydi-mcpb.md

Paket, PyInstaller ile derlenmiş motor klasörünün (desktop/src-tauri/binaries/engine) BİREBİR kopyasıdır:
macOS'ta uygulamayla aynı imzalı (ve uygulamayla birlikte notarize edilmiş) dosyalar girer. Sunucu türü
"binary", giriş komutu `<motor> mcp`. Motor ayar klasörünü (izinler, kural takımları, işlem günlüğü)
kendisi seçmez: masaüstü uygulamasının klasörünü kullanır; uygulama kurulu değilse araçlar
`app_not_installed` hatası verir (ajan.require_app). MCPB yalnızca ajan aracına sunucuyu tanıtır.

Betik yalnızca standart kütüphaneyi kullanır ve motoru ÇALIŞTIRARAK doğrular:
  1. Paketlenecek motor `mcp` ile başlatılır; initialize + tools/list yanıtından sürüm ve araç listesi alınır
     (manifest elle yazılan listeyle kaymasın).
  2. Zip belirlenimli üretilir (sıralı girdiler, SOURCE_DATE_EPOCH zamanı, POSIX izinleri korunur).
  3. Arşiv geçici klasöre açılır ve açılan kopyadaki motor yeniden `mcp` olarak denenir.

Kullanım:
  python desktop/scripts/mcpb_paketle.py --motor desktop/src-tauri/binaries/engine \
      --platform macos-arm64 --cikti cikti [--surum 0.1.2] [--manifest-yaz manifest.json]
Çıktı: cikti/bulutbelge-mcp-<sürüm>-<platform>.mcpb (ad "mcp" içerir: kayıt bunu şart koşar).
"""

from __future__ import annotations

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
SIMGE = KOK / "desktop" / "src-tauri" / "icons" / "icon.png"

# platform adı -> (MCPB compatibility.platforms değeri, motor dosyasının uzantısı)
PLATFORMLAR: dict[str, tuple[str, str]] = {
    "macos-arm64": ("darwin", ""),
    "windows-x64": ("win32", ".exe"),
    "linux-x64": ("linux", ""),
}
MANIFEST_SURUMU = "0.3"  # @anthropic-ai/mcpb 2.1.2 "latest" şeması
MOTOR_ADI = "bulutbelge-engine"
SUNUCU_KLASORU = "server"
ZAMAN_ASIMI = 120  # sn; ilk açılışta (Windows Defender taraması) motor yavaş başlayabilir

ACIKLAMA = "Belgelerdeki kişisel veriyi bilgisayarda bulup gerçekten silen yerel MCP sunucusu (maskeli okuma)."
UZUN_ACIKLAMA = (
    "BulutBelge, belgelerdeki (PDF, Word, Excel, görsel, metin) kişisel verileri kullanıcının bilgisayarında "
    "bulur ve gerçekten siler; görsel örtü değil, gerçek silmedir. Bu MCP sunucusu ajana belgeyi değer göstermeden "
    "taratır (yalnızca sayılar), maskeli metni okutur ve kullanıcı isterse maskeli kopya yazar. Ajana orijinal "
    "değer dönmez. Hiçbir sunucuya bağlanmaz, ağ portu açmaz; yalnızca stdio.\n\n"
    "**Ön koşul:** BulutBelge masaüstü uygulaması kurulu olmalı ve bir kez açılmış olmalı "
    "(https://bulutbelge.com/indir). Sunucu, uygulamanın ayarlarını kullanır: ajanın çalışabileceği klasörleri, "
    "kural takımını ve maskeli kopya yazma iznini kullanıcı uygulamada Ayarlar › Ajan erişimi bölümünden verir; "
    "her işlem uygulamanın hash zincirli işlem günlüğüne yazılır. Uygulama kurulu değilse araçlar "
    "`app_not_installed` hatası döndürür."
)


class PaketHatasi(Exception):
    pass


def motor_yolu(klasor: Path, platform: str) -> Path:
    return klasor / (MOTOR_ADI + PLATFORMLAR[platform][1])


def mcp_tanit(motor: Path) -> dict:
    """Motoru `mcp` ile başlatır; initialize ve tools/list yanıtlarını döndürür."""
    istekler = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "mcpb-paketle", "version": "1"}}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
    ]
    girdi = "".join(json.dumps(i) + "\n" for i in istekler)
    ortam = {k: v for k, v in os.environ.items() if k not in ("BULUTBELGE_GELISTIRME", "BULUTBELGE_DATA_DIR")}
    try:
        sonuc = subprocess.run(
            [str(motor), "mcp"], input=girdi.encode("utf-8"), capture_output=True, timeout=ZAMAN_ASIMI, env=ortam
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PaketHatasi(f"Motor 'mcp' olarak çalıştırılamadı: {exc}") from None
    satirlar = [json.loads(s) for s in sonuc.stdout.decode("utf-8").splitlines() if s.strip()]
    yanit = {s.get("id"): s for s in satirlar}
    if sonuc.returncode != 0 or 1 not in yanit or 2 not in yanit:
        raise PaketHatasi(
            f"Motor MCP yanıtı eksik (çıkış {sonuc.returncode}): {sonuc.stderr.decode('utf-8', 'replace')[-400:]}"
        )
    bilgi = yanit[1]["result"]["serverInfo"]
    if bilgi.get("name") != "bulutbelge":
        raise PaketHatasi(f"Beklenmeyen sunucu adı: {bilgi.get('name')}")
    return {"surum": bilgi["version"], "araclar": yanit[2]["result"]["tools"]}


def manifest(surum: str, platform: str, araclar: list[dict]) -> dict:
    giris = f"{SUNUCU_KLASORU}/{MOTOR_ADI}{PLATFORMLAR[platform][1]}"
    return {
        "$schema": "https://raw.githubusercontent.com/modelcontextprotocol/mcpb/main/schemas/mcpb-manifest-v0.3.schema.json",
        "manifest_version": MANIFEST_SURUMU,
        "name": "bulutbelge",
        "display_name": "BulutBelge",
        "version": surum,
        "description": ACIKLAMA,
        "long_description": UZUN_ACIKLAMA,
        "author": {"name": "Proteksistem", "url": "https://bulutbelge.com"},
        "repository": {"type": "git", "url": "https://github.com/bulutbelge/bulutbelge"},
        "homepage": "https://bulutbelge.com",
        "documentation": "https://bulutbelge.com/ajan.html",
        "support": "https://github.com/bulutbelge/bulutbelge/issues",
        "icon": "icon.png",
        "server": {
            "type": "binary",
            "entry_point": giris,
            "mcp_config": {"command": "${__dirname}/" + giris, "args": ["mcp"], "env": {}},
        },
        "tools": [{"name": a["name"], "description": a.get("description", "")} for a in araclar],
        "tools_generated": False,
        "keywords": ["kişisel veri", "KVKK", "GDPR", "maskeleme", "anonimleştirme", "PDF", "Word", "redaction", "privacy"],
        "license": "AGPL-3.0-only",
        "privacy_policies": ["https://bulutbelge.com/aydinlatma.html"],
        "compatibility": {"platforms": [PLATFORMLAR[platform][0]]},
    }


def _girdi(ad: str, zaman: tuple, kip: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(ad, date_time=zaman)
    info.create_system = 3  # Unix: izin bitleri external_attr'ın üst 16 bitinde (mcpb pack ile aynı)
    info.external_attr = (stat.S_IFREG | kip) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    return info


def _kip(yol: Path, giris: bool) -> int:
    if giris:
        return 0o755
    if os.name != "nt" and os.stat(yol).st_mode & stat.S_IXUSR:
        return 0o755
    return 0o644


def zip_yaz(hedef: Path, motor_klasoru: Path, platform: str, mani: dict, epoch: int) -> None:
    zaman = tuple(time.gmtime(max(epoch, 315532800))[:6])  # zip en erken 1980
    giris = mani["server"]["entry_point"]
    dosyalar: list[tuple[str, Path]] = []
    for yol in sorted(motor_klasoru.rglob("*")):
        if yol.is_symlink():
            raise PaketHatasi(f"Motor klasöründe sembolik bağ var (MCPB açıcıları desteklemez): {yol}")
        if yol.is_file():
            dosyalar.append((f"{SUNUCU_KLASORU}/{yol.relative_to(motor_klasoru).as_posix()}", yol))
    if not any(ad == giris for ad, _ in dosyalar):
        raise PaketHatasi(f"Giriş dosyası yok: {giris}")
    gecici = hedef.with_suffix(".tmp")
    with zipfile.ZipFile(gecici, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        z.writestr(_girdi("manifest.json", zaman, 0o644), json.dumps(mani, ensure_ascii=False, indent=2) + "\n")
        if SIMGE.is_file():
            z.writestr(_girdi("icon.png", zaman, 0o644), SIMGE.read_bytes())
        for ad, yol in dosyalar:
            with open(yol, "rb") as f, z.open(_girdi(ad, zaman, _kip(yol, ad == giris)), "w") as w:
                while parca := f.read(1 << 20):
                    w.write(parca)
    os.replace(gecici, hedef)


def ac(arsiv: Path, hedef: Path) -> None:
    """MCPB'yi açar ve POSIX izinlerini uygular (Claude Desktop ve `mcpb unpack` ile aynı davranış)."""
    with zipfile.ZipFile(arsiv) as z:
        for info in z.infolist():
            yol = (hedef / info.filename).resolve()
            if not yol.is_relative_to(hedef.resolve()):
                raise PaketHatasi(f"Arşivde klasör dışına çıkan yol: {info.filename}")
            z.extract(info, hedef)
            kip = (info.external_attr >> 16) & 0o777
            if kip and os.name != "nt":
                os.chmod(yol, kip)


def paketle(motor_klasoru: Path, platform: str, cikti: Path, surum: str | None = None, epoch: int | None = None) -> Path:
    if platform not in PLATFORMLAR:
        raise PaketHatasi(f"Bilinmeyen platform: {platform} (geçerli: {', '.join(PLATFORMLAR)})")
    motor = motor_yolu(motor_klasoru, platform)
    if not motor.is_file():
        raise PaketHatasi(f"Motor bulunamadı: {motor}")
    tanitim = mcp_tanit(motor)
    if surum is not None and surum != tanitim["surum"]:
        raise PaketHatasi(f"Sürüm uyuşmuyor: istenen {surum}, motor {tanitim['surum']}")
    surum = tanitim["surum"]
    mani = manifest(surum, platform, tanitim["araclar"])
    if epoch is None:
        epoch = int(os.environ.get("SOURCE_DATE_EPOCH") or 0)
    cikti.mkdir(parents=True, exist_ok=True)
    hedef = cikti / f"bulutbelge-mcp-{surum}-{platform}.mcpb"
    zip_yaz(hedef, motor_klasoru, platform, mani, epoch)
    # Açılan kopya da çalışmalı (izin bitleri, eksik dosya).
    with tempfile.TemporaryDirectory(prefix="mcpb-dene-") as d:
        ac(hedef, Path(d))
        acilan = json.loads((Path(d) / "manifest.json").read_text(encoding="utf-8"))
        denenen = mcp_tanit(Path(d) / acilan["server"]["entry_point"])
        if denenen["surum"] != surum or [a["name"] for a in denenen["araclar"]] != [a["name"] for a in mani["tools"]]:
            raise PaketHatasi("Açılan paketteki motor farklı yanıt verdi")
    return hedef


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="BulutBelge MCP sunucusunu MCPB paketi olarak paketler")
    ap.add_argument("--motor", required=True, type=Path, help="PyInstaller motor klasörü (bulutbelge-engine[.exe] içerir)")
    ap.add_argument("--platform", required=True, choices=sorted(PLATFORMLAR))
    ap.add_argument("--cikti", required=True, type=Path)
    ap.add_argument("--surum", help="Beklenen sürüm (etiketten); motorun bildirdiğiyle aynı olmalı")
    ap.add_argument("--manifest-yaz", type=Path, help="manifest.json'un kopyasını buraya da yaz (şema doğrulaması için)")
    a = ap.parse_args(argv)
    try:
        hedef = paketle(a.motor, a.platform, a.cikti, a.surum)
    except PaketHatasi as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 1
    if a.manifest_yaz:
        with zipfile.ZipFile(hedef) as z:
            a.manifest_yaz.write_bytes(z.read("manifest.json"))
    print(f"MCPB paketi: {hedef} ({hedef.stat().st_size / 1e6:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
