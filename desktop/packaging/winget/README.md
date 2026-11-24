# winget paketi

BulutBelge'nin Windows Paket Yöneticisi (winget) manifestleri. Kullanıcı kabul edildikten sonra şöyle kurar:

    winget install Proteksistem.BulutBelge

Manifestler `manifests/p/Proteksistem/BulutBelge/<sürüm>/` altında, Microsoft'un `microsoft/winget-pkgs` deposundaki
klasör düzeniyle tutulur. Kurulum dosyaları GitHub sürüm sayfasındaki **MSI** paketleridir (tr-TR ve en-US, makine
kapsamı, `C:\Program Files\BulutBelge`); SHA-256 sürümün `SHA256SUMS` dosyasıyla aynı olmalıdır.

**Neden NSIS değil MSI (24 Kasım 2026).** winget indirdiği dosyayı internetten gelmiş olarak işaretler (`ZoneId=3`).
İmzasız NSIS `setup.exe` sessiz kurulumda SmartScreen onayında bekliyordu (Windows denemesi 6 ve `Windows denemesi`
iş akışı: `smartscreen` süreci açık, kurulum 10 dakikada bitmedi). Aynı sürümün MSI'ı winget ile beklemeden kuruldu,
çünkü winget MSI'ı Windows Installer ile kurar. Kod imzası gelene kadar winget MSI kullanır. MSI `bulutbelge`
komutunu PATH'e eklemez; komut satırı ve ajan kullanımı için NSIS kurulumu (siteden) önerilir, MSI'da tam yol
`(Get-ItemProperty 'HKCU:\Software\proteksistem\BulutBelge').InstallDir` ile bulunur.

## Yeni sürüm

1. Sürüm yayımlandıktan sonra bir önceki sürüm klasörünü kopyalayın; `PackageVersion`, her iki kurulum için
   `InstallerUrl`, `InstallerSha256` (büyük harf), `ProductCode` ve `AppsAndFeaturesEntries` (`ProductCode`,
   `DisplayVersion`), ayrıca `ReleaseDate` ve `ReleaseNotesUrl` alanlarını güncelleyin. `ProductCode` her derlemede
   değişir; `UpgradeCode` sabittir. Değerler MSI'ın Property tablosundan okunur (Windows'ta
   `WindowsInstaller.Installer` COM nesnesi; macOS/Linux'ta `python-msi`). `Publisher` 0.1.1'de `proteksistem`,
   0.1.2'den itibaren `tauri.conf.json` `bundle.publisher` değeri `Proteksistem`.
2. Bir Windows makinesinde doğrulayın ve deneyin (yönetici PowerShell'i gerekebilir):

       winget validate --manifest <klasör>
       winget settings --enable LocalManifestFiles
       winget install --manifest <klasör>

3. `microsoft/winget-pkgs` deposuna çekme isteği açın (bir çatal üzerinden, tek sürüm tek PR). Microsoft'un otomatik
   denetimi kurulumu dener ve dosyayı tarar; gerekirse bir moderatör inceler. Kurulum dosyaları kod imzalı değildir
   (24 Kasım 2026 kararı); imzasız kurulum dosyaları winget deposunda yaygın, kesin sonuç ilk denetimde görülür. Windows 11 Akıllı Uygulama Denetimi açık makinelerde kurulum
   engellenebilir.

Otomatik deneme: GitHub'da `Windows denemesi` iş akışı (bir Derleme koşusunun numarasıyla elle çalışır) bu
manifesti temiz bir Windows makinesinde doğrular, sessiz kurar, `winget list` ile tanındığını ve kaldırmayı dener.

Dosyanın bütünlüğünü manifestteki SHA-256 korur.
