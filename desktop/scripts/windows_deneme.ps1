# Windows denemesinin otomatik kısmı (GitHub Actions Windows makinesi; .github/workflows/windows-deneme.yml).
# Temiz, atılıp giden bir makinede çalışır: paketi kurar, kaldırır, DNS ve ajan ayarı yazar. Kendi
# bilgisayarınızda çalıştırmayın. Gözle bakılması gerekenler (sihirbaz görünümü, kurulum metinleri, gerçek
# kullanıcı oturumundaki SmartScreen penceresi) bu betiğin dışında kalır.
#
# Bölümler: B (WebView2 şifreli DNS; eski 0.1.1 ile karşılaştırmalı), Program Ekle/Kaldır kaydı, D (yüz kutusu),
# F (fatura alanları), MSI kurulum yolu, winget yerel manifest.

param(
    [Parameter(Mandatory)] [string] $Paket,     # kurulum-windows dosyaları
    [Parameter(Mandatory)] [string] $Eski,      # karşılaştırma için 0.1.1 NSIS setup.exe
    [Parameter(Mandatory)] [string] $Belgeler,  # sahte belgeler (windows_deneme_belgeler.py uret)
    [Parameter(Mandatory)] [string] $Depo,      # depo kökü
    [Parameter(Mandatory)] [string] $Rapor,     # yazılacak Markdown rapor
    [int] $Bekleme1 = 120,
    [int] $Bekleme2 = 300,
    [switch] $SadeceWinget       # yalnızca winget bölümü (manifest değişikliğinden sonra hızlı deneme)
)

# Not: PowerShell değişken adları büyük/küçük harfe duyarsızdır; parametrelerle aynı adı kullanmayın.
$ErrorActionPreference = 'Continue'
# Bir bölüm hata verirse kaydedilir, sonraki bölümler yine çalışır.
trap { Yaz "HATA: $($_.Exception.Message) (satır $($_.InvocationInfo.ScriptLineNumber))"; $script:Hatalar++; continue }
$script:Hatalar = 0
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$AppId = 'com.proteksistem.bulutbelge'
$KurulumYeri = Join-Path $env:LOCALAPPDATA 'BulutBelge'
$Profil = Join-Path $env:LOCALAPPDATA $AppId
$VeriKlasoru = Join-Path $env:APPDATA $AppId
$Sonuclar = [System.Collections.Generic.List[object]]::new()

function Yaz([string] $Metin = '') { Add-Content -Path $Rapor -Value $Metin -Encoding utf8; Write-Host $Metin }
function Sonuc([string] $Bolum, [string] $Kontrol, [bool] $Gecti, [string] $Ayrinti = '') {
    $Sonuclar.Add([pscustomobject]@{ Bolum = $Bolum; Kontrol = $Kontrol; Gecti = $Gecti; Ayrinti = $Ayrinti })
    Yaz ("- {0} {1}{2}" -f ($(if ($Gecti) { 'GEÇTİ' } else { 'KALDI' })), $Kontrol, $(if ($Ayrinti) { ": $Ayrinti" } else { '' }))
}

function Uygulamayi-Kapat {
    Get-Process bulutbelge-desktop, bulutbelge-engine, msedgewebview2 -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
}

function Nsis-Kur([string] $Setup) {
    Uygulamayi-Kapat
    $p = Start-Process -FilePath $Setup -ArgumentList '/S' -Wait -PassThru
    return $p.ExitCode
}

function Nsis-Kaldir {
    Uygulamayi-Kapat
    $u = Join-Path $KurulumYeri 'uninstall.exe'
    if (Test-Path $u) { Start-Process -FilePath $u -ArgumentList '/S' -Wait | Out-Null; Start-Sleep -Seconds 5 }
}

function Uygulama-Exe {
    Get-ChildItem $KurulumYeri -Filter '*.exe' -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -notmatch 'uninstall' } | Select-Object -First 1 -ExpandProperty FullName
}

function Ozel-Adres([string] $a) {
    return $a -match '^(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|::1$|fe80:|0\.0\.0\.0)'
}

