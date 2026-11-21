# Üçüncü taraf lisans bildirimi (TAKIP 1.83)

BulutBelge masaüstü uygulaması ve `core/`, GNU Affero Genel Kamu Lisansı sürüm 3 (AGPL-3.0) altındadır (bkz. `LICENSE`). Telif hakkı: Copyright (c) 2026 PROTEK YAZILIM SİSTEM DANIŞMANLIK BİLG. SAN. VE TİC. LTD. ŞTİ. Karar 17 Kasım 2026'da oturum sahibi tarafından verildi; 21 Kasım 2026'da ürün sahibi hukukçu görüşü istenmeyeceğini kararlaştırdı (`docs/kararlar/2026-11-21-hukukcu-ve-acma-hazirligi.md`). İstenirse lisans değiştirilebilir.
Sürümler 17 Kasım 2026'da geliştirme ortamından okundu; yayın sırasında kilit dosyalarından yeniden üretilmeli (aşağıdaki "Yenileme").

## Sorumluluk reddi (TAKIP 1.94)

BulutBelge yardımcı bir araçtır; kişisel bilgileri %100 doğrulukla bulamayabilir ya da maskeleyemeyebilir. "Bulunamadı", "maskelendi" ya da "iz kalmadı" bildirimleri kesin sonuç değildir; çıktıyı paylaşmadan önce kendiniz gözden geçirin. Yazılım AGPL-3.0'ın 15. ve 16. maddeleri uyarınca "olduğu gibi", hiçbir garanti olmadan sunulur. Kullanım koşullarının tamamı: <https://bulutbelge.com/kosullar.html> (kurulum programında da gösterilir). `LICENSE` dosyası lisansın değiştirilmemiş metnidir; bu not onun parçası değildir.

## Python (çekirdek ve masaüstü motoru)

| Bileşen | Lisans | Not |
|---|---|---|
| PyMuPDF (MuPDF, içinde Tesseract OCR) | AGPL-3.0 ya da Artifex ticari lisansı | Projeyi AGPL-3.0'a bağlayan bileşen; ticari lisans ücretli ve teklifle |
| cryptography | Apache-2.0 ya da BSD-3-Clause | |
| regex | Apache-2.0 ve CNRI-Python | |
| Pillow | MIT-CMU (HPND benzeri) | |
| lxml | BSD-3-Clause | libxml2 ve libxslt (MIT) paketle gelir |
| opencv-python-headless | Apache-2.0 | Tekerlek içindeki FFmpeg bileşenleri LGPL-2.1: paketlemede ayrı denetlenmeli |
| NumPy | BSD-3-Clause (ayrıca 0BSD, MIT, Zlib, CC0-1.0 parçaları) | |

## OCR dil dosyaları

| Bileşen | Lisans | Not |
|---|---|---|
| Tesseract `eng` ve `tur` eğitilmiş veri (`desktop/engine/tessdata`) | Apache-2.0 | Kaynak ve özet `tessdata_indir.py` ile doğrulanır; yayın öncesi kaynak deposundaki lisans dosyası teyit edilmeli |

## Arayüz (JavaScript)

| Bileşen | Lisans |
|---|---|
| React, React DOM | MIT |
| docx-preview | Apache-2.0 |
| @tauri-apps/api, plugin-dialog, plugin-opener | Apache-2.0 ya da MIT |

## Kabuk (Rust)

| Bileşen | Lisans | Not |
|---|---|---|
| Tauri 2 ve eklentileri | Apache-2.0 ya da MIT | |
| serde, serde_json | MIT ya da Apache-2.0 | |
| ureq, native-tls | MIT ya da Apache-2.0 | Yalnızca güncelleme denetimi için |

Rust bileşenlerinin tam listesi bu taslakta elle yazılmadı; yayın öncesi `cargo about` ya da `cargo license` çıktısı eklenmeli.

## Derleme araçları (dağıtıma girmez)

