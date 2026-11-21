"""Üçüncü taraf lisans listesini üretir (TAKIP T4, T5; NOTICE.md "Yenileme" adımı).

Kullanım (depo kökünden):
    python core/tools/lisans_listesi_uret.py > THIRD-PARTY-LICENSES.md

Kaynaklar (hiçbir şey indirmez, kurulu olanı okur):
  - Python: `desktop/engine/.venv` içindeki kurulu dağıtımlar (kilit dosyasıyla kurulmuş ortam)
  - JavaScript: `desktop/node_modules` içindeki üretim bağımlılıkları (`npm ls --omit=dev --all`)
  - Rust: `cargo metadata` (geliştirme bağımlılıkları hariç, derleme bağımlılıkları dahil)
Çıktı lisansa göre gruplanır; GPL/LGPL/AGPL/MPL gibi paylaşımlı lisanslar en başta ayrıca işaretlenir.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "desktop"
COPYLEFT = re.compile(r"GPL|MPL|EPL|CDDL|OSL|EUPL", re.I)

PY_SNIPPET = r"""
import json, importlib.metadata as m
out = []
for d in m.distributions():
    md = d.metadata
    lic = md.get("License-Expression") or ""
    if not lic:
        lic = md.get("License") or ""
        if len(lic) > 80 or "\n" in lic:
            lic = ""
    if not lic:
        cl = [c.split("::")[-1].strip() for c in md.get_all("Classifier") or [] if c.startswith("License ::")]
        lic = " / ".join(cl)
    out.append([md["Name"], md["Version"], lic or "BİLİNMİYOR"])
print(json.dumps(out))
"""


def python_paketleri() -> list[tuple[str, str, str]]:
    py = DESKTOP / "engine" / ".venv" / "bin" / "python"
    if not py.exists():
        py = DESKTOP / "engine" / ".venv" / "Scripts" / "python.exe"
    out = subprocess.run([str(py), "-c", PY_SNIPPET], capture_output=True, text=True, check=True).stdout
    return [tuple(x) for x in json.loads(out)]


def js_paketleri() -> list[tuple[str, str, str]]:
    r = subprocess.run(["npm", "ls", "--omit=dev", "--all", "--json", "--long"], cwd=DESKTOP, capture_output=True, text=True)
    tree = json.loads(r.stdout or "{}")
    seen: dict[str, tuple[str, str, str]] = {}

    def walk(deps: dict) -> None:
        for name, info in (deps or {}).items():
            lic = info.get("license") or info.get("licenses") or ""
            if isinstance(lic, dict):
                lic = lic.get("type", "")
            if isinstance(lic, list):
                lic = " OR ".join(x.get("type", str(x)) if isinstance(x, dict) else str(x) for x in lic)
            seen[f"{name}@{info.get('version', '?')}"] = (name, info.get("version", "?"), lic or "BİLİNMİYOR")
            walk(info.get("dependencies"))

    walk(tree.get("dependencies"))
    return sorted(seen.values())


def rust_paketleri() -> list[tuple[str, str, str]]:
    meta = json.loads(
        subprocess.run(
            ["cargo", "metadata", "--format-version", "1", "--manifest-path", str(DESKTOP / "src-tauri" / "Cargo.toml")],
            capture_output=True, text=True, check=True,
        ).stdout
    )
    dev_only = {d["pkg"] for n in meta["resolve"]["nodes"] for d in n["deps"] if all(k["kind"] == "dev" for k in d["dep_kinds"])}
    root = meta["resolve"]["root"]
    out = []
    for p in meta["packages"]:
        if p["id"] == root or p["id"] in dev_only:
            continue
        out.append((p["name"], p["version"], p.get("license") or ("(" + p["license_file"] + ")" if p.get("license_file") else "BİLİNMİYOR")))
    return sorted(set(out))


def bolum(baslik: str, paketler: list[tuple[str, str, str]]) -> str:
    gruplar: dict[str, list[str]] = defaultdict(list)
    for ad, surum, lic in paketler:
        gruplar[lic].append(f"{ad} {surum}")
    satirlar = [f"## {baslik} ({len(paketler)} paket)", ""]
    for lic in sorted(gruplar, key=lambda k: (-len(gruplar[k]), k)):
        satirlar.append(f"**{lic}** ({len(gruplar[lic])}): " + ", ".join(sorted(gruplar[lic])))
        satirlar.append("")
    return "\n".join(satirlar)


def main() -> None:
    bolumler = {"Python (motor ortamı)": python_paketleri(), "JavaScript (arayüz, üretim)": js_paketleri(), "Rust (kabuk)": rust_paketleri()}
    isaretli = sorted(
        {f"{ad} {surum}: {lic} ({k})" for k, paketler in bolumler.items() for ad, surum, lic in paketler if COPYLEFT.search(lic) or lic == "BİLİNMİYOR"}
    )
    print("# Üçüncü taraf lisans listesi (üretilmiş)\n")
    print("Bu dosya `python core/tools/lisans_listesi_uret.py` ile üretilir; elle düzenlenmez. Tablolu özet ve notlar `NOTICE.md` içindedir.\n")
    print("## Paylaşımlı (copyleft) ya da bilinmeyen lisanslılar\n")
    print("\n".join(f"- {x}" for x in isaretli) if isaretli else "Yok.")
    print()
    for baslik, paketler in bolumler.items():
        print(bolum(baslik, paketler))


if __name__ == "__main__":
    sys.exit(main())
