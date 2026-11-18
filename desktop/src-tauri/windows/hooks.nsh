; BulutBelge komut satırı (TAKIP 1.33): NSIS kurulumu, kurulum klasörünü KULLANICI PATH'ine ekler ve
; `bulutbelge` kısa adını yazar; böylece yeni açılan terminalde `bulutbelge read <dosya>` çalışır.
; Kaldırınca ikisi de geri alınır. Yalnızca geçerli kullanıcının ortamı değişir (yönetici izni gerekmez).
; Not: MSI paketi PATH'e dokunmaz; MSI kullananlar komutu tam yolla çağırır (docs/AJAN-KOMUT-SATIRI.md).

!macro NSIS_HOOK_POSTINSTALL
  ; Kısa ad: bulutbelge.cmd -> motor exe'si (argümanla çağrılınca ajan komutu olarak çalışır).
  FileOpen $0 "$INSTDIR\bulutbelge.cmd" w
  FileWrite $0 `@"%~dp0bulutbelge-engine.exe" %*$\r$\n`
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
!macroend
