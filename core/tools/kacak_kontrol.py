"""Örnek belgeleri maskeleyip maskeli kopyada orijinal değer arar (TAKIP 1.80'in ilk adımı).

Kullanım (desktop/engine/.venv içindeki Python ile, repo kökünden):

    python core/tools/kacak_kontrol.py <örnek-klasör> [<çıktı-klasör>]

Klasörde `beklenen.json` olmalı (zor_ornekler_uret.py üretir). Her belge varsayılan
kurallarla taranır ve maskelenir; maskeli kopyada her beklenen değer şu katmanlarda aranır:

- ham bayt (UTF-8, UTF-16, Latin-1) ve rakam dışı karakterler atılmış hâli
- PDF: tüm akışlar açılarak (artımlı kayıttaki eski sürümler dahil), metin katmanı,
  meta veri, XMP, notlar, form alanları, gömülü dosyalar, yer imleri, JavaScript
  (açık ve akış içi), sayfa önizleme görselleri (/Thumb, OCR ile) ve artımlı kayıtların
  her `%%EOF` noktasındaki eski sürümleri ("eski-sürüm-N/…" katmanları)
- Office: bütün zip parçaları açılarak; docProps/thumbnail.* önizleme görseli OCR ile
- görsel: yeniden tarama (OCR) ile bulunan bulgular

Değerler sahtedir; yine de rapora değerin kendisi değil yalnızca ilk iki karakteri yazılır.
Çıkış kodu: 0 kaçak yok, 1 kaçak var, 2 kullanım hatası.
"""

from __future__ import annotations

import io
import json
import re
import sys
import zipfile
import zlib
from pathlib import Path

import pymupdf

from bulutbelge_core.documents import kind_of
from bulutbelge_core.image import is_image
from bulutbelge_core.ocr import ocr_available, ocr_textpage
from bulutbelge_core.pdf import PdfError, mask_pdf, scan_pdf
from bulutbelge_core.rules import Rules
from bulutbelge_core import office
from bulutbelge_core.textdoc import mask_text_doc

FW = str.maketrans("０１２３４５６７８９", "0123456789")


def _norm(s: str) -> str:
    return re.sub(r"\s+", "", s.translate(FW)).casefold()


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s.translate(FW))


def _ocr_image_bytes(data: bytes) -> str | None:
    """Önizleme görselini OCR ile okur; OCR yoksa ya da görsel açılamazsa None."""
    if not ocr_available():
        return None
    try:
        with pymupdf.open(stream=data) as img_doc:
            page = img_doc[0]
            return ocr_textpage(page, True).extractText()
    except Exception:  # noqa: BLE001 - bozuk önizleme kaçak sayılmaz, atlanır
        return None


def _pdf_thumbnails(doc: pymupdf.Document) -> list[bytes]:
    """Sayfa sözlüklerindeki /Thumb görsellerini PNG baytı olarak döndürür."""
    out = []
    for xref in range(1, doc.xref_length()):
        if doc.xref_get_key(xref, "Type")[1] == "/Page" and doc.xref_get_key(xref, "Thumb")[0] == "xref":
            t_xref = int(doc.xref_get_key(xref, "Thumb")[1].split()[0])
            try:
                out.append(pymupdf.Pixmap(doc, t_xref).tobytes("png"))
            except Exception:  # noqa: BLE001 - çözülemeyen önizleme
                continue
    return out


def _pdf_javascript(doc: pymupdf.Document, data: bytes) -> str:
    """/JS ve /JavaScript içeren bütün nesneler (akış içeriği dahil) ile ham JS dizgeleri."""
    parts = []
    for xref in range(1, doc.xref_length()):
        try:
            obj = doc.xref_object(xref, compressed=False)
        except Exception:  # noqa: BLE001
            continue
        if "/JS" in obj or "/JavaScript" in obj:
            parts.append(obj)
            try:
                parts.append((doc.xref_stream(xref) or b"").decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                pass
    return "\n".join(parts)


def _pdf_text_layers(data: bytes) -> dict[str, str]:
    layers = {"ham": data.decode("latin-1")}
    inflated = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S):
        try:
            inflated.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except zlib.error:
            pass
    layers["akislar"] = "\n".join(inflated)
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:  # noqa: BLE001 - görsel çıktı
        return layers
    with doc:
        layers["metin"] = "\n".join(p.get_text() for p in doc)
        layers["meta"] = json.dumps(doc.metadata, ensure_ascii=False) + (doc.get_xml_metadata() or "")
        layers["yer_imi"] = json.dumps(doc.get_toc(), ensure_ascii=False)
        notes = []
        for p in doc:
            notes += [a.info.get("content", "") for a in p.annots() or []]
            notes += [w.field_value or "" for w in p.widgets() or []]
        layers["not_form"] = "\n".join(map(str, notes))
        layers["gomulu"] = "\n".join(doc.embfile_get(i).decode("utf-8", "replace") for i in range(doc.embfile_count()))
        layers["javascript"] = _pdf_javascript(doc, data)
        previews = [t for t in (_ocr_image_bytes(b) for b in _pdf_thumbnails(doc)) if t]
        layers["onizleme"] = "\n".join(previews)
    return layers


