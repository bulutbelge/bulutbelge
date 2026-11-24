; BulutBelge: Tauri 2.12.4'ün Turkish.nsh dosyasının kopyası (bundle.windows.nsis.customLanguageFiles).
; Farkları: "product_name" yer tutucusu (Tauri dil dosyalarını işlemez, metinde olduğu gibi görünürdü)
; ${PRODUCTNAME} oldu; sonda W.5 için karşılama ve lisans sayfası metinleri (windows/hooks.nsh kullanır).
; NSIS'in kendi Türkçe dosyasındaki "programlari" yazım hatası ve "'Kabul Ediyorum'a basınız" ile
; düğmedeki "Katılıyorum" uyumsuzluğu bu metinlerle giderilir. Tauri yükseltilince bu dosya karşılaştırılmalı.
LangString addOrReinstall ${LANG_TURKISH} "Bileşen Ekle/Yeniden Yükle"
LangString alreadyInstalled ${LANG_TURKISH} "Daha Önceden Yüklenmiş"
LangString alreadyInstalledLong ${LANG_TURKISH} "${PRODUCTNAME} ${VERSION} daha önceden yüklenmiş. Gerçekleştirmek istediğiniz işlemi seçin ve devam etmek için İleri'ye tıklayın."
LangString appRunning ${LANG_TURKISH} "${PRODUCTNAME} çalışır durumda! Lütfen önce uygulamayı kapatın ve sonra tekrar deneyin."
LangString appRunningOkKill ${LANG_TURKISH} "${PRODUCTNAME} çalışır durumda!$\nUygulamayı sonlandırmak için Tamam'a tıklayın."
LangString chooseMaintenanceOption ${LANG_TURKISH} "Gerçekleştirmek istediğiniz bakım seçeneğini belirleyin."
LangString chooseHowToInstall ${LANG_TURKISH} "${PRODUCTNAME} uygulamasını nasıl yüklemek istediğinizi seçin."
LangString createDesktop ${LANG_TURKISH} "Masaüstü kısayolu oluştur"
LangString dontUninstall ${LANG_TURKISH} "Kaldırma işlemini gerçekleştirme"
LangString dontUninstallDowngrade ${LANG_TURKISH} "Kaldırma işlemini gerçekleştirme (Kaldırma işlemi yapmadan sürüm düşürme bu yükleyici için devre dışı bırakılmıştır)"
LangString failedToKillApp ${LANG_TURKISH} "${PRODUCTNAME} sonlandırılamadı. Lütfen önce kapatın sonra tekrar deneyin."
LangString installingWebview2 ${LANG_TURKISH} "WebView2 yükleniyor..."
LangString newerVersionInstalled ${LANG_TURKISH} "${PRODUCTNAME} uygulamasının daha yeni bir sürümü zaten yüklü! Daha eski bir sürümü yüklemeniz önerilmez. Bu eski sürümü gerçekten yüklemek istiyorsanız, önce mevcut sürümü kaldırmanız daha uygundur. Gerçekleştirmek istediğiniz işlemi seçin ve devam etmek için İleri'ye tıklayın."
LangString older ${LANG_TURKISH} "daha eski"
LangString olderOrUnknownVersionInstalled ${LANG_TURKISH} "Sisteminizde ${PRODUCTNAME} uygulamasının $R4 sürümü yüklü. Yükleme işleminden önce mevcut sürümü kaldırmanız önerilir. Gerçekleştirmek istediğiniz işlemi seçin ve devam etmek için İleri'ye tıklayın."
LangString silentDowngrades ${LANG_TURKISH} "Bu yükleyici için sürüm düşürme işlemleri devre dışı bırakıldı, sessiz yükleyici ile devam edilemiyor, lütfen bunun yerine grafik arayüz yükleyicisini kullanın.$\n"
LangString unableToUninstall ${LANG_TURKISH} "Kaldırma işlemi gerçekleştirilemiyor!"
LangString uninstallApp ${LANG_TURKISH} "${PRODUCTNAME}'i kaldır"
LangString uninstallBeforeInstalling ${LANG_TURKISH} "Yükleme yapmadan önce kaldırın"
LangString unknown ${LANG_TURKISH} "bilinmeyen"
LangString webview2AbortError ${LANG_TURKISH} "WebView2 yüklenemedi! Uygulama bu bileşen olmadan çalışamaz. Yükleyiciyi yeniden başlatmayı deneyin."
LangString webview2DownloadError ${LANG_TURKISH} "Hata: WebView2 İndirmesi Başarısız - $0"
LangString webview2DownloadSuccess ${LANG_TURKISH} "WebView2 önyükleyicisi başarıyla indirildi"
LangString webview2Downloading ${LANG_TURKISH} "WebView2 önyükleyicisi indiriliyor..."
LangString webview2InstallError ${LANG_TURKISH} "Hata: WebView2 yüklemesi $1 hata koduyla başarısız oldu."
LangString webview2InstallSuccess ${LANG_TURKISH} "WebView2 başarıyla yüklendi"
LangString deleteAppData ${LANG_TURKISH} "Uygulama verilerini sil"

