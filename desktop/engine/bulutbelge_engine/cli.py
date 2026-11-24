"""Ajan için komut satırı (karar: docs/kararlar/2026-11-05-ajan-yerel-kullanim.md).

    python -m bulutbelge_engine.cli scan  <dosya>  [--profil ID] [--ajan AD] [--json]
    python -m bulutbelge_engine.cli read  <dosya>  [--profil ID] [--ajan AD] [--json]
    python -m bulutbelge_engine.cli mask  <dosya>  [--hedef YOL] [--profil ID] [--ajan AD] [--json]
    python -m bulutbelge_engine.cli folders [--json]
    python -m bulutbelge_engine.cli mcp     (yerel MCP sunucusu, yalnızca stdio; bkz. mcp.py)

Kurallar (kodda korunur; iç işlevler ajan.py'de, yerel MCP sunucusuyla ortak):
- Tarama (scan) değer döndürmez: yalnızca tür bazında sayılar, sayfa sayısı ve uyarılar.
- Okuma maskeli döner: belge maskelenir, metin maskeli kopyadan çıkarılır.
- Ajan için atanan kural takımı üst sınırdır; --profil daha gevşek takım seçemez.
- Yalnızca kullanıcının Ayarlar › Ajan erişimi bölümünde tanımladığı klasörlerde çalışır.
- Yazma (mask) kullanıcı ayrıca izin verdiyse yapılır; her zaman yeni dosyaya, mevcut dosya
  üzerine yazılmaz. Maske kaldırma (takma ad geri çevirme) bu komutta yoktur.
- Her çağrı (reddedilenler dahil) çağıran=ajan olarak işlem günlüğüne yazılır; günlük
  yazılamazsa işlem yapılmaz.
- stdout yalnızca maskeli içerik ve işlem özetini taşır; hatalar stderr'e yazılır.

Çıkış kodları: 0 başarılı, 1 belge/işlem hatası, 2 kullanım hatası, 3 izin yok (reddedildi),
4 işlem günlüğü yazılamıyor.
"""

from __future__ import annotations

import argparse
import contextvars
import json
import os
import sys
from pathlib import Path
from typing import Any

APP_ID = "com.proteksistem.bulutbelge"
DEV_ENV = "BULUTBELGE_GELISTIRME"
EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_REFUSED, EXIT_LOG = 0, 1, 2, 3, 4

# Çıkış kodları: kod -> (anlamı, ajan ne yapmalı). Metinler bulutbelge_engine/kilavuz.md'deki
# "Çıkış kodları" tablosuyla birebir aynıdır (test denetler); --help ve man sayfası buradan üretilir.
EXIT_CODES: dict[int, tuple[str, str]] = {
    EXIT_OK: ("Başarılı", "Devam et"),
    EXIT_ERROR: (
        "Belge ya da işlem hatası (bozuk dosya, desteklenmeyen biçim, **kaçak denetimi**, OCR kullanılamıyor)",
        "Hata mesajını kullanıcıya ilet; dosyayı başka yoldan okuma",
    ),
    EXIT_USAGE: ("Kullanım hatası (yanlış argüman, kural takımı yok)", "Komutu düzelt"),
    EXIT_REFUSED: (
        "İzin yok: dosya izinli klasör dışında, yazma izni yok, kasa koşulu, atanandan gevşek kural takımı, "
        "masaüstü uygulaması kurulu değil",
        "**Dur**, mesajı aynen ilet; izni aşmaya çalışma",
    ),
    EXIT_LOG: ("İşlem günlüğü yazılamıyor; güvenlik için işlem yapılmadı", "**Dur**, kullanıcıya bildir"),
}

# --json özet alanları: (alan, tür, açıklama). Kılavuzdaki "JSON çıktı şeması" tablosuyla aynıdır.
SUMMARY_FIELDS: list[tuple[str, str, str]] = [
    ("islem", "string", '"okuma" ya da "maskeleme"'),
    ("kaynak", "string", "Kaynak belgenin mutlak yolu"),
    ("hedef", "string | null", "Maskeli kopyanın yolu (yalnızca mask; read'de null)"),
    ("kural_takimi", "string", "Kullanılan kural takımının adı"),
    ("maskelenen", "integer", "Maskelenen değer sayısı"),
    ("turler", "object (string → integer)", "Veri türü adına göre maskelenen sayı"),
    ("uyarilar", "array of string", "Uyarılar (ör. OCR); yoksa boş liste"),
    ("not", "string | null", "İşlem notu; yoksa null"),
]

