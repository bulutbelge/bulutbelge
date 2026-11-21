# Marka dosyaları

Tescilli "bulut belge" markasının görsel dosyaları. Tescil: TÜRKPATENT 2018/97096 (koruma 31.10.2028'e kadar; ayrıntı `docs/markalar.md`, iç belge). Kullanım kuralları: marka kullanım politikası (`TRADEMARKS.md`, yayımlanınca).

| Dosya | Ne | Nerede kullanılır |
|---|---|---|
| `bulutbelge-logo.svg` | Tescilli kelime-logo ("bulut" gri-mavi, "belge" kırmızı) | Site başlığı (`site/logo.svg`), uygulama ve panel başlığı (`desktop/src/marka.ts`), ürün belgesi (`dokuman/packages/gitbook-arayuz/src/marka.ts`) |
| `simge.svg` | Uygulama simgesi: logodan türetilen "bb" (macOS için kenar paylı) | `desktop/src-tauri/icons/` (aşağıdaki komutla üretilir), panel `icon-192/512.png` |
| `simge-kucuk.svg` | Aynı simge, kenar paysız (favicon) | `site/favicon.svg`, `web/public/favicon.svg`, ürün belgesi favicon'ları |

Renkler: gri-mavi `#54688D`, kırmızı `#C5181C` (tescil görselinden ölçüldü). Koyu temada okunurluk için açık tonlar kullanılır: `#9FB1D3`, `#F0525A` (`desktop/src/App.css`, `--marka-mavi`, `--marka-kirmizi`).

Kaynak: logo, TÜRKPATENT kaydındaki 814×814 piksellik görselden konturları izlenerek SVG'ye çevrildi (yazı tipi kullanılmadı). Tasarımcıdan gelen asıl vektör dosyası bulunursa bu dosyalar onunla değiştirilir. Logonun biçimi, oranı ve renkleri değiştirilmez.

Uygulama simgelerini yeniden üretmek (masaüstü klasöründe): `simge.svg` 1024×1024 saydam PNG'ye çevrilir, sonra `npx tauri icon <png> -o src-tauri/icons`; Android ve iOS klasörleri kullanılmaz, silinir.
