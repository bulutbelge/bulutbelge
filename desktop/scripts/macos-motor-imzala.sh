#!/usr/bin/env bash
# macOS: paketlenmiş motorun (src-tauri/binaries/engine) içindeki tüm Mach-O dosyalarını imzalar. Tauri yalnızca
# uygulamanın kendi ikilisini imzalar; kaynak olarak eklenen motor imzalanmazsa Apple notarizasyonu reddeder.
#
#   bash desktop/scripts/macos-motor-imzala.sh "<imza kimliği>" [motor-klasörü]
#
# Kimlik: "Developer ID Application: <Kurum> (<TAKIM>)" ya da yerel deneme için "-" (ad-hoc).
# Sertleştirilmiş çalışma zamanı (--options runtime) ve zaman damgası notarizasyon için zorunludur; ad-hoc imzada
# zaman damgası alınmaz. İçten dışa imzalanır: önce kitaplıklar, en son motorun kendisi.
set -euo pipefail
KIMLIK="${1:?imza kimliği gerekli}"
KLASOR="${2:-$(cd "$(dirname "$0")/.." && pwd)/src-tauri/binaries/engine}"
IZINLER="$(cd "$(dirname "$0")/.." && pwd)/src-tauri/macos/motor.entitlements"
[ -d "$KLASOR" ] || { echo "Motor klasörü yok: $KLASOR" >&2; exit 2; }
ZAMAN=(--timestamp); [ "$KIMLIK" = "-" ] && ZAMAN=(--timestamp=none)

ANA="$KLASOR/bulutbelge-engine"
sayi=0
while IFS= read -r -d '' f; do
  [ "$f" = "$ANA" ] && continue
  if file -b "$f" | grep -q "Mach-O"; then
    case "$f" in
      *.framework/*)
        # PyInstaller'ın Python.framework kopyasında Info.plist yok; codesign yerinde "bundle format is ambiguous"
        # der. Dosya framework dışındaki geçici bir kopyada imzalanıp yerine konur (imza dosyanın içindedir).
        gecici="$(mktemp -d)/$(basename "$f")"
        cp -p "$f" "$gecici"
        codesign --force --sign "$KIMLIK" --options runtime "${ZAMAN[@]}" "$gecici"
        cp -p "$gecici" "$f"; rm -rf "$(dirname "$gecici")"
        ;;
      *) codesign --force --sign "$KIMLIK" --options runtime "${ZAMAN[@]}" "$f" ;;
    esac
    sayi=$((sayi + 1))
  fi
done < <(find "$KLASOR" -type f -print0)
codesign --force --sign "$KIMLIK" --options runtime "${ZAMAN[@]}" --entitlements "$IZINLER" "$ANA"
codesign --verify --strict "$ANA"
echo "Motor imzalandı: $sayi kitaplık + bulutbelge-engine (kimlik: $([ "$KIMLIK" = "-" ] && echo ad-hoc || echo Developer ID))"