# scan --json özet alanları: değer yok, yalnızca sayılar. Kılavuzdaki "scan --json" tablosuyla aynıdır.
SCAN_FIELDS: list[tuple[str, str, str]] = [
    ("islem", "string", '"tarama"'),
    ("kaynak", "string", "Kaynak belgenin mutlak yolu"),
    ("kural_takimi", "string", "Kullanılan kural takımının adı"),
    ("bulunan", "integer", "Bulunan değer sayısı (maskelenmez, gösterilmez)"),
    ("turler", "object (string → integer)", "Veri türü adına göre bulunan sayı"),
    ("sayfa", "integer", "Sayfa sayısı (PDF/görsel sayfa, sunum slayt, arşiv dosya; diğerleri 1)"),
    ("uyarilar", "array of string", "Uyarılar (ör. OCR, özel nitelikli veri ipucu); yoksa boş liste"),
]

# Komut -> --json çıktısının üst düzey alanları: (alan, tür, açıklama).
JSON_OUTPUTS: dict[str, list[tuple[str, str, str]]] = {
    "scan": [
        ("ok", "boolean", "Başarıda her zaman true"),
        ("summary", "object", "Tarama özeti (alanlar aşağıda); değer ve metin yok"),
    ],
    "read": [
        ("ok", "boolean", "Başarıda her zaman true"),
        ("text", "string", "Belgenin maskeli metni"),
        ("summary", "object", "İşlem özeti (alanlar aşağıda)"),
    ],
    "mask": [
        ("ok", "boolean", "Başarıda her zaman true"),
        ("summary", "object", "İşlem özeti (alanlar aşağıda)"),
    ],
    "folders": [
        ("folders", "array of string", "İzinli klasörler"),
        ("allow_write", "boolean", "Maskeli kopya yazma izni"),
    ],
}


def exit_codes_help() -> str:
    """Çıkış kodları tablosu, --help epilog'u için düz metin."""
    lines = ["Çıkış kodları:"]
    for code, (meaning, action) in EXIT_CODES.items():
        lines.append(f"  {code}  {meaning.replace('**', '')}")
        lines.append(f"     Ajan: {action.replace('**', '')}")
    lines.append("Hatalar stderr'e 'Hata (kod): ...' olarak yazılır; --json yalnızca başarıda JSON verir.")
    return "\n".join(lines)


def _json_help(command: str) -> str:
    lines = ["--json çıktısı (tek satır JSON, stdout):"]
    lines += [f"  {a:<12} {t:<10} {d}" for a, t, d in JSON_OUTPUTS[command]]
    if command != "folders":
        lines.append("  summary alanları:")
        lines += [f"    {a:<13} {t:<27} {d}" for a, t, d in (SCAN_FIELDS if command == "scan" else SUMMARY_FIELDS)]
    return "\n".join(lines)


EXAMPLES: dict[str, list[str]] = {
    "main": [
        "bulutbelge folders",
        'bulutbelge scan "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge read "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge mask "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code --json',
    ],
    "scan": [
        'bulutbelge scan "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge scan "C:\\Belgeler\\ornek_tablo.xlsx" --json --ajan claude-code',
    ],
    "read": [
        'bulutbelge read "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge read "C:\\Belgeler\\ornek_tablo.xlsx" --json --ajan claude-code',
        'bulutbelge read "C:\\Belgeler\\ornek_dilekce.docx" --profil varsayilan',
    ],
    "mask": [
        'bulutbelge mask "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge mask "C:\\Belgeler\\ornek_basvuru.pdf" --hedef "C:\\Belgeler\\ornek_basvuru_gizli.pdf"',
        'bulutbelge mask "C:\\Belgeler\\ornek_tablo.xlsx" --json --ajan claude-code',
    ],
    "folders": ["bulutbelge folders", "bulutbelge folders --json"],
    "kilavuz": ["bulutbelge kilavuz", "bulutbelge kilavuz --yonerge", "bulutbelge kilavuz --skill"],
    "mcp": [
        "claude mcp add bulutbelge -- bulutbelge mcp",
        "BULUTBELGE_AJAN=cursor bulutbelge mcp",
    ],
}


def _epilog(command: str, with_codes: bool = True) -> str:
    parts = ["Örnekler:\n" + "\n".join(f"  {e}" for e in EXAMPLES[command])]
    if command in JSON_OUTPUTS:
        parts.append(_json_help(command))
    if with_codes:
        parts.append(exit_codes_help())
    parts.append("Ayrıntı: bulutbelge kilavuz")
    return "\n\n".join(parts)


