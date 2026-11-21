; BulutBelge komut satırı: NSIS kurulumu, kurulum klasörünü KULLANICI PATH'ine ekler ve
; `bulutbelge` kısa adını yazar; böylece yeni açılan terminalde `bulutbelge read <dosya>` çalışır.
; Kaldırınca ikisi de geri alınır. Yalnızca geçerli kullanıcının ortamı değişir (yönetici izni gerekmez).
; Not: MSI paketi PATH'e dokunmaz; MSI kullananlar komutu tam yolla çağırır (docs/AJAN-KOMUT-SATIRI.md).

!macro NSIS_HOOK_POSTINSTALL
  ; Kısa ad: bulutbelge.cmd -> motor exe'si (argümanla çağrılınca ajan komutu olarak çalışır).
  FileOpen $0 "$INSTDIR\bulutbelge.cmd" w
  FileWrite $0 `@"%~dp0engine\bulutbelge-engine.exe" %*$\r$\n`
  FileClose $0
  ; Kurulum klasörünü kullanıcı PATH'ine ekle (zaten varsa dokunma).
  nsExec::ExecToLog `powershell.exe -NoProfile -NonInteractive -Command "$$d='$INSTDIR'; $$p=[Environment]::GetEnvironmentVariable('Path','User'); if (-not (($$p -split ';') -contains $$d)) { [Environment]::SetEnvironmentVariable('Path', (($$p.TrimEnd(';') + ';' + $$d).TrimStart(';')), 'User') }"`
  Pop $0
!macroend

!macro NSIS_HOOK_POSTUNINSTALL
  Delete "$INSTDIR\bulutbelge.cmd"
  ; PATH'ten yalnızca kendi klasörümüzü çıkar.
  nsExec::ExecToLog `powershell.exe -NoProfile -NonInteractive -Command "$$d='$INSTDIR'; $$p=[Environment]::GetEnvironmentVariable('Path','User'); if ($$p) { [Environment]::SetEnvironmentVariable('Path', (($$p -split ';' | Where-Object { $$_ -and $$_ -ne $$d }) -join ';'), 'User') }"`
  Pop $0
  ; Boş kalan kurulum klasörünü kaldır (doluysa RMDir dokunmaz) ve kayıt defteri anahtarını sil.
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\proteksistem\BulutBelge"
  ; Uygulama verisi silinmediyse ayarların nerede kaldığını söyle (sessiz kaldırmada gösterme).
  ${If} $DeleteAppDataCheckboxState = 0
  ${AndIfNot} ${Silent}
    MessageBox MB_OK|MB_ICONINFORMATION "Ayarlarınız ve işlem günlüğünüz $APPDATA\com.proteksistem.bulutbelge klasöründe kaldı. Gerekmiyorsa bu klasörü elle silebilirsiniz."
  ${EndIf}
!macroend
