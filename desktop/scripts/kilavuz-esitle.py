"""Ajan kılavuzunu tek kaynaktan eşitler.

Kaynak: desktop/engine/bulutbelge_engine/kilavuz.md (uygulamayla gelir: `bulutbelge kilavuz`; 22 Kasım 2026
ürün sahibi kararı, docs/kararlar/2026-11-14-ajan-kilavuzu-konumlari.md "Güncelleme"). Kopyalar:
- docs/AJAN-KOMUT-SATIRI.md                      (depodaki okunur kopya; README bağlantıları buraya)
- site/ajan.md                                   (ajanların indirebileceği düz metin)
- site/ajan.html                                 (insanlar için web sayfası)

Kullanım: python desktop/scripts/kilavuz-esitle.py          (kopyaları yazar)
          python desktop/scripts/kilavuz-esitle.py --kontrol (fark varsa hata koduyla çıkar)
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "desktop" / "engine" / "bulutbelge_engine" / "kilavuz.md"
DOCS_COPY = ROOT / "docs" / "AJAN-KOMUT-SATIRI.md"
SITE_MD = ROOT / "site" / "ajan.md"
SITE_HTML = ROOT / "site" / "ajan.html"


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = re.sub(r"`([^`]+)`", lambda m: f"<code>{m.group(1)}</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', out)
    return out


def markdown_to_html(md: str) -> str:
    """Kılavuzda kullanılan Markdown alt kümesi: başlık, paragraf, liste, tablo, kod çiti."""
    md = re.sub(r"<!--.*?-->\n?", "", md, flags=re.S)
    lines = md.split("\n")
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            code = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1
            out.append("<pre><code>" + html.escape("\n".join(code), quote=False) + "</code></pre>")
            continue
        m = re.match(r"(#{1,3}) (.*)", line)
        if m:
            level = len(m.group(1))
            cls = ' class="first"' if level == 2 and not any(o.startswith("<h2") for o in out) else ""
            out.append(f"<h{level}{cls}>{_inline(m.group(2))}</h{level}>")
            i += 1
            continue
        if line.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                i += 1
            head, body = rows[0], [r for r in rows[1:] if not all(re.fullmatch(r":?-{3,}:?", c) for c in r)]
            t = ["<div class=\"tablo\"><table>"]
            if any(head):
                t.append("<thead><tr>" + "".join(f"<th>{_inline(c)}</th>" for c in head) + "</tr></thead>")
            t.append("<tbody>" + "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>" for r in body) + "</tbody>")
            t.append("</table></div>")
            out.append("".join(t))
            continue
        if re.match(r"(?:- |\d+\. )", line):
            ordered = bool(re.match(r"\d+\. ", line))
            start = int(re.match(r"(\d+)\. ", line).group(1)) if ordered else 1
            items = []
            while i < len(lines) and re.match(r"(?:- |\d+\. )", lines[i]):
                text = re.sub(r"^(?:- |\d+\. )", "", lines[i])
                i += 1
                while i < len(lines) and lines[i].startswith("   ") and lines[i].strip():
                    text += " " + lines[i].strip()
                    i += 1
                items.append(f"<li>{_inline(text)}</li>")
            opening = f'<ol start="{start}">' if ordered and start != 1 else ("<ol>" if ordered else "<ul>")
            out.append(opening + "".join(items) + ("</ol>" if ordered else "</ul>"))
            continue
        if not line.strip():
            i += 1
            continue
        para = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r"(?:#|\||```|- |\d+\. )", lines[i]):
            para.append(lines[i])
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return "\n".join(out)


def build_html(md: str) -> str:
    body = markdown_to_html(md)
    title = re.match(r"# (.*)", md).group(1)
    # İlk başlık sayfanın h1'i olur (markdown_to_html "h1" üretir).
    return f"""<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light">
<meta name="theme-color" content="#fbfaf7">
<title>BulutBelge komut satırı kılavuzu</title>
<meta name="description" content="BulutBelge'yi terminalden ve yapay zekâ ajanlarıyla kullanma kılavuzu.">
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<link rel="stylesheet" href="style.css">
</head>
<body>
<header class="top"><div class="wrap"><a class="logo" href="./"><img class="logo-resim" src="logo.svg" alt="BulutBelge" width="119" height="24"></a><nav><a href="./">Ana sayfa</a> · <a href="ajan.md">Düz metin (ajanlar için)</a></nav></div></header>
<main><div class="wrap page">
<!-- Bu sayfa desktop/engine/bulutbelge_engine/kilavuz.md'den desktop/scripts/kilavuz-esitle.py ile üretilir; elle düzenlemeyin. -->
{body}
</div></main>
<footer><div class="wrap"><p><a href="./">Ana sayfa</a> · <a href="kosullar.html">Kullanım Koşulları</a> · <a href="aydinlatma.html">Aydınlatma Metni</a> · <a href="cerez.html">Çerez Politikası</a></p></div></footer>
</body>
</html>
"""


def outputs() -> dict[Path, str]:
    md = SOURCE.read_text(encoding="utf-8")
    return {DOCS_COPY: md, SITE_MD: md, SITE_HTML: build_html(md)}


def main() -> int:
    check = "--kontrol" in sys.argv
    bad = []
    for path, content in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == content:
            continue
        if check:
            bad.append(path.relative_to(ROOT))
        else:
            path.write_text(content, encoding="utf-8")
            print("yazıldı:", path.relative_to(ROOT))
    if bad:
        print("Eşitlenmemiş dosyalar (python desktop/scripts/kilavuz-esitle.py çalıştırın):", *map(str, bad), sep="\n  ")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