def subcommands(parser: argparse.ArgumentParser) -> dict[str, argparse.ArgumentParser]:
    """Alt komut adı -> ayrıştırıcı (man sayfası üretimi için)."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            return dict(action.choices)
    return {}


def dev_mode() -> bool:
    """Geliştirme/test modu: yalnızca BULUTBELGE_GELISTIRME=1 iken ayar klasörü elle seçilebilir."""
    return os.environ.get(DEV_ENV) == "1"


def default_data_dir() -> Path:
    """Masaüstü uygulamasının (Tauri app_data_dir) kullandığı klasör."""
    if os.name == "nt":
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_ID
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_ID
    return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_ID


class CliError(Exception):
    def __init__(self, code: str, message: str, exit_code: int) -> None:
        super().__init__(message)
        self.code, self.message, self.exit_code = code, message, exit_code


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bulutbelge",
        description="BulutBelge ajan komutu: izinli klasörlerde değersiz tarama, maskeli okuma ve maskeli kopya yazma.",
        epilog=_epilog("main") + "\n\nKomutlar için: bulutbelge <komut> --help",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--veri-klasoru",
        help=f"Uygulamanın ayar klasörü; yalnızca geliştirme modunda ({DEV_ENV}=1). Varsayılan: masaüstü uygulamasınınki",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--profil",
        help="Kural takımı kimliği (varsayılan: Ayarlar'da ajan için seçilen). Yalnızca atanan takım ya da ondan sıkısı",
    )
    common.add_argument("--ajan", help="Ajanın adı (günlüğe yazılır), ör. claude-code")
    common.add_argument("--json", action="store_true", help="Çıktıyı JSON olarak ver")

    raw = argparse.RawDescriptionHelpFormatter
    sc = sub.add_parser("scan", parents=[common], help="Belgeyi değiştirmeden tarar; yalnızca sayılar (değer yok)",
                        epilog=_epilog("scan"), formatter_class=raw)
    sc.add_argument("dosya")
    r = sub.add_parser("read", parents=[common], help="Belgenin maskeli metnini yazdırır",
                       epilog=_epilog("read"), formatter_class=raw)
    r.add_argument("dosya")
    m = sub.add_parser("mask", parents=[common], help="Maskeli kopyayı yeni dosyaya yazar",
                       epilog=_epilog("mask"), formatter_class=raw)
    m.add_argument("dosya")
    m.add_argument("--hedef", help="Maskeli kopyanın yolu (varsayılan: kaynağın yanında _maskeli)")
    f = sub.add_parser("folders", help="İzinli klasörleri ve yazma iznini gösterir",
                       epilog=_epilog("folders"), formatter_class=raw)
    f.add_argument("--json", action="store_true")
    k = sub.add_parser("kilavuz", help="Ajan kılavuzunu yazdırır (kurulum, komutlar, çıkış kodları, hazır yönerge, beceri)",
                       epilog=_epilog("kilavuz"), formatter_class=raw)
    sub.add_parser(
        "mcp",
        help="Yerel MCP sunucusu: yalnızca stdio, ağ portu açmaz (araçlar: folders, scan, read, mask)",
        description="Ajan aracının alt süreç olarak başlattığı MCP sunucusu: yalnızca stdio, ağ portu açmaz. Araçlar komut satırıyla aynı izin "
        "denetimini ve işlem günlüğünü kullanır. Ajan adı BULUTBELGE_AJAN ortam değişkeninden ya da istemcinin adından.",
        epilog=_epilog("mcp", with_codes=False),
        formatter_class=raw,
    )
    kg = k.add_mutually_exclusive_group()
    kg.add_argument("--yonerge", action="store_true", help="Yalnızca ajanın talimat dosyasına (CLAUDE.md, AGENTS.md) eklenecek hazır yönergeyi yazdır")
    kg.add_argument("--skill", action="store_true", help="Claude Code beceri dosyasını (SKILL.md) yazdır")
    return p


def _print_scan(summary: dict[str, Any], out) -> None:
    from .ajan import format_scan

    out.write(format_scan(summary))


def _print_summary(summary: dict[str, Any], out) -> None:
    from .ajan import format_summary

    out.write(format_summary(summary))


def run(argv: list[str], stdout, stderr, stdin=None) -> int:
    # Ayrı bağlamda: çağıran bilgisi (journal.CALLER = ajan) aynı süreçteki sonraki işlemlere sızmasın.
    return contextvars.copy_context().run(_run, argv, stdout, stderr, stdin)


def ajan_valid(name: str) -> bool:
    from .ajan import valid_agent_name

    return valid_agent_name(name)


def select_data_dir(flag: str | None, stderr) -> str | None:
    """Politika klasörünü (ajan.json, settings.json, kasa, işlem günlüğü) seçer ve BULUTBELGE_DATA_DIR'e yazar.

    Masaüstü uygulamasının klasörüdür; çağıran (ajan) bu klasörü seçemez (karar:
    docs/kararlar/2026-11-21-ajan-cli-veri-klasoru.md). --veri-klasoru ve BULUTBELGE_DATA_DIR yalnızca
    açık geliştirme/test modunda kabul edilir. Bayrak geliştirme modu dışında verildiyse None (kullanım hatası).
    """
    if dev_mode():
        data = flag or os.environ.get("BULUTBELGE_DATA_DIR") or str(default_data_dir())
    else:
        if flag:
            stderr.write(
                "Hata [invalid_params]: --veri-klasoru yalnızca geliştirme modunda kullanılabilir "
                f"({DEV_ENV}=1). Ajan komutu masaüstü uygulamasının ayarlarını kullanır.\n"
            )
            return None
        data = str(default_data_dir())
        given = os.environ.get("BULUTBELGE_DATA_DIR")
        if given and Path(given) != Path(data):
            stderr.write(
                f"Uyarı: BULUTBELGE_DATA_DIR yok sayıldı (yalnızca {DEV_ENV}=1 ile geçerli); "
                "masaüstü uygulamasının ayarları kullanılıyor.\n"
            )
    os.environ["BULUTBELGE_DATA_DIR"] = str(Path(data))
    return data


def _run(argv: list[str], stdout, stderr, stdin=None) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    if args.command == "kilavuz":
        # Statik metin: ayar klasörü, izin ve işlem günlüğü gerektirmez (belgeye dokunmaz).
        from . import kilavuz

        if args.skill:
            stdout.write(kilavuz.skill_text(kilavuz.command_here()))
        else:
            stdout.write(kilavuz.guide_prompt(kilavuz.command_here()) if args.yonerge else kilavuz.guide_text())
        return EXIT_OK

    agent_name = getattr(args, "ajan", None)
    if agent_name and not ajan_valid(agent_name):
        stderr.write(
            "Hata [invalid_params]: --ajan yalnızca harf, rakam, nokta, alt çizgi ve tire içerebilir "
            "ve harf ya da rakamla başlamalıdır (ör. claude-code).\n"
        )
        return EXIT_USAGE

    if select_data_dir(args.veri_klasoru, stderr) is None:
        return EXIT_USAGE

    if args.command == "mcp":
        from . import mcp

        if stdout is sys.__stdout__ and stdin is None:
            mcp.serve_stdio()
        else:
            mcp.serve(stdin if stdin is not None else sys.stdin, stdout)
        return EXIT_OK

    from . import ajan, journal
    from .protocol import EngineError

    try:
        if args.command == "folders":
            info = ajan.folders()
            if args.json:
                stdout.write(json.dumps(info, ensure_ascii=False) + "\n")
            else:
                stdout.write("İzinli klasörler:\n" + ("".join(f"  {f}\n" for f in info["folders"]) or "  (yok)\n"))
                stdout.write(f"Maskeli kopya yazma izni: {'var' if info['allow_write'] else 'yok'}\n")
            return EXIT_OK

        journal.CALLER.set(("ajan", (args.ajan or "ajan")[:60]))
        if args.command == "scan":
            summary = ajan.scan(args.dosya, args.profil)
            if args.json:
                stdout.write(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False) + "\n")
            else:
                _print_scan(summary, stdout)
            return EXIT_OK

        if args.command == "read":
            result = ajan.read(args.dosya, args.profil)
            if args.json:
                stdout.write(json.dumps({"ok": True, **result}, ensure_ascii=False) + "\n")
            else:
                stdout.write(result["text"].rstrip("\n") + "\n\n")
                _print_summary(result["summary"], stdout)
            return EXIT_OK

        result = ajan.mask(args.dosya, args.hedef, args.profil, args.ajan)
        if args.json:
            stdout.write(json.dumps({"ok": True, **result}, ensure_ascii=False) + "\n")
        else:
            _print_summary(result["summary"], stdout)
        return EXIT_OK
    except CliError as exc:
        stderr.write(f"Hata ({exc.code}): {exc.message}\n")
        return exc.exit_code
    except EngineError as exc:
        stderr.write(f"Hata ({exc.code}): {exc.message}\n")
        if exc.code == "log_unwritable":
            return EXIT_LOG
        if exc.code in journal.REFUSALS or exc.code == ajan.APP_NOT_INSTALLED:
            return EXIT_REFUSED
        return EXIT_USAGE if exc.code in ("invalid_params", "no_data_dir") else EXIT_ERROR
    except Exception as exc:  # noqa: BLE001 - mesaj içerik taşıyabilir; yalnızca tür
        stderr.write(f"Hata (internal): {type(exc).__name__}\n")
        return EXIT_ERROR


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    if argv[:1] == ["cli"]:  # `bulutbelge-engine cli read ...` biçimi de çalışsın
        argv = argv[1:]
    sys.exit(run(argv, sys.stdout, sys.stderr))


if __name__ == "__main__":
    main()
