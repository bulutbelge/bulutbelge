# Üçüncü taraf lisans bildirimi

BulutBelge masaüstü uygulaması ve `core/`, GNU Affero Genel Kamu Lisansı sürüm 3 (AGPL-3.0) altındadır (bkz. `LICENSE`). Telif hakkı: Copyright (c) 2026 PROTEK YAZILIM SİSTEM DANIŞMANLIK BİLG. SAN. VE TİC. LTD. ŞTİ.

Aşağıdaki tablolar öne çıkan bileşenleri ve dikkat isteyen lisansları gösterir. Bütün bağımlılıkların sürüm ve lisans listesi [THIRD-PARTY-LICENSES.md](THIRD-PARTY-LICENSES.md) içindedir.

## Sorumluluk reddi

BulutBelge yardımcı bir araçtır; kişisel bilgileri %100 doğrulukla bulamayabilir ya da maskeleyemeyebilir. "Bulunamadı", "maskelendi" ya da "iz kalmadı" bildirimleri kesin sonuç değildir; çıktıyı paylaşmadan önce kendiniz gözden geçirin. Yazılım AGPL-3.0'ın 15. ve 16. maddeleri uyarınca "olduğu gibi", hiçbir garanti olmadan sunulur. Kullanım koşullarının tamamı: <https://bulutbelge.com/kosullar.html> (kurulum programında da gösterilir). `LICENSE` dosyası lisansın değiştirilmemiş metnidir; bu not onun parçası değildir.

## Python (çekirdek ve masaüstü motoru)

| Bileşen | Lisans | Not |
|---|---|---|
| PyMuPDF (MuPDF, içinde Tesseract OCR) | AGPL-3.0 ya da Artifex ticari lisansı | Projeyi AGPL-3.0'a bağlayan bileşen. PyMuPDF'nin kendi parçası olan düzen çözümleme modülü (`pymupdf/layout`) kullanılmaz ve paketten çıkarılır |
| cryptography | Apache-2.0 ya da BSD-3-Clause | |
| regex | Apache-2.0 ve CNRI-Python | |
| Pillow | MIT-CMU (HPND benzeri) | |
| lxml | BSD-3-Clause | libxml2 ve libxslt (MIT) paketle gelir |
| opencv-python-headless | Apache-2.0 | Görsellerde yüz, plaka, QR kodu, barkod, kaşe ve MRZ tespiti için kullanılır. Kaynaktan, FFmpeg'siz derlenir; aşağıdaki "OpenCV yapısı" bölümüne bakın |
| NumPy | BSD-3-Clause (ayrıca 0BSD, MIT, Zlib, CC0-1.0 parçaları) | |

Ayrı yayımlanan `pymupdf4llm` ve `pymupdf-layout` paketleri kurulu bağımlılık listesinde görünür ama kodumuz bunları kullanmaz ve kurulum paketine alınmaz (`pymupdf-layout` 2.1 içerik taşımayan bir geçiş paketidir). `onnxruntime` paketlenmez.

## OCR dil dosyaları

| Bileşen | Lisans | Not |
|---|---|---|
| Tesseract `eng` ve `tur` eğitilmiş veri | Apache-2.0 | Kaynak: <https://github.com/tesseract-ocr/tessdata_fast>; indirme betiği (`desktop/engine/tessdata_indir.py`) dosyaları SHA-256 özetiyle doğrular |

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
| ureq, native-tls | MIT ya da Apache-2.0 | Yalnızca kullanıcının açtığı sürüm denetimi için |

Paylaşımlı ya da ikili lisanslı Rust ve JavaScript bileşenleri:

- **MPL-2.0** (Rust: cssparser, cssparser-macros, dtoa-short, option-ext, selectors): dosya düzeyinde paylaşımlı lisans; değiştirilmeden kullanılır, kaynakları crates.io'dadır.
- **İkili lisanslı:** jszip (MIT veya GPL-3.0-or-later; MIT seçilir), r-efi (MIT, Apache-2.0 veya LGPL-2.1-or-later; MIT ya da Apache-2.0 seçilir).

## OpenCV yapısı

`opencv-python-headless` 4.14.0.94, PyPI'daki kaynak arşivinden (SHA-256 özeti `desktop/engine/requirements.lock` ile doğrulanır) **FFmpeg, GStreamer ve Intel IPP olmadan** derlenir (`desktop/engine/opencv_derle.py`). BulutBelge video işlemez; bu yapı FFmpeg'i ve onun GPL ya da LGPL lisanslı kodeklerini içermez. OpenCV'nin kendi içinde derlenen yardımcı kütüphaneler (ör. libjpeg-turbo, libpng, libtiff, libwebp, OpenJPEG, zlib) izin veren lisanslıdır. Tekerleğin lisans dosyaları kurulum klasöründe `engine/_internal/cv2/` altındadır (`LICENSE.txt`, `LICENSE-3RD-PARTY.txt`); ikincisi PyPI tekerleği için yazılmış genel bir metindir ve bu yapıda bulunmayan FFmpeg'i de anar. Paketleme betiği, FFmpeg kütüphanelerinden biri pakette bulunursa derlemeyi durdurur.

Sunucu imajı da aynı betik ve kilitle, ayrı bir derleme aşamasında FFmpeg'siz OpenCV kurar (`server/Dockerfile`); derleme araçları son imaja girmez ve imaj, OpenCV FFmpeg ile derlenmişse oluşturulmaz.

Kaynak kodu: <https://github.com/opencv/opencv-python> (sürüm 4.14.0.94) ve <https://github.com/opencv/opencv>.

## Derleme araçları

PyInstaller, motoru paketlemek için kullanılır (GPL-2.0, önyükleyici istisnasıyla): istisna, PyInstaller önyükleyicisini içeren paketlerin kendi lisanslarıyla dağıtılmasına izin verir. Vite, TypeScript, pip ve setuptools dağıtıma girmez.

## Yenileme (her sürümden önce)

1. `python core/tools/lisans_listesi_uret.py > THIRD-PARTY-LICENSES.md` (motor sanal ortamı, `npm ci` ve Rust araçları kurulu olmalı; çıktı Python, JavaScript ve Rust'ı kapsar).
2. `git diff THIRD-PARTY-LICENSES.md` ile yeni ya da değişen paketlere bakılır.
3. Paketleme betiği (`desktop/engine/build.py`) her platformda beklenmeyen paketleri (`pymupdf4llm`, `onnxruntime`) ve FFmpeg kütüphanelerini denetler, bulursa derlemeyi durdurur; PyMuPDF'nin düzen modülünü (`pymupdf/layout`) paketten çıkarır.
4. Yeni ya da değişen paylaşımlı lisans (GPL, LGPL, AGPL, MPL) bu bildirime işlenir.
