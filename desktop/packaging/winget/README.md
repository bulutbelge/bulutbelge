# winget paketi

BulutBelge'nin Windows Paket Yöneticisi (winget) manifestleri. Kullanıcı kabul edildikten sonra şöyle kurar:

    winget install Proteksistem.BulutBelge

Manifestler `manifests/p/Proteksistem/BulutBelge/<sürüm>/` altında, Microsoft'un `microsoft/winget-pkgs` deposundaki
klasör düzeniyle tutulur. Kurulum dosyası GitHub sürüm sayfasındaki NSIS kurulum programıdır (`*_x64-setup.exe`, kullanıcı
kapsamı, `bulutbelge` komutunu PATH'e ekler); SHA-256 sürümün `SHA256SUMS` dosyasıyla aynı olmalıdır.

## Yeni sürüm

1. Sürüm yayımlandıktan sonra bir önceki sürüm klasörünü kopyalayın; `PackageVersion`, `InstallerUrl`, `InstallerSha256`
   (büyük harf), `ReleaseDate` ve `ReleaseNotesUrl` alanlarını güncelleyin.
2. Bir Windows makinesinde doğrulayın ve deneyin (yönetici PowerShell'i gerekebilir):

       winget validate --manifest <klasör>
       winget settings --enable LocalManifestFiles
       winget install --manifest <klasör>

3. `microsoft/winget-pkgs` deposuna çekme isteği açın (bir çatal üzerinden, tek sürüm tek PR). Microsoft'un otomatik
   denetimi kurulumu dener ve dosyayı tarar; gerekirse bir moderatör inceler. Kurulum dosyaları kod imzalı değildir
   (24 Kasım 2026 kararı); imzasız kurulum dosyaları winget deposunda yaygın, kesin sonuç ilk denetimde görülür. Windows 11 Akıllı Uygulama Denetimi açık makinelerde kurulum
   engellenebilir.

Not: winget kurulum dosyasını tarayıcıdan indirmediği için "internetten indirildi" işareti konmaz; SmartScreen istemi
genelde çıkmaz. Dosyanın bütünlüğünü manifestteki SHA-256 korur.