# Uygulamanın süreçlerinin (WebView2 dahil) dış bağlantıları. WebView2 süreçlerinde --type ve
# uygulamanın profil klasörünü kullanıp kullanmadığı da yazılır.
function Dis-Baglantilar {
    $surecler = @{}
    Get-CimInstance Win32_Process -Filter "Name='msedgewebview2.exe' OR Name='bulutbelge-desktop.exe' OR Name='bulutbelge-engine.exe'" |
        ForEach-Object { $surecler[[int]$_.ProcessId] = $_ }
    $satirlar = @()
    foreach ($c in Get-NetTCPConnection -State Established, SynSent, CloseWait -ErrorAction SilentlyContinue) {
        if (-not $surecler.ContainsKey([int]$c.OwningProcess)) { continue }
        if (Ozel-Adres $c.RemoteAddress) { continue }
        $s = $surecler[[int]$c.OwningProcess]
        $tur = if ($s.CommandLine -match '--type=([\w-]+)') { $Matches[1] } else { 'ana' }
        $ad = (Resolve-DnsName -Name $c.RemoteAddress -Type PTR -QuickTimeout -ErrorAction SilentlyContinue | Select-Object -First 1).NameHost
        $satirlar += [pscustomobject]@{
            Adres = "$($c.RemoteAddress):$($c.RemotePort)"; PTR = $(if ($ad) { $ad } else { '-' })
            Surec = $s.Name; Tur = $tur; Durum = "$($c.State)"
        }
    }
    return $satirlar
}

function Olc([string] $Baslik, [int[]] $Anlar) {
    $exe = Uygulama-Exe
    if (-not $exe) { Yaz "  uygulama dosyası bulunamadı"; return @() }
    [Environment]::SetEnvironmentVariable('WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS', $null, 'Process')
    Start-Process -FilePath $exe | Out-Null
    $gecen = 0; $tumu = @()
    foreach ($an in $Anlar) {
        Start-Sleep -Seconds ($an - $gecen); $gecen = $an
        $wv = @(Get-Process msedgewebview2 -ErrorAction SilentlyContinue).Count
        $b = @(Dis-Baglantilar)
        Yaz "  $Baslik, $an sn: WebView2 süreci $wv, dış bağlantı $($b.Count)"
        foreach ($x in $b) { Yaz ("    {0} ({1}) {2} --type={3} {4}" -f $x.Adres, $x.PTR, $x.Surec, $x.Tur, $x.Durum) }
        $tumu += $b
    }
    Uygulamayi-Kapat
    return $tumu
}

function DoH-Var($Baglantilar) {
    # Chromium DoH uç noktaları: chrome.cloudflare-dns.com (172.64.41.3, 162.159.61.3), dns.google (8.8.8.8, 8.8.4.4)
    return @($Baglantilar | Where-Object { $_.Adres -match '^(172\.64\.41\.3|162\.159\.61\.3|8\.8\.8\.8|8\.8\.4\.4|1\.1\.1\.1|1\.0\.0\.1):443$' }).Count -gt 0
}

function Dns-Modu {
    $ls = Join-Path $Profil 'EBWebView\Local State'
    if (-not (Test-Path $ls)) { return '(dosya yok)' }
    try { $m = (Get-Content $ls -Raw | ConvertFrom-Json).dns_over_https.mode; if ($m) { return $m } else { return '(ayar yok)' } }
    catch { return '(okunamadı)' }
}

# ---------------------------------------------------------------------------------------------------------
Set-Content -Path $Rapor -Value '' -Encoding utf8
$os = Get-CimInstance Win32_OperatingSystem
Yaz "# Windows denemesi (otomatik)"
Yaz ""
Yaz "Makine: $($os.Caption) $($os.Version), dil $((Get-Culture).Name). GitHub Actions; kişisel veri yok."
Yaz ""
Yaz "Paket dosyaları:"
Get-ChildItem $Paket -File | ForEach-Object {
    Yaz ("- {0}: {1:N1} MB, SHA-256 {2}" -f $_.Name, ($_.Length / 1MB), (Get-FileHash $_.FullName -Algorithm SHA256).Hash)
}
$Setup = Get-ChildItem $Paket -Filter '*x64-setup.exe' | Where-Object { $_.Name -notmatch 'cevrimdisi' } | Select-Object -First 1 -ExpandProperty FullName
$MsiTr = Get-ChildItem $Paket -Filter '*tr-TR.msi' | Where-Object { $_.Name -notmatch 'cevrimdisi' } | Select-Object -First 1 -ExpandProperty FullName

