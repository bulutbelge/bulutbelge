# Üçüncü taraf lisans bildirimi (TAKIP 1.83)

BulutBelge masaüstü uygulaması ve `core/`, GNU Affero Genel Kamu Lisansı sürüm 3 (AGPL-3.0) altındadır (bkz. `LICENSE`). Karar 17 Kasım 2026'da oturum sahibi tarafından verildi; hukukçu teyidi yapılmadı, istenirse lisans değiştirilebilir.
Sürümler 17 Kasım 2026'da geliştirme ortamından okundu; yayın sırasında kilit dosyalarından yeniden üretilmeli (aşağıdaki "Yenileme").

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

## Yenileme (yayın öncesi)

1. Python: `pip-licenses --format=markdown` (motor sanal ortamında).
2. JavaScript: `npx license-checker --production --summary`.
3. Rust: `cargo about generate` ya da `cargo license`.
4. Çıktıları bu tabloyla karşılaştır; yeni ya da değişen lisans (özellikle GPL/LGPL/AGPL) varsa hukukçuya bildir.

## Açık noktalar

- AGPL-3.0 seçimi ve PyMuPDF ticari lisans karşılaştırması: hukukçu teyidi (TAKIP 1.83).
- OpenCV tekerleği içindeki LGPL bileşenler ve masaüstü paketlemesinde (1.33, 1.90) yeniden dağıtım koşulları.
