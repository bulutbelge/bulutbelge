"""Ajan için komut satırı (karar: docs/kararlar/2026-11-05-ajan-yerel-kullanim.md).

    python -m bulutbelge_engine.cli read  <dosya>  [--profil ID] [--ajan AD] [--json]
    python -m bulutbelge_engine.cli mask  <dosya>  [--hedef YOL] [--profil ID] [--ajan AD] [--json]
    python -m bulutbelge_engine.cli folders [--json]

Kurallar (kodda korunur):
- Okuma maskeli döner: belge maskelenir, metin maskeli kopyadan çıkarılır.
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
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

APP_ID = "com.proteksistem.bulutbelge"
DEV_ENV = "BULUTBELGE_GELISTIRME"
# --ajan değeri işlem günlüğüne ve CSV dışa aktarımına girer: güvenli karakter kümesi (F15).
_AGENT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

EXIT_OK, EXIT_ERROR, EXIT_USAGE, EXIT_REFUSED, EXIT_LOG = 0, 1, 2, 3, 4

# Çıkış kodları: kod -> (anlamı, ajan ne yapmalı). Metinler docs/AJAN-KOMUT-SATIRI.md'deki
# "Çıkış kodları" tablosuyla birebir aynıdır (test denetler); --help ve man sayfası buradan üretilir.
EXIT_CODES: dict[int, tuple[str, str]] = {
    EXIT_OK: ("Başarılı", "Devam et"),
    EXIT_ERROR: (
        "Belge ya da işlem hatası (bozuk dosya, desteklenmeyen biçim, **kaçak denetimi**)",
        "Hata mesajını kullanıcıya ilet; dosyayı başka yoldan okuma",
    ),
    EXIT_USAGE: ("Kullanım hatası (yanlış argüman, kural takımı yok)", "Komutu düzelt"),
    EXIT_REFUSED: (
        "İzin yok: dosya izinli klasör dışında, yazma izni yok, kasa koşulu",
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

# Komut -> --json çıktısının üst düzey alanları: (alan, tür, açıklama).
JSON_OUTPUTS: dict[str, list[tuple[str, str, str]]] = {
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
        lines += [f"    {a:<13} {t:<27} {d}" for a, t, d in SUMMARY_FIELDS]
    return "\n".join(lines)


EXAMPLES: dict[str, list[str]] = {
    "main": [
        "bulutbelge folders",
        'bulutbelge read "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code',
        'bulutbelge mask "C:\\Belgeler\\ornek_basvuru.pdf" --ajan claude-code --json',
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
    "kilavuz": ["bulutbelge kilavuz", "bulutbelge kilavuz --yonerge"],
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
        description="BulutBelge ajan komutu: izinli klasörlerde maskeli okuma ve maskeli kopya yazma.",
        epilog=_epilog("main") + "\n\nKomutlar için: bulutbelge <komut> --help",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--veri-klasoru",
        help=f"Uygulamanın ayar klasörü; yalnızca geliştirme modunda ({DEV_ENV}=1). Varsayılan: masaüstü uygulamasınınki",
    )
    sub = p.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--profil", help="Kural takımı kimliği (varsayılan: Ayarlar'da ajan için seçilen)")
    common.add_argument("--ajan", help="Ajanın adı (günlüğe yazılır), ör. claude-code")
    common.add_argument("--json", action="store_true", help="Çıktıyı JSON olarak ver")

    raw = argparse.RawDescriptionHelpFormatter
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
    k = sub.add_parser("kilavuz", help="Ajan kılavuzunu yazdırır (kurulum, komutlar, çıkış kodları, hazır yönerge)",
                       epilog=_epilog("kilavuz"), formatter_class=raw)
    k.add_argument("--yonerge", action="store_true", help="Yalnızca ajanın talimat dosyasına eklenecek hazır yönergeyi yazdır")
    return p


def _profile(settings_mod: Any, wanted: str | None, agent_cfg: dict[str, Any]) -> dict[str, Any]:
    s = settings_mod.load_settings()
    pid = wanted or agent_cfg.get("profile") or s["active"]
    for p in s["profiles"]:
        if p["id"] == pid:
            return p
    raise CliError("invalid_params", f"Kural takımı bulunamadı: {pid}", EXIT_USAGE)


def _summary(op: str, source: str, profile: dict[str, Any], result: dict[str, Any], target: str | None) -> dict[str, Any]:
    from bulutbelge_core.rules import DATA_TYPES

    counts = result.get("counts") or {}
    return {
        "islem": op,
        "kaynak": source,
        "hedef": target,
        "kural_takimi": profile["name"],
        "maskelenen": int(result.get("masked") or sum(counts.values())),
        "turler": {DATA_TYPES[k].label if k in DATA_TYPES else k: n for k, n in counts.items()},
        "uyarilar": list(result.get("warnings") or []),
        "not": result.get("changed"),
    }


def _record_recent(settings_mod: Any, source: str, profile: dict[str, Any], result: dict[str, Any], agent: str | None) -> None:
    """Ajanın yazdığı maskeli kopyayı arayüzdeki "Son yapılanlar" listesine ekler ("Ajan" etiketiyle).

    Yardımcı kayıttır: eklenemezse işlem başarısız sayılmaz (denetim kaydı işlem günlüğündedir).
    """
    import time

    from bulutbelge_core.rules import DATA_TYPES

    try:
        counts = result.get("counts") or {}
        settings_mod.history_add(
            {
                "entry": {
                    "path": source,
                    "target": result["target"],
                    "count": int(result.get("masked") or sum(counts.values())),
                    "at": int(time.time() * 1000),
                    "profileName": profile["name"],
                    "byType": [
                        {"type": k, "label": DATA_TYPES[k].label if k in DATA_TYPES else k, "count": n}
                        for k, n in counts.items()
                    ],
                    "agent": agent or "ajan",
                }
            }
        )
    except Exception:  # noqa: BLE001 - yardımcı kayıt
        pass


def _print_summary(summary: dict[str, Any], out) -> None:
    out.write("--- BulutBelge özeti ---\n")
    out.write(f"İşlem: {summary['islem']}\nKaynak: {summary['kaynak']}\n")
    if summary["hedef"]:
        out.write(f"Maskeli kopya: {summary['hedef']}\n")
    out.write(f"Kural takımı: {summary['kural_takimi']}\nMaskelenen: {summary['maskelenen']}\n")
    for label, n in summary["turler"].items():
        out.write(f"  - {label}: {n}\n")
    if summary["not"]:
        out.write(f"Not: {summary['not']}\n")
    for w in summary["uyarilar"]:
        out.write(f"Uyarı: {w}\n")


def run(argv: list[str], stdout, stderr) -> int:
    try:
        args = _parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_USAGE if exc.code else EXIT_OK

    if args.command == "kilavuz":
        # Statik metin: ayar klasörü, izin ve işlem günlüğü gerektirmez (belgeye dokunmaz).
        from . import kilavuz

        stdout.write(kilavuz.guide_prompt(kilavuz.command_here()) if args.yonerge else kilavuz.guide_text())
        return EXIT_OK

    agent_name = getattr(args, "ajan", None)
    if agent_name and not _AGENT_NAME.fullmatch(agent_name):
        stderr.write(
            "Hata [invalid_params]: --ajan yalnızca harf, rakam, nokta, alt çizgi ve tire içerebilir "
            "ve harf ya da rakamla başlamalıdır (ör. claude-code).\n"
        )
        return EXIT_USAGE

    # Politika (ajan.json, settings.json, kasa, işlem günlüğü) masaüstü uygulamasının klasöründen
    # okunur; çağıran (ajan) bu klasörü seçemez (karar: docs/kararlar/2026-11-21-ajan-cli-veri-klasoru.md).
    # --veri-klasoru ve BULUTBELGE_DATA_DIR yalnızca açık geliştirme/test modunda kabul edilir.
    if dev_mode():
        data = args.veri_klasoru or os.environ.get("BULUTBELGE_DATA_DIR") or str(default_data_dir())
    else:
        if args.veri_klasoru:
            stderr.write(
                "Hata [invalid_params]: --veri-klasoru yalnızca geliştirme modunda kullanılabilir "
                f"({DEV_ENV}=1). Ajan komutu masaüstü uygulamasının ayarlarını kullanır.\n"
            )
            return EXIT_USAGE
        data = str(default_data_dir())
        given = os.environ.get("BULUTBELGE_DATA_DIR")
        if given and Path(given) != Path(data):
            stderr.write(
                f"Uyarı: BULUTBELGE_DATA_DIR yok sayıldı (yalnızca {DEV_ENV}=1 ile geçerli); "
                "masaüstü uygulamasının ayarları kullanılıyor.\n"
            )
    os.environ["BULUTBELGE_DATA_DIR"] = str(Path(data))

    from . import commands, journal, settings
    from .protocol import EngineError

    try:
        agent_cfg = settings.load_agent()
        if args.command == "folders":
            info = {k: agent_cfg[k] for k in ("folders", "allow_write")}
            if args.json:
                stdout.write(json.dumps(info, ensure_ascii=False) + "\n")
            else:
                stdout.write("İzinli klasörler:\n" + ("".join(f"  {f}\n" for f in info["folders"]) or "  (yok)\n"))
                stdout.write(f"Maskeli kopya yazma izni: {'var' if info['allow_write'] else 'yok'}\n")
            return EXIT_OK

        journal.CALLER.set(("ajan", (args.ajan or "ajan")[:60]))
        source = str(Path(args.dosya).absolute())
        op = "okuma" if args.command == "read" else "maskeleme"
        profile = _profile(settings, args.profil, agent_cfg)
        folders = agent_cfg["folders"]

        def refuse(code: str, message: str) -> None:
            journal.refuse(op, code, message, source=source, profile=profile["name"])

        if not folders:
            refuse("not_allowed", "Ajan için izinli klasör yok. BulutBelge › Ayarlar › Ajan erişimi bölümünden ekleyin.")
        if not settings.agent_allows(source, folders):
            refuse("not_allowed", "Dosya izinli klasörlerin dışında")
        if settings.VAULT.path.exists() and not agent_cfg["allow_without_terms"]:
            # Özel ifadeler şifreli kasada; ajan komutu kasayı açamaz. Kullanıcı açıkça izin vermedikçe
            # özel ifadeleri (kişi, müşteri adları) uygulamadan okuma yapılmaz.
            refuse(
                "terms_unavailable",
                "Özel ifade kasası var ama ajan komutu kasayı açamaz. Özel ifadeler olmadan çalışmasına "
                "Ayarlar › Ajan erişimi bölümünden izin verin.",
            )
        rules = {**profile, "terms": [], "profile_name": profile["name"]}

        if args.command == "read":
            from bulutbelge_core.readout import read_masked

            @commands._user_errors
            def do_read(params: dict[str, Any]) -> dict[str, Any]:
                r = read_masked(source, commands._rules(params))
                return {"text": r.text, "format": r.format, "masked": r.masked, "counts": r.counts, "warnings": r.warnings}

            result = journal.run(
                "okuma",
                lambda: do_read({"rules": rules}),
                source=source,
                profile=profile["name"],
                counts_of=lambda r: r["counts"],
            )
            summary = _summary("okuma", source, profile, result, None)
            if args.json:
                stdout.write(json.dumps({"ok": True, "text": result["text"], "summary": summary}, ensure_ascii=False) + "\n")
            else:
                stdout.write(result["text"].rstrip("\n") + "\n\n")
                _print_summary(summary, stdout)
            return EXIT_OK

        # mask
        if not agent_cfg["allow_write"]:
            refuse("write_not_allowed", "Ajanın maskeli kopya yazmasına izin verilmemiş (Ayarlar › Ajan erişimi)")
        from bulutbelge_core.pdf import default_target

        target = str(Path(args.hedef).absolute()) if args.hedef else default_target(source)
        if not settings.agent_allows(target, folders):
            refuse("not_allowed", "Hedef izinli klasörlerin dışında")
        result = journal.run(
            "maskeleme",
            lambda: commands._doc_mask_checked({"source": source, "target": target, "rules": rules}),
            source=source,
            profile=profile["name"],
            counts_of=lambda r: r.get("counts") or {},
            target_of=lambda r: r["target"],
        )
        if not settings.agent_allows(result["target"], folders):
            # Çekirdek yolu değiştirdiyse (uzantı, var olan dosya) yine izinli klasörde olmalı.
            Path(result["target"]).unlink(missing_ok=True)
            raise CliError("not_allowed", "Kopya izinli klasörün dışına düştü; silindi", EXIT_REFUSED)
        summary = _summary("maskeleme", source, profile, result, result["target"])
        _record_recent(settings, source, profile, result, args.ajan)
        if args.json:
            stdout.write(json.dumps({"ok": True, "summary": summary}, ensure_ascii=False) + "\n")
        else:
            _print_summary(summary, stdout)
        return EXIT_OK
    except CliError as exc:
        stderr.write(f"Hata ({exc.code}): {exc.message}\n")
        return exc.exit_code
    except EngineError as exc:
        stderr.write(f"Hata ({exc.code}): {exc.message}\n")
        if exc.code == "log_unwritable":
            return EXIT_LOG
        if exc.code in journal.REFUSALS:
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