if (-not $SadeceWinget) {
# --- B. WebView2 şifreli DNS --------------------------------------------------------------------------------
Yaz ""
Yaz "## B. WebView2 şifreli DNS (W.1)"
# İnternet trafiğinin geçtiği bağdaştırıcı (varsayılan yol); sanal bağdaştırıcıların DNS istemcisi olmayabilir.
$yol = Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric, InterfaceMetric | Select-Object -First 1
$ad = Get-NetAdapter -InterfaceIndex $yol.InterfaceIndex -ErrorAction SilentlyContinue
Yaz "Bağdaştırıcı: $($ad.InterfaceDescription) (ifIndex $($ad.ifIndex))"
$eskiDns = (Get-DnsClientServerAddress -InterfaceIndex $ad.ifIndex -AddressFamily IPv4).ServerAddresses -join ', '
Set-DnsClientServerAddress -InterfaceIndex $ad.ifIndex -ServerAddresses '1.1.1.1', '8.8.8.8'
Clear-DnsClientCache
$yeniDns = (Get-DnsClientServerAddress -InterfaceIndex $ad.ifIndex -AddressFamily IPv4).ServerAddresses -join ', '
$dohSablon = @(Get-DnsClientDohServerAddress -ErrorAction SilentlyContinue).Count
Yaz "Bağdaştırıcı DNS: önce $eskiDns, deneme sırasında $yeniDns (deneme 6 ile aynı koşul). Windows DoH şablonu: $dohSablon."

Yaz ""
Yaz "1) Karşılaştırma: eski 0.1.1, temiz profil"
Nsis-Kaldir; Remove-Item $Profil -Recurse -Force -ErrorAction SilentlyContinue
$k = Nsis-Kur $Eski; Yaz "  kurulum çıkış kodu $k"
$olcEski = Olc 'eski' @($Bekleme1, $Bekleme2)
$eskiMod = Dns-Modu; Yaz "  Local State dns_over_https.mode: $eskiMod"

Yaz ""
Yaz "2) Yeni paket, eski profilin üzerine"
$k = Nsis-Kur $Setup; Yaz "  kurulum çıkış kodu $k"
$olcUst = Olc 'yeni (üzerine)' @($Bekleme1, $Bekleme2)
$ustMod = Dns-Modu; Yaz "  Local State dns_over_https.mode: $ustMod"

Yaz ""
Yaz "3) Yeni paket, temiz profil"
Nsis-Kaldir; Remove-Item $Profil -Recurse -Force -ErrorAction SilentlyContinue
$k = Nsis-Kur $Setup; Yaz "  kurulum çıkış kodu $k"
$olcTemiz = Olc 'yeni (temiz)' @($Bekleme1, $Bekleme2)
$temizMod = Dns-Modu; Yaz "  Local State dns_over_https.mode: $temizMod"

Yaz ""
Yaz "Sonuç:"
Sonuc 'B' 'Ölçüm düzeneği sorunu yakalıyor (eski 0.1.1 DoH adresine bağlanıyor)' (DoH-Var $olcEski) 'yakalamazsa yeni sonuçlar kanıt sayılmaz'
Sonuc 'B' 'Yeni paket, eski profil üzerine: DoH bağlantısı yok' (-not (DoH-Var $olcUst))
Sonuc 'B' 'Yeni paket, temiz profil: DoH bağlantısı yok' (-not (DoH-Var $olcTemiz))
Sonuc 'B' 'Local State dns_over_https.mode = off (iki durumda)' (($ustMod -eq 'off') -and ($temizMod -eq 'off')) "üzerine: $ustMod, temiz: $temizMod"

Set-DnsClientServerAddress -InterfaceIndex $ad.ifIndex -ResetServerAddresses
Clear-DnsClientCache
Yaz "Bağdaştırıcı DNS eski hâline döndü: $((Get-DnsClientServerAddress -InterfaceIndex $ad.ifIndex -AddressFamily IPv4).ServerAddresses -join ', ')"

# --- Program Ekle/Kaldır kaydı -------------------------------------------------------------------------------
Yaz ""
Yaz "## Program Ekle/Kaldır kaydı (NSIS)"
$arp = Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\BulutBelge' -ErrorAction SilentlyContinue
Yaz "DisplayName '$($arp.DisplayName)', Publisher '$($arp.Publisher)', DisplayVersion '$($arp.DisplayVersion)'"
Sonuc 'Kayıt' "NSIS yayıncı adı 'Proteksistem'" ($arp.Publisher -ceq 'Proteksistem') "$($arp.Publisher)"
Sonuc 'Kayıt' 'NSIS kaydı BulutBelge anahtarında, ad BulutBelge' (($null -ne $arp) -and ($arp.DisplayName -eq 'BulutBelge'))

# --- D ve F: komut satırıyla sahte belgeler ----------------------------------------------------------------
Yaz ""
Yaz "## D ve F: komut satırı (sahte belgeler)"
$motor = Get-ChildItem $KurulumYeri -Recurse -Filter 'bulutbelge-engine.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
Yaz "Motor: $(if ($motor) { 'bulundu' } else { 'BULUNAMADI' })"
function Ajan-Ayari([string] $ProfilId) {
    New-Item -ItemType Directory -Force -Path $VeriKlasoru | Out-Null
    $j = @{ version = 1; folders = @((Resolve-Path $Belgeler).Path); allow_write = $true; allow_without_terms = $true; profile = $ProfilId }
    # Atılıp giden test makinesi: ajan izni kullanıcı arayüzü yerine dosyayla verilir.
    [IO.File]::WriteAllText((Join-Path $VeriKlasoru 'ajan.json'), ($j | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
}
function Motor-Json([string[]] $Argumanlar) {
    $cikti = & $motor @Argumanlar 2>&1 | Out-String
    $kod = $LASTEXITCODE
    try { return @{ Kod = $kod; Veri = ($cikti | ConvertFrom-Json) } } catch { return @{ Kod = $kod; Veri = $null; Ham = $cikti } }
}
if ($motor) {
    Ajan-Ayari 'efatura'
    $f = Motor-Json @('scan', (Join-Path $Belgeler 'sahte-fatura.txt'), '--profil', 'efatura', '--json', '--ajan', 'windows-deneme')
    $t = $f.Veri.summary.turler
    Yaz "F. e-Fatura takımı, çıkış $($f.Kod), türler: $(($t | ConvertTo-Json -Compress))"
    Sonuc 'F' 'İki telefon bulundu (0850 ve artısız 90)' ($t.'Telefon' -eq 2) "$($t.'Telefon')"
    Sonuc 'F' 'Web sitesi bulundu' ($t.'Web sitesi / alan adı' -ge 1) "$($t.'Web sitesi / alan adı')"
    Sonuc 'F' 'MERSİS ve ticaret sicil bulundu' (($t.'MERSİS no' -ge 1) -and ($t.'Ticaret sicil no' -ge 1))

    Ajan-Ayari 'musteri'
    $d = Motor-Json @('mask', (Join-Path $Belgeler 'sahte-yuz.pdf'), '--profil', 'musteri', '--json', '--ajan', 'windows-deneme')
    $s = $d.Veri.summary
    Yaz "D. Müşteriye takımı, çıkış $($d.Kod), türler: $(($s.turler | ConvertTo-Json -Compress))"
    Sonuc 'D' 'Yüz bulundu ve maskelendi' ($s.turler.'Yüz (fotoğraf)' -ge 1)
    if ($s.hedef -and (Test-Path $s.hedef)) {
        $den = & python (Join-Path $Depo 'desktop\scripts\windows_deneme_belgeler.py') denetle $s.hedef 2>&1 | Out-String
        Yaz "  $($den.Trim())"
        Sonuc 'D' 'Yüzün yanındaki başlık ve açıklama silinmedi' ($LASTEXITCODE -eq 0)
    } else {
        Sonuc 'D' 'Maskeli kopya yazıldı' $false "$($d.Ham)"
    }
    Remove-Item (Join-Path $VeriKlasoru 'ajan.json') -Force -ErrorAction SilentlyContinue
}

# --- MSI kurulum yolu ----------------------------------------------------------------------------------------
Yaz ""
Yaz "## MSI (tr-TR) kurulum yolu"
Nsis-Kaldir
$log = Join-Path $env:RUNNER_TEMP 'msi.log'
$p = Start-Process msiexec.exe -ArgumentList '/i', "`"$MsiTr`"", '/qn', '/l*v', "`"$log`"" -Wait -PassThru
Yaz "msiexec çıkış kodu $($p.ExitCode)"
$pf = Join-Path $env:ProgramFiles 'BulutBelge'
Sonuc 'MSI' 'Program Files altına kuruldu' (Test-Path $pf)
$idir = (Get-ItemProperty 'HKCU:\Software\proteksistem\BulutBelge' -ErrorAction SilentlyContinue).InstallDir
Sonuc 'MSI' 'InstallDir kayıt değeri kurulum klasörünü gösteriyor' ($idir -and ($idir.TrimEnd('\') -eq $pf)) "$idir"
$msiArp = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' |
    ForEach-Object { Get-ItemProperty $_.PSPath } | Where-Object DisplayName -eq 'BulutBelge' | Select-Object -First 1
Sonuc 'MSI' "MSI yayıncı adı 'Proteksistem'" ($msiArp.Publisher -ceq 'Proteksistem') "$($msiArp.Publisher)"
$me = Get-ChildItem $pf -Recurse -Filter 'bulutbelge-engine.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
if ($me) { & $me --help *> $null; Sonuc 'MSI' 'Motor --help çalışıyor' ($LASTEXITCODE -eq 0) "çıkış $LASTEXITCODE" }
$p = Start-Process msiexec.exe -ArgumentList '/x', "`"$MsiTr`"", '/qn' -Wait -PassThru
Sonuc 'MSI' 'Kaldırma sonrası InstallDir anahtarı silindi' (-not (Test-Path 'HKCU:\Software\proteksistem\BulutBelge')) "msiexec /x çıkış $($p.ExitCode)"

}

# --- winget yerel manifest ------------------------------------------------------------------------------------
# Deneme 6 ve ilk otomatik koşu: NSIS manifestiyle sessiz kurulum "Starting package install..." aşamasında bekledi,
# aynı setup.exe doğrudan /S ile kuruluyordu. Bekleme sırasında açık pencereler ve indirilen dosyanın internet
# işareti (Zone.Identifier) kaydedilir. Neden SmartScreen'di; manifest bu yüzden MSI'a geçti (winget/README.md).
function Winget-Kur([string] $Man, [string] $Ad, [int] $Sure = 300) {
    $cikti = Join-Path $env:RUNNER_TEMP "winget-$Ad.txt"
    $basla = Get-Date
    $wi = Start-Process $wg.Source -ArgumentList 'install', '--manifest', "`"$Man`"", '--silent', '--accept-package-agreements',
        '--accept-source-agreements', '--disable-interactivity' -PassThru -RedirectStandardOutput $cikti
    $bitti = $wi.WaitForExit(90000)
    if (-not $bitti) {
        Yaz "  90 sn sonra hâlâ sürüyor; tanılama:"
        Get-Process | Where-Object { $_.StartTime -ge $basla -and $_.Id -ne $wi.Id } | ForEach-Object {
            Yaz ("    süreç {0} (pencere: '{1}')" -f $_.ProcessName, $_.MainWindowTitle)
        }
        Get-ChildItem (Join-Path $env:TEMP 'WinGet') -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.exe', '.msi' } | ForEach-Object {
                $z = Get-Content -Path $_.FullName -Stream Zone.Identifier -ErrorAction SilentlyContinue
                Yaz ("    indirilen {0}: Zone.Identifier {1}" -f $_.Name, $(if ($z) { ($z -join ' ') } else { 'yok' }))
            }
        $bitti = $wi.WaitForExit(($Sure - 90) * 1000)
    }
    if (-not $bitti) {
        Get-Process | Where-Object { $_.StartTime -ge $basla } | Stop-Process -Force -ErrorAction SilentlyContinue
    }
    $son = (Get-Content $cikti -ErrorAction SilentlyContinue | Where-Object { $_ -match '[A-Za-z]' } | Select-Object -Last 3) -join ' / '
    Yaz "  winget: $($son -replace '[\\|/-]\s+', '' -replace '\s{2,}', ' ')"
    return @{ Bitti = $bitti; Kod = $(if ($bitti) { $wi.ExitCode } else { 'zaman aşımı' }) }
}

Yaz ""
# Depodaki en yeni sürüm klasörü denenir (sürüm numarasına göre); kurulum dosyaları o sürümün GitHub Releases'taki
# resmî MSI'larıdır, derleme koşusunun paketleri değil.
$manKok = Join-Path $Depo 'desktop\packaging\winget\manifests\p\Proteksistem\BulutBelge'
$man = Get-ChildItem $manKok -Directory | Sort-Object { [version]$_.Name } | Select-Object -Last 1 -ExpandProperty FullName
Yaz "## winget yerel manifest (depodaki en yeni manifest $(Split-Path $man -Leaf): MSI, GitHub Releases'taki resmî dosyalar)"
$wg = Get-Command winget -ErrorAction SilentlyContinue
if (-not $wg) {
    Yaz "winget bu makinede yok; bölüm atlandı."
} else {
    Yaz "winget $(& $wg.Source --version)"
    & $wg.Source settings --enable LocalManifestFiles *> $null
    $v = & $wg.Source validate --manifest $man 2>&1 | Out-String
    Sonuc 'winget' 'Manifest doğrulaması' ($v -match 'succeeded') ($v.Trim() -replace '\s+', ' ')
    $r = Winget-Kur $man 'msi'
    Sonuc 'winget' 'Sessiz kurulum 5 dk içinde bitti (SmartScreen beklemesi yok)' $r.Bitti "çıkış $($r.Kod)"
    if ($r.Bitti) {
        Sonuc 'winget' 'Program Files altına kuruldu' (Test-Path (Join-Path $env:ProgramFiles 'BulutBelge'))
        # Yerel manifestle kurulan paket bir kaynağa bağlı olmadığından `winget list --id` onu tanımaz; winget kurulu
        # programı ProductCode ile görür. Paket winget deposuna girince eşleşme bu kod üzerinden yapılır.
        $kodlar = (Select-String -Path (Join-Path $man 'Proteksistem.BulutBelge.installer.yaml') -Pattern "ProductCode: '(\{[0-9A-F-]+\})'" -AllMatches).Matches |
            ForEach-Object { $_.Groups[1].Value } | Sort-Object -Unique
        $l = & $wg.Source list --name BulutBelge --accept-source-agreements --disable-interactivity 2>&1 | Out-String
        $satir = ($l -split "`n" | Where-Object { $_ -match 'BulutBelge' } | Select-Object -First 1) -replace '\s+', ' '
        $eslesen = @($kodlar | Where-Object { $l -match [regex]::Escape($_) })
        Sonuc 'winget' 'winget list kurulu programı manifestteki ProductCode ile görüyor' ($eslesen.Count -ge 1) "$satir"
        & $wg.Source uninstall --manifest $man --silent --disable-interactivity --accept-source-agreements *> $null
        $kalan = Get-ChildItem 'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall' | ForEach-Object { Get-ItemProperty $_.PSPath } |
            Where-Object DisplayName -eq 'BulutBelge'
        Sonuc 'winget' 'winget ile kaldırıldı' (-not $kalan)
    }
    & $wg.Source settings --disable LocalManifestFiles *> $null
}

# --- Özet ------------------------------------------------------------------------------------------------------
Yaz ""
Yaz "## Özet"
Yaz ""
Yaz "| Bölüm | Kontrol | Sonuç | Ayrıntı |"
Yaz "|---|---|---|---|"
foreach ($s in $Sonuclar) { Yaz ("| {0} | {1} | {2} | {3} |" -f $s.Bolum, $s.Kontrol, $(if ($s.Gecti) { 'geçti' } else { '**kaldı**' }), ($s.Ayrinti -replace '\|', '/')) }
$kalan = @($Sonuclar | Where-Object { -not $_.Gecti }).Count + $script:Hatalar
Yaz ""
Yaz "Toplam $($Sonuclar.Count) kontrol, kalan $kalan (betik hatası $($script:Hatalar))."
exit $(if ($kalan) { 1 } else { 0 })