def _pdf_revisions(data: bytes) -> list[bytes]:
    """Artımlı kayıtlarda her `%%EOF` noktasında kesilmiş eski sürümler (son sürüm hariç)."""
    ends = [m.end() for m in re.finditer(rb"%%EOF", data)]
    return [data[:e] for e in ends[:-1] if e < len(data.rstrip())]


def _pdf_layers(data: bytes) -> dict[str, str]:
    layers = _pdf_text_layers(data)
    for i, old in enumerate(_pdf_revisions(data), 1):
        for name, text in _pdf_text_layers(old).items():
            if name != "ham":  # ham bayt zaten son sürümün içinde aranıyor
                layers[f"eski-sürüm-{i}/{name}"] = text
    return layers


def _zip_layers(data: bytes) -> dict[str, str]:
    out = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for n in z.namelist():
            raw = z.read(n)
            out[n] = raw.decode("utf-8", "replace")
            if n.startswith("docProps/thumbnail"):
                text = _ocr_image_bytes(raw)
                if text:
                    out[f"{n} (OCR)"] = text
    return out


def _layers(path: Path) -> dict[str, str]:
    data = path.read_bytes()
    kind = kind_of(path)
    layers: dict[str, str] = {}
    if kind == "pdf":
        layers.update(_pdf_layers(data))
    elif kind in ("word", "sunum", "tablo"):
        layers.update(_zip_layers(data))
    else:
        for enc in ("utf-8", "utf-16", "latin-1"):
            try:
                layers[f"ham-{enc}"] = data.decode(enc)
            except UnicodeDecodeError:
                pass
    return layers


def _mask(src: Path, dst_dir: Path, rules: Rules) -> Path:
    kind = kind_of(src)
    target = dst_dir / f"{src.stem}_maskeli{src.suffix}"
    if kind == "metin":
        return Path(mask_text_doc(src, target, rules)[0])
    if kind in ("word", "sunum", "tablo"):
        return Path(office.mask(src, target, office.format_of(src), rules)[0])
    return Path(mask_pdf(src, target, rules).target)


def check(folder: Path, out_dir: Path) -> int:
    expected = json.loads((folder / "beklenen.json").read_text(encoding="utf-8"))
    out_dir.mkdir(parents=True, exist_ok=True)
    rules = Rules.from_dict(None)
    leaks = 0
    for name, spec in expected.items():
        src = folder / name
        print(f"\n== {name}")
        try:
            out = _mask(src, out_dir, rules)
        except PdfError as exc:
            print(f"   MASKELENEMEDİ: {exc}")
            leaks += 1
            continue
        layers = _layers(out)
        image_values: set[str] = set()
        if is_image(out):
            yeniden = scan_pdf(out, rules)
            image_values = {_norm(f.finding.value) for f in yeniden.findings}
            if any("OCR dil dosyaları kurulu değil" in w for w in yeniden.warnings):
                # OCR yoksa görselde yeniden okuma boş döner ve "temiz" görünürdü (yanlış güvence); sessiz geçilmez.
                print("   KONTROL YAPILAMADI: OCR dil dosyaları kurulu değil (BULUTBELGE_TESSDATA); görsel sonucu geçerli sayılmaz")
                leaks += 1
                continue
        for value in spec["degerler"]:
            hits = [k for k, text in layers.items() if _norm(value) in _norm(text)]
            d = _digits(value)
            if len(d) >= 10:
                hits += [f"{k} (rakamlar)" for k, text in layers.items() if d in _digits(text) and k not in hits]
            if _norm(value) in image_values:
                hits.append("yeniden tarama (OCR)")
            label = value[:2] + "…"
            if hits:
                leaks += 1
                print(f"   KAÇAK  {label:6} → {', '.join(hits[:6])}")
            else:
                print(f"   temiz  {label}")
        for n in spec.get("not", []):
            print(f"   not: {n}")
    print(f"\nToplam kaçak: {leaks}")
    return 1 if leaks else 0


def _tessdata_varsayilan() -> None:
    """OCR dil dosyası ortam değişkeniyle verilmediyse depodaki masaüstü motoru klasörünü kullanır."""
    import os

    if os.environ.get("BULUTBELGE_TESSDATA"):
        return
    aday = Path(__file__).resolve().parents[2] / "desktop" / "engine" / "tessdata"
    if (aday / "tur.traineddata").exists():
        os.environ["BULUTBELGE_TESSDATA"] = str(aday)


def main() -> None:
    _tessdata_varsayilan()
    if len(sys.argv) not in (2, 3):
        print(__doc__)
        sys.exit(2)
    folder = Path(sys.argv[1])
    out_dir = Path(sys.argv[2]) if len(sys.argv) == 3 else folder.with_name(folder.name + "_kontrol")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.exit(check(folder, out_dir))


if __name__ == "__main__":
    main()
