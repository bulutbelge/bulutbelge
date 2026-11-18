import sys

from .protocol import serve


def main() -> None:
    # Argüman verilirse motor komut satırı olarak çalışır (paketli sürümde `bulutbelge-engine read <dosya>`);
    # argümansız çalışırsa arayüzün JSON protokolünü sunar.
    if len(sys.argv) > 1:
        from .cli import main as cli_main

        cli_main()
        return
    # Windows'ta varsayılan kod sayfası yerine her iki yönde UTF-8 kullan.
    # utf-8-sig: PowerShell'in başa eklediği BOM'u kabul eder.
    sys.stdin.reconfigure(encoding="utf-8-sig")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    serve(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
