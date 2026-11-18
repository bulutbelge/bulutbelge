"""Uygulama dışarıya ağ bağlantısı kurmaz (TAKIP 1.90, "gizlilik sözü" denetimi).

Çekirdek ve masaüstü motoru Python kodu ağ modülü içe aktarmaz; masaüstü kurum sunucusuna hiçbir istek atmaz
(karar 17 Kasım 2026, "masaüstü ve sunucu ayrı"). Rust tarafında yalnızca güncelleme denetimi
(`guncelleme.rs`, bulutbelge.com/surum.json) ağa çıkar. Yeni bir ağ bağlantısı eklenirse bu test kırılır ve
bilinçli olarak, gizlilik metniyle birlikte güncellenmelidir.
"""

import ast
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
YASAK = {"requests", "urllib", "urllib3", "socket", "http", "httpx", "aiohttp", "ftplib", "smtplib", "telnetlib",
         "websockets", "xmlrpc", "imaplib", "poplib", "ssl", "asyncio.streams"}


def _ice_aktarilanlar(yol: Path) -> set[str]:
    ad: set[str] = set()
    for n in ast.walk(ast.parse(yol.read_text(encoding="utf-8"))):
        if isinstance(n, ast.Import):
            ad |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            ad.add(n.module.split(".")[0])
    return ad


def test_cekirdek_ve_motor_ag_modulu_icermez():
    sorunlu = {}
    for klasor in ("core/bulutbelge_core", "desktop/engine/bulutbelge_engine"):
        for yol in (KOK / klasor).rglob("*.py"):
            bulunan = _ice_aktarilanlar(yol) & YASAK
            if bulunan:
                sorunlu[str(yol.relative_to(KOK)).replace("\\", "/")] = sorted(bulunan)
    assert not sorunlu, f"Ağ modülü içe aktarılıyor: {sorunlu}"


def test_rust_tarafinda_yalnizca_guncelleme_agi_kullanir():
    kaynaklar = {p.name: p.read_text(encoding="utf-8") for p in (KOK / "desktop/src-tauri/src").glob("*.rs")}
    agli = sorted(ad for ad, metin in kaynaklar.items() if "ureq::" in metin or "reqwest" in metin or "TcpStream" in metin)
    assert agli == ["guncelleme.rs"], agli
    cargo = (KOK / "desktop/src-tauri/Cargo.toml").read_text(encoding="utf-8")
    assert "reqwest" not in cargo and "hyper" not in cargo


def test_masaustu_sunucu_baglantisi_icermez():
    assert not (KOK / "desktop/engine/bulutbelge_engine/sunucu.py").exists()
    assert not (KOK / "desktop/src/SunucuPanel.tsx").exists()
    assert '"server.' not in (KOK / "desktop/engine/bulutbelge_engine/protocol.py").read_text(encoding="utf-8")
    # Arayüz motorun sunucu komutlarını çağırmaz ve doğrudan ağ isteği atmaz.
    for yol in (KOK / "desktop/src").rglob("*.ts*"):
        metin = yol.read_text(encoding="utf-8")
        assert '"server.' not in metin, yol.name
        assert "fetch(" not in metin and "XMLHttpRequest" not in metin and "WebSocket" not in metin, yol.name