; W.5: karşılama ve lisans sayfası (windows/hooks.nsh içindeki MUI_*_TEXT tanımları bunları kullanır)
LangString bbKarsilama ${LANG_TURKISH} "Bu sihirbaz $(^NameDA) kurulumunda size yol gösterecek.$\r$\n$\r$\nKuruluma başlamadan önce çalışan diğer programları kapatmanızı öneririz. Böylece bilgisayarınızı yeniden başlatmadan bazı sistem dosyaları sorunsuz güncellenebilir.$\r$\n$\r$\n$_CLICK"
LangString bbLisansAlt ${LANG_TURKISH} "Koşulları kabul ediyorsanız 'Katılıyorum' düğmesine basın. $(^NameDA) uygulamasını kurmak için koşulları kabul etmeniz gerekir."

; NSIS'in kendi Türkçe MUI dosyasındaki hatalı metinler (24 Kasım Windows ekran kontrolü). Tauri bu dosyayı
; MUI_LANGUAGE'dan sonra include ettiği için aynı adlı LangString'ler NSIS'in metnini geçersiz kılar
; (makensis "set multiple times" uyarısı verir, hata değildir).
LangString MUI_TEXT_FINISH_INFO_TEXT ${LANG_TURKISH} "$(^NameDA) bilgisayarınıza kuruldu.$\r$\n$\r$\nKurulumu kapatmak için 'Bitir' düğmesine basın."
LangString MUI_TEXT_FINISH_INFO_REBOOT ${LANG_TURKISH} "$(^NameDA) kurulumunun tamamlanması için bilgisayarınızı yeniden başlatmanız gerekiyor. Bilgisayarınızı şimdi yeniden başlatmak istiyor musunuz?"
LangString MUI_UNTEXT_UNINSTALLING_SUBTITLE ${LANG_TURKISH} "Lütfen $(^NameDA) programı sisteminizden kaldırılırken bekleyin."
LangString MUI_UNTEXT_FINISH_TITLE ${LANG_TURKISH} "Kaldırma İşlemi Tamamlandı"
LangString MUI_UNTEXT_ABORTWARNING ${LANG_TURKISH} "$(^Name) programını kaldırma işleminden çıkmak istediğinize emin misiniz?"

; Kaldırmadan sonra uygulama verisinin nerede kaldığı (windows/hooks.nsh, NSIS_HOOK_POSTUNINSTALL)
LangString bbVeriKaldi ${LANG_TURKISH} "Ayarlarınız ve işlem günlüğünüz $APPDATA\com.proteksistem.bulutbelge klasöründe kaldı. Gerekmiyorsa bu klasörü elle silebilirsiniz."