PyInstaller (GPL-2.0 ve önyükleyici istisnası; çıktıya lisans bulaştırmaz), Vite, TypeScript. Derleme çıktısındaki motor paketi PyInstaller önyükleyicisini içerir; istisna metni yayın öncesi doğrulanmalı.

## Üretilmiş tam liste (21 Kasım 2026)

Paketlerin tamamı (Python 27, JavaScript 20, Rust 464) lisansa göre gruplanmış olarak [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) içindedir; `python core/tools/lisans_listesi_uret.py > THIRD-PARTY-LICENSES.md` ile yenilenir. Paylaşımlı lisanslı olanlar ve notlar:

- **MPL-2.0** (Rust: cssparser, cssparser-macros, dtoa-short, option-ext, selectors): dosya düzeyinde paylaşımlı lisans; değiştirilmeden kullanılır, kaynakları crates.io'dadır.
- **İkili lisanslı:** jszip (MIT veya GPL-3.0-or-later; MIT seçilir), r-efi (MIT, Apache-2.0 veya LGPL-2.1-or-later; MIT ya da Apache-2.0 seçilir).
- **pymupdf4llm ve pymupdf-layout:** PyMuPDF 2.1 bunları bağımlılık olarak bildirir ve kilit dosyasında (`requirements.lock`) yer alır. Kodumuz bunları içe aktarmaz ve paketlenen macOS motor klasöründe bulunmadığı doğrulanmıştır. pymupdf-layout, Artifex tarafından ticari eklenti olarak sunulur (PyPI sayfasındaki ifade); paketlenirse ticari lisans gerekir. Windows ve Linux derlemelerinde de yok olduğu CI çıktısında doğrulanmalıdır (TAKIP T4).
- **PyInstaller** (GPL-2.0, önyükleyici istisnasıyla) ve derleme araçları (pip, setuptools) dağıtıma girmez ya da çıktıya lisans bulaştırmaz.

## FFmpeg (LGPL-2.1) kaynak kodu ve değiştirme hakkı

`opencv-python-headless` 4.14.0.94 tekerleği FFmpeg kütüphanelerini (LGPL-2.1) içinde taşır. FFmpeg kaynak kodu: https://ffmpeg.org/download.html. Tekerleği üreten proje ve derleme betikleri: https://github.com/opencv/opencv-python (sürüm 4.14.0.94). Kurulum paketinde motor klasör olarak paketlenir (PyInstaller `--onedir`): FFmpeg kütüphaneleri ayrı dosyalar olarak durur, kullanıcı bunları aynı arayüze sahip bir sürümle değiştirebilir. Paketlenen tam FFmpeg sürümü yenileme adımında doğrulanıp buraya yazılacak.

## Yenileme (yayın öncesi)

1. Hepsi tek komutla: `python core/tools/lisans_listesi_uret.py > THIRD-PARTY-LICENSES.md` (motor sanal ortamı, `npm ci` ve Rust araçları kurulu olmalı; çıktı Python, JavaScript ve Rust'ı kapsar).
2. `git diff THIRD-PARTY-LICENSES.md` ile yeni ya da değişen paketlere bak.
3. Paketlenen motor klasöründe (`_internal`) beklenmeyen paket (özellikle pymupdf-layout, pymupdf4llm) olmadığını denetle.
4. Çıktıları bu tabloyla karşılaştır; yeni ya da değişen lisans (özellikle GPL/LGPL/AGPL) varsa ürün sahibine bildir.

## Açık noktalar

- AGPL-3.0 seçimi ve PyMuPDF ticari lisans karşılaştırması: ürün sahibi kararıyla hukukçu görüşü alınmadı (21 Kasım 2026). Kapalı kaynak dağıtım, farklı lisans ya da sunucunun harici kuruma verilmesi gündeme gelirse Artifex ticari lisansı ve AGPL madde 13 yeniden değerlendirilir.
- OpenCV tekerleği içindeki LGPL bileşenler ve masaüstü paketlemesinde (1.33, 1.90) yeniden dağıtım koşulları.
