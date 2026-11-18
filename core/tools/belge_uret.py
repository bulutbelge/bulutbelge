"""Koddan belge üretimi (TAKIP D.2).

Yalnızca standart kütüphane ve projenin kendi paketleri. Üretilen dosyalar:

- docs/api/referans.md: sunucunun OpenAPI şemasından uç başvurusu
- docs/uretilen/ayarlar.md: `BB_*` ortam değişkenleri (server config.py)
- docs/uretilen/roller.md: varsayılan rol–yetki tablosu (server roller.py)
- docs/uretilen/veri-turleri.md: çekirdek veri türleri ve varsayılan sütun başlığı sözlüğü
- docs/uretilen/bulutbelge.1: masaüstü komut satırının man sayfası (argparse tanımları + kılavuz, groff)

Çıktı deterministiktir (tarih/saat yazılmaz). Kullanım: `python core/tools/belge_uret.py`
(`--denetle`: diskteki dosyalar güncel mi bakar, yazmaz). Sunucu uygulaması geçici veri
klasörüyle, ağsız kurulur; hiçbir dış servise bağlanılmaz.
"""
import argparse
import inspect
import re
import sys
import tempfile
from pathlib import Path

KOK = Path(__file__).resolve().parents[2]
for _p in (KOK / "core", KOK / "server", KOK / "desktop" / "engine"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

NOT = "> Bu dosya üretilir, elle düzenlemeyin: `python core/tools/belge_uret.py`\n"
DOSYALAR = ("docs/api/referans.md", "docs/uretilen/ayarlar.md", "docs/uretilen/roller.md", "docs/uretilen/veri-turleri.md", "docs/uretilen/bulutbelge.1")
YONTEMLER = ("get", "post", "put", "patch", "delete")


def _hucre(metin) -> str:
    return " ".join(str(metin if metin is not None else "").split()).replace("|", "\\|") or "—"


def _tablo(baslik: list[str], satirlar: list[list]) -> str:
    cikti = ["| " + " | ".join(baslik) + " |", "|" + "|".join("---" for _ in baslik) + "|"]
    cikti += ["| " + " | ".join(_hucre(h) for h in s) + " |" for s in satirlar]
    return "\n".join(cikti) + "\n"


# ---------- API başvurusu ----------

def _uygulama():
    from bulutbelge_server.config import Ayarlar
    from bulutbelge_server.main import create_app

    with tempfile.TemporaryDirectory() as gecici:
        cfg = Ayarlar(_env_file=None, ortam="test", kimlik="kapali", kuyruk="satir_ici", veri_klasoru=gecici)
        app = create_app(cfg)
        return app, app.openapi()


def _kimlik_bilgisi(app) -> dict[tuple[str, str], str]:
    """Her (yöntem, yol) için bağımlılıklardan okunan kimlik/yetki bilgisi."""
    sonuc: dict[tuple[str, str], str] = {}

    def gez(dep, bulunan: list[str]) -> None:
        for alt in dep.dependencies:
            ad = getattr(alt.call, "__name__", "")
            if ad == "denetle":
                roller = {}
                for kod, hucre in zip(alt.call.__code__.co_freevars, alt.call.__closure__ or ()):
                    roller[kod] = hucre.cell_contents
                izinli = roller.get("izinli") or ()
                bulunan.append("Panel oturumu, rol: " + ", ".join(izinli) if izinli else "Panel oturumu")
            elif ad == "oturum_ya_da_anahtar":
                bulunan.append("Panel oturumu ya da API anahtarı")
            elif ad == "istemci_ya_da_panel":
                bulunan.append("API anahtarı ya da panel oturumu")
            gez(alt, bulunan)

    def rotalar(liste):
        for r in liste:
            alt = getattr(getattr(r, "original_router", None), "routes", None)  # include_router ile eklenenler
            if alt is not None:
                yield from rotalar(alt)
            else:
                yield r

    for r in rotalar(getattr(app, "routes", [])):
        dependant = getattr(r, "dependant", None)
        if dependant is None:
            continue
        bulunan: list[str] = []
        gez(dependant, bulunan)
        for y in getattr(r, "methods", None) or ():
            sonuc[(y.lower(), r.path)] = "; ".join(dict.fromkeys(bulunan)) or "Uçta denetlenir ya da açık"
    return sonuc


def _cozumle(sema: dict, ref: dict):
    r = ref.get("$ref") if isinstance(ref, dict) else None
    if r and r.startswith("#/"):
        dugum = sema
        for parca in r[2:].split("/"):
            dugum = dugum[parca]
        return dugum
    return ref


def _tur(sema: dict, alan: dict) -> str:
    if "$ref" in alan:
        return alan["$ref"].rsplit("/", 1)[-1]
    for anahtar in ("anyOf", "oneOf"):
        if anahtar in alan:
            return " | ".join(_tur(sema, a) for a in alan[anahtar])
    if alan.get("type") == "array":
        return f"liste[{_tur(sema, alan.get('items', {}))}]"
    return str(alan.get("type", "—"))


def _govde_alanlari(sema: dict, govde: dict) -> list[str]:
    cikti = []
    for tur in sorted(govde.get("content", {})):
        s = _cozumle(sema, govde["content"][tur].get("schema", {}))
        ozellikler = s.get("properties", {})
        gerekli = set(s.get("required", []))
        satirlar = [
            [f"`{ad}`", _tur(sema, o), "evet" if ad in gerekli else "hayır", o.get("description") or o.get("title", "")]
            for ad, o in sorted(ozellikler.items())
        ]
        cikti.append(f"İstek gövdesi (`{tur}`{', zorunlu' if govde.get('required') else ''}):\n")
        cikti.append(_tablo(["Alan", "Tür", "Zorunlu", "Açıklama"], satirlar) if satirlar else "Alan şeması tanımlı değil.\n")
    return cikti


def api_referansi() -> str:
    app, sema = _uygulama()
    kimlik = _kimlik_bilgisi(app)
    ust = [
        "# API başvurusu\n",
        NOT,
        "Kaynak: sunucunun OpenAPI şeması. Genel kimlik: `Authorization: Bearer bb_...` (API anahtarı); "
        "uçlara göre panel oturumu da geçerli olabilir. Ayrıntı için ilgili uç satırındaki \"Kimlik/yetki\" alanına bakın.\n",
    ]
    govde = []
    for yol in sorted(sema["paths"]):
        for yontem in YONTEMLER:
            uc = sema["paths"][yol].get(yontem)
            if uc is None:
                continue
            govde.append(f"## {yontem.upper()} {yol}\n")
            govde.append(f"- Özet: {_hucre(uc.get('summary'))}")
            if uc.get("description"):
                govde.append(f"- Açıklama: {_hucre(uc['description'])}")
            govde.append(f"- Kimlik/yetki: {kimlik.get((yontem, yol), 'Uçta denetlenir ya da açık')}")
            if uc.get("tags"):
                govde.append(f"- Etiket: {', '.join(sorted(uc['tags']))}")
            govde.append("")
            parametreler = [_cozumle(sema, p) for p in uc.get("parameters", [])]
            if parametreler:
                govde.append("Parametreler:\n")
                govde.append(_tablo(
                    ["Ad", "Konum", "Tür", "Zorunlu"],
                    [[f"`{p['name']}`", p["in"], _tur(sema, p.get("schema", {})), "evet" if p.get("required") else "hayır"]
                     for p in sorted(parametreler, key=lambda p: (p["in"], p["name"]))],
                ))
            if "requestBody" in uc:
                govde.extend(_govde_alanlari(sema, _cozumle(sema, uc["requestBody"])))
            govde.append("Yanıt kodları:\n")
            govde.append(_tablo(
                ["Kod", "Açıklama"],
                [[k, v.get("description", "")] for k, v in sorted(uc.get("responses", {}).items())],
            ))
    return "\n".join(ust + govde).rstrip() + "\n"


# ---------- Ayarlar ----------

def _kod_yorumlari(kaynak: str) -> dict[str, str]:
    """`Ayarlar` gövdesinde alanın üstündeki ve satır sonundaki yorumlar."""
    yorumlar: dict[str, str] = {}
    bekleyen: list[str] = []
    for satir in kaynak.splitlines():
        s = satir.strip()
        if s.startswith("#"):
            bekleyen.append(s.lstrip("# ").strip())
            continue
        e = re.match(r"([a-z_][a-z0-9_]*)\s*:\s*[^=#]+(?:=[^#]*)?(#\s*(.*))?$", s)
        if e and not s.startswith(("def ", "class ", "@")):
            ek = (e.group(3) or "").strip()
            yorumlar[e.group(1)] = " ".join(bekleyen + ([ek] if ek else []))
            bekleyen = []
        else:
            bekleyen = []
    return yorumlar


def _tur_adi(ek) -> str:
    metin = str(ek).replace("typing.", "")
    return re.sub(r"<class '([^']+)'>", r"\1", metin)


def ayarlar_belgesi() -> str:
    from pydantic_core import PydanticUndefined

    from bulutbelge_server.config import Ayarlar

    yorumlar = _kod_yorumlari(inspect.getsource(Ayarlar))
    onek = Ayarlar.model_config.get("env_prefix", "")
    satirlar = []
    for ad in sorted(Ayarlar.model_fields):
        alan = Ayarlar.model_fields[ad]
        varsayilan = "zorunlu" if alan.default is PydanticUndefined and alan.default_factory is None else (
            repr(alan.default_factory()) if alan.default_factory else repr(alan.default))
        if alan.default is None:
            varsayilan = "boş"
        satirlar.append([
            f"`{(onek + ad).upper()}`", _tur_adi(alan.annotation), f"`{varsayilan}`" if varsayilan != "boş" else "boş",
            alan.description or yorumlar.get(ad, ""),
        ])
    return "\n".join([
        "# Sunucu ayarları (BB_ ortam değişkenleri)\n",
        NOT,
        "Ayarlar ortam değişkeninden ya da `.env` dosyasından okunur. Gizli değerler repoya girmez. "
        "`uretim` ortamında eksik ya da örnek bırakılmış ayar varsa sunucu açılmaz. "
        "Bazı ayarlar yönetim panelinden de değişir.\n",
        _tablo(["Ortam değişkeni", "Tür", "Varsayılan", "Açıklama"], satirlar),
    ])


# ---------- Roller ----------

def roller_belgesi() -> str:
    from bulutbelge_server.roller import VARSAYILAN_ROLLER, YETKILER

    yetkiler = sorted(YETKILER)
    cikti = ["# Varsayılan roller ve yetkiler\n", NOT,
             "Roller ve yetkiler yönetim panelinden düzenlenebilir; aşağıdakiler ilk kurulumdaki varsayılanlardır.\n",
             "## Roller\n",
             _tablo(["Kod", "Ad", "Açıklama"], [[f"`{r['kod']}`", r["ad"], r["aciklama"]] for r in VARSAYILAN_ROLLER]),
             "## Yetki açıklamaları\n",
             _tablo(["Yetki", "Ad", "Açıklama"], [[f"`{k}`", YETKILER[k]["ad"], YETKILER[k]["aciklama"]] for k in yetkiler]),
             "## Rol–yetki tablosu\n",
             _tablo(["Yetki"] + [f"`{r['kod']}`" for r in VARSAYILAN_ROLLER],
                    [[f"`{k}`"] + ["✓" if r["yetkiler"][k] else "—" for r in VARSAYILAN_ROLLER] for k in yetkiler])]
    return "\n".join(cikti)


# ---------- Veri türleri ----------

def veri_turleri_belgesi() -> str:
    from bulutbelge_core.rules import DATA_TYPES, DEFAULT_COLUMN_HEADERS, METHOD_LABELS

    satirlar = []
    for anahtar in sorted(DATA_TYPES):
        t = DATA_TYPES[anahtar]
        etiketler = dict(t.method_labels)
        yontemler = ", ".join(f"`{m}` ({etiketler.get(m, METHOD_LABELS.get(m, m))})" for m in t.methods)
        notlar = []
        if not t.default_enabled:
            notlar.append("varsayılan kapalı")
        if t.always_on:
            notlar.append("her zaman açık")
        satirlar.append([f"`{t.key}`", t.label, f"`{t.tag}`", yontemler, f"`{t.default_method}`", ", ".join(notlar)])
    sozluk = [[f"`{t}`", DATA_TYPES[t].label if t in DATA_TYPES else "", ", ".join(f"`{h}`" for h in sorted(DEFAULT_COLUMN_HEADERS[t]))]
              for t in sorted(DEFAULT_COLUMN_HEADERS)]
    return "\n".join([
        "# Veri türleri ve sütun başlığı sözlüğü\n", NOT,
        "## Veri türleri\n",
        _tablo(["Anahtar", "Ad", "Etiket", "Yöntemler", "Varsayılan yöntem", "Not"], satirlar),
        "## Varsayılan sütun başlığı sözlüğü\n",
        "Tablo sütunu başlığı bu sözlükle eşleşirse sütun o türde maskelenir. Eşleşme tam başlık üzerindendir; "
        "büyük/küçük harf, boşluk, alt çizgi, tire ve Türkçe karakter farkı yok sayılır "
        "(`adres_tipi` gibi bileşik başlıklar eşleşmez).\n",
        _tablo(["Veri türü", "Ad", "Başlıklar"], sozluk),
    ])


# ---------- Man sayfası ----------

def _roff(metin: str) -> str:
    """Düz metni groff için kaçışlar (ters bölü, tire, satır başı nokta/kesme)."""
    cikti = []
    for satir in metin.replace("**", "").replace("`", "").split("\n"):
        satir = satir.replace("\\", "\\e").replace("-", "\\-")
        if satir[:1] in (".", "'"):
            satir = "\\&" + satir
        cikti.append(satir)
    return "\n".join(cikti)


def _bolum(kilavuz: str, baslik: str) -> list[str]:
    """Kılavuzdaki `## baslik` bölümünün satırları (sonraki `## ` başlığına kadar)."""
    satirlar = kilavuz.split("\n")
    for i, s in enumerate(satirlar):
        if s == f"## {baslik}":
            son = next((j for j in range(i + 1, len(satirlar)) if satirlar[j].startswith("## ")), len(satirlar))
            return satirlar[i + 1:son]
    return []


def _kilavuz_roff(satirlar: list[str]) -> list[str]:
    """Kılavuzun küçük Markdown alt kümesi (paragraf, madde, kod çiti, ### başlık) → roff."""
    cikti: list[str] = []
    kod = False
    for s in satirlar:
        if s.startswith("```"):
            cikti.append(".fi" if kod else ".nf")
            kod = not kod
        elif kod:
            cikti.append(_roff(s))
        elif s.startswith("### "):
            cikti.append(".SS " + _roff(s[4:]))
        elif s.startswith("- "):
            cikti.append(".IP \\(bu 2\n" + _roff(s[2:]))
        elif s.startswith("|") or not s.strip():
            continue
        else:
            cikti.append(".PP\n" + _roff(s))
    return cikti


def man_sayfasi() -> str:
    """`bulutbelge(1)`: argparse tanımları (cli.py) ve kılavuzdan, deterministik (tarih yok)."""
    from bulutbelge_engine import cli, kilavuz

    ana = cli._parser()
    alt = cli.subcommands(ana)
    c = ["'\\\" Bu dosya üretilir, elle düzenlemeyin: `python core/tools/belge_uret.py`",
         '.TH BULUTBELGE 1 "" "BulutBelge" "Kullanıcı Komutları"',
         ".SH AD", "bulutbelge \\- " + _roff(ana.description.split(": ", 1)[1].rstrip(".")),
         ".SH ÖZET", ".nf"]
    for ad, p in alt.items():
        kullanim = " ".join(p.format_usage().replace("usage:", "").split())
        c.append(_roff(kullanim.replace("bulutbelge " + ad, "bulutbelge " + ad)))
    c += [".fi", ".SH AÇIKLAMA", ".PP", _roff(ana.description),
          ".SH KOMUTLAR"]
    for ad, p in alt.items():
        c.append(".TP\n.B " + _roff(ad))
        c.append(_roff(next(a.help for a in ana._subparsers._group_actions[0]._choices_actions if a.dest == ad)))
        for a in p._actions:
            if a.option_strings and a.dest != "help":
                c.append(".RS\n.TP\n.B " + _roff(", ".join(a.option_strings)) + "\n" + _roff(a.help or "") + "\n.RE")
    c += [".SH ÇIKIŞ KODLARI"]
    for kod, (anlam, ne) in cli.EXIT_CODES.items():
        c.append(f".TP\n.B {kod}\n{_roff(anlam)}. Ajan: {_roff(ne)}.")
    c += [".SH JSON ÇIKTISI", ".PP", _roff("--json başarıda stdout'a tek satır JSON yazar.")]
    for ad, alanlar in cli.JSON_OUTPUTS.items():
        c.append(f".SS {ad} \\-\\-json")
        c += [f".TP\n.B {_roff(a)}\n{_roff(t)}. {_roff(d)}" for a, t, d in alanlar]
    c.append(".SS summary")
    c += [f".TP\n.B {_roff(a)}\n{_roff(t)}. {_roff(d)}" for a, t, d in cli.SUMMARY_FIELDS]
    c += [".SH ÖRNEKLER", ".nf"]
    for ornek in cli.EXAMPLES["main"]:
        c.append(_roff(ornek))
    c.append(".fi")
    metin = kilavuz.guide_text()
    for baslik, ust in (("Güvenlik modeli", "GÜVENLİK MODELİ"), ("Sınırlar", "SINIRLAR")):
        c.append(".SH " + ust)
        c += _kilavuz_roff(_bolum(metin, baslik))
    c += [".SH ŞUNA DA BAKIN", ".PP", "bulutbelge kilavuz, docs/AJAN\\-KOMUT\\-SATIRI.md"]
    return "\n".join(c) + "\n"


def uret() -> dict[str, str]:
    """Yol (depo köküne göre) → içerik; belleğte."""
    return {
        "docs/api/referans.md": api_referansi(),
        "docs/uretilen/ayarlar.md": ayarlar_belgesi(),
        "docs/uretilen/roller.md": roller_belgesi(),
        "docs/uretilen/veri-turleri.md": veri_turleri_belgesi(),
        "docs/uretilen/bulutbelge.1": man_sayfasi(),
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--denetle", action="store_true", help="yazmaz; diskteki dosyalar eskiyse 1 döner")
    a = p.parse_args(argv)
    eskiler = []
    for yol, icerik in uret().items():
        hedef = KOK / yol
        if a.denetle:
            if not hedef.is_file() or hedef.read_text(encoding="utf-8") != icerik:
                eskiler.append(yol)
            continue
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_text(icerik, encoding="utf-8", newline="\n")
        print(f"yazıldı: {yol}")
    if eskiler:
        print("Eski belge: " + ", ".join(eskiler) + "\npython core/tools/belge_uret.py çalıştırın")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
