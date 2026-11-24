# winget paketi

BulutBelge'nin Windows Paket Yöneticisi (winget) manifestleri. Kullanıcı kabul edildikten sonra şöyle kurar:

    winget install Proteksistem.BulutBelge

Manifestler `manifests/p/Proteksistem/BulutBelge/<sürüm>/` altında, Microsoft'un `microsoft/winget-pkgs` deposundaki
klasör düzeniyle tutulur. Kurulum dosyası GitHub sürüm sayfasındaki NSIS kurulum programıdır (`*_x64-setup.exe`, kullanıcı
kapsamı, `bulutbelge` komutunu PATH'e ekler); SHA-256 sürümün `SHA256SUMS` dosyasıyla aynı olmalıdır.

## Yeni sürüm

1. Sürüm yayımlandıktan sonra bir önceki sürüm klasörünü kopyalayın; `PackageVersion`, `InstallerUrl`, `InstallerSha256`
   (büyük harf), `ReleaseDate`, `ReleaseNotesUrl` ve `AppsAndFeaturesEntries` içindeki `DisplayVersion` alanlarını
   güncelleyin. `AppsAndFeaturesEntries`, kurulumun Program Ekle/Kaldır'a yazdığı değerlerle aynı olmalıdır (winget
   kurulu sürümü ve yükseltmeyi bununla tanır): `DisplayName` ve `ProductCode` `BulutBelge` (Tauri NSIS şablonu,
   `HKCU\...\Uninstall\BulutBelge`), `Publisher` 0.1.1'de kimlikten türetilen `proteksistem`, 0.1.2'den itibaren
   `tauri.conf.json` `bundle.publisher` değeri `Proteksistem`.
2. Bir Windows makinesinde doğrulayın ve deneyin (yönetici PowerShell'i gerekebilir):

       winget validate --manifest <klasör>
       winget settings --enable LocalManifestFiles
       winget install --manifest <klasör>

3. `microsoft/winget-pkgs` deposuna çekme isteği açın (bir çatal üzerinden, tek sürüm tek PR). Microsoft'un otomatik
   denetimi kurulumu dener ve dosyayı tarar; gerekirse bir moderatör inceler. Kurulum dosyaları kod imzalı değildir
   (24 Kasım 2026 kararı); imzasız kurulum dosyaları winget deposunda yaygın, kesin sonuç ilk denetimde görülür. Windows 11 Akıllı Uygulama Denetimi açık makinelerde kurulum
   engellenebilir.

Bilinen durum (Windows denemesi 6, 24 Kasım 2026): yerel manifestle `winget install --manifest` denemesinde sessiz
kurulum, imzasız kurulum dosyası için Windows'un "Bilinmeyen Yayımcı" onay penceresinde bekledi. Bu pencere dosyanın
imzasız olmasından gelir; manifestle kapatılamaz (kurulum anahtarları değil, Windows'un dosya güvenliği uyarısı). Kalıcı
çözüm kod imzasıdır (karar: `docs/kararlar/2026-11-24-windows-imza-winget-derleme-kaniti.md`). Microsoft'un
`winget-pkgs` doğrulaması kurulumu kendi ortamında sessiz dener; bu pencere orada da çıkarsa gönderim reddedilebilir.
Gönderimden önce aynı denemeyi depo kaynağıyla (`winget install --manifest`) ve pencerenin gerçek adıyla (SmartScreen mi,
"Dosya Aç - Güvenlik Uyarısı" mı) bir Windows makinesinde netleştirin.

Not: winget kurulum dosyasını tarayıcıdan indirmediği için "internetten indirildi" işareti konmaz; SmartScreen istemi
genelde çıkmaz. Dosyanın bütünlüğünü manifestteki SHA-256 korur.
